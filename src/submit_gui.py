"""
图形化界面提交系统
它由submit.py调用
业务逻辑在submit_logic.py中实现，这里主要负责UI交互
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
from typing import Dict, List, Any, Optional, Tuple
import threading 
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 统一根目录锚定到 config_loader.py 的 project_root
from src.core.config_loader import get_config_instance
BASE_DIR = str(get_config_instance().project_root)

from src.core.database_model import Paper
# 引入业务逻辑层
from src.submit_logic import SubmitLogic
# 引入AI生成器 (用于GUI直接调用，如配置)
from src.ai_generator import AIGenerator, PROVIDER_CONFIGS

class PaperSubmissionGUI:
    """论文提交图形界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Awesome 论文提交系统")
        self.root.geometry("1300x850")
        
        # 初始化业务逻辑控制器
        self.logic = SubmitLogic()
        
        # 快捷引用
        self.config = self.logic.config
        self.settings = self.logic.settings
        
        self.current_paper_index = -1
        # 存储当前筛选后的索引列表 [real_index_in_logic_papers, ...]
        self.filtered_indices: List[int] = [] 
        
        # 尺寸调整：紧凑 (1.1)
        self.root.tk.call('tk', 'scaling', 1.3)
        
        self.color_invalid = "#FFC0C0" 
        self.color_required_empty = "#E6F7FF"
        self.color_normal = "white"
        self.color_conflict = "#FFEEEE" # 冲突行背景色
        
        self.style = ttk.Style()
        self.style.map('Invalid.TCombobox', fieldbackground=[('readonly', self.color_invalid)])
        self.style.map('Required.TCombobox', fieldbackground=[('readonly', self.color_required_empty)])
        self.style.configure("Conflict.Treeview", background=self.color_conflict)

        self._suppress_select_event = False
        
        # 跟踪已导入的文件，避免重复导入
        # 格式: {'pipeline_image': (源路径, 目标相对路径), 'paper_file': (源路径, 目标相对路径)}
        self._imported_files: Dict[str, Optional[Tuple[str, str]]] = {
            'pipeline_image': None,
            'paper_file': None
        }

        self.setup_ui()
        
        # 检查管理员状态并更新UI
        self._update_admin_ui_state()
        
        self.load_initial_data()
        
        messagebox.showinfo("须知",f"该界面用于:\n    1.规范化生成的处理json/csv更新文件\n    2.自动分支并提交PR（完整版功能）\n如果根目录中的submit_template.xlsx或submit_template.json已按规范填写内容，你可以手动提交PR或使用该界面自动分支并提交PR，您提交的内容会自动更新到仓库论文列表")
        
        self.tooltip = None
        self.show_placeholder()
    
    def load_initial_data(self):
        try:
            count = self.logic.load_existing_updates()
            if count > 0:
                self.refresh_list_view()
                filename = os.path.basename(self.logic.primary_update_file) if self.logic.primary_update_file else "Template"
                self.update_status(f"已从 {filename} 加载 {count} 篇论文")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1) 
        main_frame.columnconfigure(1, weight=1) 
        main_frame.rowconfigure(1, weight=1)
        
        # === 顶部 Header 区域 ===
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        
        title_label = ttk.Label(header_frame, text="🎓 Awesome 论文规范化提交处理界面", font=("Arial", 14, "bold"))
        title_label.pack(side=tk.LEFT)
        
        # 显示当前活跃的更新文件提示
        active_files = []
        paths = self.logic.config.settings['paths']
        for k in ['update_json', 'update_csv', 'my_update_json', 'my_update_csv']:
            p = paths.get(k)
            if p: active_files.append(os.path.basename(p))
                
        # 额外更新文件
        extra = paths.get('extra_update_files_list', [])
        active_files.extend([os.path.basename(f) for f in extra])
        
        files_str = ", ".join(active_files[:6])
        if len(active_files) > 6: files_str += "..."
        
        info_label = ttk.Label(header_frame, text=f"  [Active: {files_str}]", foreground="gray")
        info_label.pack(side=tk.LEFT, padx=10)

        # 管理员切换按钮
        self.admin_btn = ttk.Button(header_frame, text="🔒 管理员模式", command=self._toggle_admin_mode, width=15)
        self.admin_btn.pack(side=tk.RIGHT)
        
        # === 主分割窗口 ===
        self.paned_window = tk.PanedWindow(
            main_frame,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            sashrelief=tk.RAISED,
            showhandle=False,
            opaqueresize=True,
            bd=0
            
        )
        self.paned_window.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=(0,0), pady=(0,0))

        left_frame = ttk.Frame(self.paned_window)
        self.right_container = ttk.Frame(self.paned_window)

        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(2, weight=1) # Treeview expands
        self.right_container.columnconfigure(0, weight=1)
        self.right_container.rowconfigure(0, weight=1)
        
        self.setup_paper_list_frame(left_frame)
        self.setup_paper_form_frame(self.right_container)
        
        self.paned_window.add(left_frame, minsize=250, stretch="always")
        self.paned_window.add(self.right_container, minsize=500, stretch="always")

        def _set_initial_sash_position():
            total_width = self.paned_window.winfo_width()
            if total_width > 1:
                self.paned_window.sash_place(0, int(total_width * 0.22), 0)
        self.root.after_idle(_set_initial_sash_position)

        self.placeholder_label = ttk.Label(
            self.right_container,
            text="👈 请从左侧列表选择一篇论文以进行编辑",
            font=("Arial", 12),
            foreground="gray",
            anchor="center"
        )
        
        self.setup_buttons_frame(main_frame)
        self.setup_status_bar(main_frame)
    
# ================= 1. 论文列表区域布局修改 =================

    def setup_paper_list_frame(self, parent):
        # 定义 grid 权重，确保 list_frame (row 1) 占据绝大部分空间
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0) # Header
        parent.rowconfigure(1, weight=1) # Treeview (Expand)
        parent.rowconfigure(2, weight=0) # Buttons

        # --- Row 0: 标题 + 搜索 + 筛选 ---
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # 1. 标题
        list_title = ttk.Label(header_frame, text="📚 论文列表", font=("Arial", 11, "bold"))
        list_title.pack(side=tk.LEFT, padx=(0, 5))
        
        # 2. 分类筛选 (Right)
        self.cat_filter_combo = ttk.Combobox(header_frame, state="readonly", width=15)
        cats = ["All Categories"] + [c['name'] for c in self.config.get_active_categories()]
        self.cat_filter_combo['values'] = cats
        self.cat_filter_combo.set("All Categories")
        self.cat_filter_combo.bind("<<ComboboxSelected>>", self._on_search_change)
        self.cat_filter_combo.pack(side=tk.RIGHT)
        
        # 3. 搜索框 (Middle Fill) - 带占位符逻辑
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(header_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)
        
        # 占位符逻辑
        self._search_placeholder = "输入关键词进行筛选..."
        self._search_is_placeholder = True
        
        def on_search_focus_in(event):
            if self._search_is_placeholder:
                self.search_var.set("")
                self.search_entry.config(foreground='black')
                self._search_is_placeholder = False

        def on_search_focus_out(event):
            if not self.search_var.get():
                self._search_is_placeholder = True
                self.search_var.set(self._search_placeholder)
                self.search_entry.config(foreground='gray')
            
        # 初始化占位符
        on_search_focus_out(None)
        
        # 绑定事件
        self.search_entry.bind("<FocusIn>", on_search_focus_in)
        self.search_entry.bind("<FocusOut>", on_search_focus_out)
        # 只有当不是占位符时才触发搜索逻辑
        def on_trace(*args):
            if not self._search_is_placeholder:
                self._on_search_change()
        self.search_var.trace("w", on_trace)


        # --- Row 1: 列表区域 ---
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew")
        
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        columns = ("ID", "Title", "Status") 
        self.paper_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        self.paper_tree.heading("ID", text="#")
        self.paper_tree.heading("Title", text="Title")
        self.paper_tree.heading("Status", text="Status")
        
        self.paper_tree.column("ID", width=40, anchor="center")
        self.paper_tree.column("Title", width=200)
        self.paper_tree.column("Status", width=60, anchor="center")
        
        self.paper_tree.tag_configure('conflict', background=self.color_conflict)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.paper_tree.yview)
        self.paper_tree.configure(yscrollcommand=scrollbar.set)
        
        self.paper_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
    
        self.paper_tree.bind('<<TreeviewSelect>>', self.on_paper_selected)
        self.paper_tree.bind('<Enter>', lambda e: self._bind_global_scroll(self.paper_tree.yview_scroll))
        
        self.paper_tree.bind("<Button-3>", self._show_context_menu)
        self.paper_tree.bind("<Button-1>", self._on_drag_start)
        self.paper_tree.bind("<B1-Motion>", self._on_drag_motion)
        self.paper_tree.bind("<ButtonRelease-1>", self._on_drag_release)
        
        # --- Row 2: 按钮区域 (调整顺序) ---
        list_buttons_frame = ttk.Frame(parent)
        list_buttons_frame.grid(row=2, column=0, pady=(5, 0), sticky="ew")
        
        # 按文字长度分配：Zotero 略宽，其他三个略窄
        list_buttons_frame.columnconfigure(0, weight=14)
        list_buttons_frame.columnconfigure(1, weight=10)
        list_buttons_frame.columnconfigure(2, weight=10)
        list_buttons_frame.columnconfigure(3, weight=10)

        ttk.Button(list_buttons_frame, text="📑 从Zotero新建", command=self.add_from_zotero_meta).grid(
            row=0, column=0, sticky="ew", padx=2
        )
        ttk.Button(list_buttons_frame, text="➕ 新建论文", command=self.add_paper).grid(
            row=0, column=1, sticky="ew", padx=2
        )
        ttk.Button(list_buttons_frame, text="🗑 删除论文", command=self.delete_paper).grid(
            row=0, column=2, sticky="ew", padx=2
        )
        ttk.Button(list_buttons_frame, text="🧹 清空列表", command=self.clear_papers).grid(
            row=0, column=3, sticky="ew", padx=2
        )

    # ================= 2. 表单区域布局 (按钮宽度对齐) =================

    def setup_paper_form_frame(self, parent):
        self.form_container = ttk.Frame(parent)
        
        # --- 标题栏 (Grid 对齐) ---
        title_frame = ttk.Frame(self.form_container)
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # 定义列权重：Col 0 是 Label，Col 1 是 Button (要拉伸)
        title_frame.columnconfigure(1, weight=1)

        form_title = ttk.Label(title_frame, text="📝 论文详情", font=("Arial", 11, "bold"))
        # 给 Label 一个固定的 minsize 或者 padx，使其宽度大致等于下方 Label 的宽度
        # 假设下方 Label 宽度大约 120px
        form_title.grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        fill_zotero_btn = ttk.Button(title_frame, text="📋 填充当前表单 (Zotero)", command=self.fill_from_zotero_meta)
        # sticky="ew" 让按钮横向填满，实现“右边也对齐”
        # padx=(5, 5) 这里的左边距需要手动调整以对齐下方的输入框起始位置
        # 下方输入框起始位置 = Label Width + Label Padding
        fill_zotero_btn.grid(row=0, column=1, sticky="ew", padx=(15, 5)) 
        
        # --- 可滚动区域 ---
        self.form_canvas = tk.Canvas(self.form_container)
        scrollbar = ttk.Scrollbar(self.form_container, orient=tk.VERTICAL, command=self.form_canvas.yview)
        
        self.form_frame = ttk.Frame(self.form_canvas)
        self.form_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.form_canvas_window = self.form_canvas.create_window((0, 0), window=self.form_frame, anchor=tk.NW, width=800)

        self.form_canvas.bind('<Enter>', lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
        self.form_frame.bind('<Enter>', lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))

        self.form_canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        
        self.form_container.columnconfigure(0, weight=1)
        self.form_container.rowconfigure(1, weight=1)
        
        self.form_frame.bind("<Configure>", lambda e: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all")))
        self.form_canvas.bind("<Configure>", self._on_canvas_configure)
        
        self.create_form_fields()

    
    def _on_canvas_configure(self, event):
        if event.width > 1:
            self.form_canvas.itemconfig(self.form_canvas_window, width=event.width)

    def create_form_fields(self):
        """动态生成表单字段"""
        # 清除旧控件（用于切换管理员模式时刷新）
        for widget in self.form_frame.winfo_children():
            widget.destroy()

        row = 0
        active_tags = self.config.get_active_tags()
        
        self.form_fields = {}
        self.field_widgets = {}
        
        for tag in active_tags:
            # 逻辑：如果是系统字段且不是管理员模式，隐藏
            # 管理员模式下，显示所有字段（包括 id, conflict_marker 等）
            is_system = tag.get('system_var', False)
            if is_system and not self.logic.is_admin:
                continue
            
            # 逻辑：tag['variable'] 是唯一标识
            variable = tag.get('variable')
            if not variable:
                continue
            display_name = tag['display_name']
            description = tag.get('description', '')
            required = tag.get('required', False)
            field_type = tag.get('type', 'string')
            
            label_text = f"{display_name}* :" if required else f"{display_name} :"
            
            # 特殊标注系统字段
            if is_system:
                label_text = f"[SYS] {label_text}"
            
            label = ttk.Label(self.form_frame, text=label_text)
            label_sticky = tk.NW if field_type == 'text' else tk.W
            
            label.grid(row=row, column=0, sticky=label_sticky, pady=(2, 2))
            if description: self.create_tooltip(label, description)
            
            # === 1. Category Field (Complex) ===
            if field_type == 'enum[]' and variable == 'category':
                container = ttk.Frame(self.form_frame)
                container.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))

                categories = self.config.get_active_categories()
                category_names = [cat['name'] for cat in categories]
                category_values = [cat['unique_name'] for cat in categories]
                self.category_mapping = dict(zip(category_names, category_values))
                self.category_description_mapping = {cat['name']: cat.get('description', '') for cat in categories}
                self.category_reverse_mapping = {v: k for k, v in self.category_mapping.items()}
                self.category_reverse_mapping[""] = ""

                self.category_rows = []
                self.category_container = container
                try:
                    cfg_max = int(self.settings['database'].get('max_categories_per_paper', 4))
                except Exception:
                    cfg_max = 4
                self._gui_category_max = min(cfg_max, 6)

                self._gui_add_category_row('')
                self.form_fields[variable] = container
                self.field_widgets[variable] = container

            # === 2. File Fields (Asset Import) ===
            elif variable in ['pipeline_image', 'paper_file']:
                self._create_file_field_ui(row, variable)

            # === 3. Standard Enum ===
            elif field_type == 'enum':
                values = tag.get('options', [])
                # Hardcoded fallback for status if not in config
                if variable == 'status' and not values: 
                    values = ['unread', 'reading', 'done', 'skimmed', 'adopted']
                
                combo = ttk.Combobox(self.form_frame, values=values, state='readonly')
                combo.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))
                combo.bind("<<ComboboxSelected>>", lambda e, v=variable, w=combo: self._on_field_change(v, w))
                self._bind_widget_scroll_events(combo)
                
                self.form_fields[variable] = combo
                self.field_widgets[variable] = combo

            # === 4. Bool ===
            elif field_type == 'bool':
                var = tk.BooleanVar()
                var.trace_add("write", lambda *args, v=variable, val=var: self._on_field_change(v, val))
                checkbox = ttk.Checkbutton(self.form_frame, variable=var)
                checkbox.grid(row=row, column=1, sticky=tk.W, pady=(2, 2), padx=(5, 0))
                self.form_fields[variable] = var
                self.field_widgets[variable] = checkbox 
                
            # === 5. Text (Multiline) ===
            elif field_type == 'text':
                text_frame = ttk.Frame(self.form_frame)
                text_frame.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))
                
                height = 4 if variable in ['abstract', 'notes'] else 2
                text_widget = scrolledtext.ScrolledText(text_frame, height=height, width=50, undo=True, maxundo=-1)
                text_widget.grid(row=0, column=0, sticky="nsew")
                
                text_frame.columnconfigure(0, weight=1)
                text_frame.rowconfigure(0, weight=1)
                
                self.form_fields[variable] = text_widget
                self.field_widgets[variable] = text_widget
                
                text_widget.bind("<KeyRelease>", lambda e, v=variable, w=text_widget: self._on_field_change(v, w))
                self._bind_widget_scroll_events(text_widget)
                text_widget.bind('<Control-z>', lambda e: self._on_text_undo(e))
                text_widget.bind('<Control-y>', lambda e: self._on_text_redo(e))
                
            # === 6. Default String ===
            else:
                entry = tk.Entry(self.form_frame, width=60, relief=tk.GROOVE, borderwidth=2)
                entry.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))
                
                sv = tk.StringVar()
                sv.trace_add("write", lambda *args, v=variable, w=entry: self._on_field_change(v, w))
                entry.config(textvariable=sv)
                entry.textvariable = sv
                
                entry.bind("<Enter>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
                self.form_fields[variable] = entry
                self.field_widgets[variable] = entry
            
            row += 1
        
        self.form_frame.columnconfigure(1, weight=1)

    def _import_file_asset_once(self, src_path: str, asset_type: str, field_name: str) -> str:
            """
            智能导入文件资源，避免重复导入
            Args:
                src_path: 源文件路径（绝对路径或相对路径）
                asset_type: 'figure' or 'paper'
                field_name: 'pipeline_image' or 'paper_file'
            Returns:
                相对路径字符串
            """
            # 1. 如果是相对路径且文件存在，直接返回（已经在项目中）
            if not os.path.isabs(src_path):
                rel_check = os.path.join(BASE_DIR, src_path)
                if os.path.exists(rel_check):
                    # 更新跟踪记录
                    self._imported_files[field_name] = (src_path, src_path)
                    return src_path
            
            # 2. 如果是绝对路径，检查是否已经在项目目录中
            if os.path.isabs(src_path):
                try:
                    # 尝试获取相对于项目的路径
                    rel_path = os.path.relpath(src_path, BASE_DIR).replace('\\', '/')
                    # 如果文件在项目目录内，直接使用相对路径
                    if not rel_path.startswith('..'):
                        self._imported_files[field_name] = (src_path, rel_path)
                        return rel_path
                except ValueError:
                    # 不同驱动器，无法计算相对路径
                    pass
            
            # 3. 检查是否已经导入过这个源文件 (缓存机制)
            if field_name in self._imported_files and self._imported_files[field_name]:
                cached_src, cached_dest = self._imported_files[field_name]
                # 如果源文件相同，直接返回之前的目标路径
                if cached_src == src_path:
                    return cached_dest
            
            # 4. 需要导入新文件，调用底层方法 (导入到 assets/temp/)
            rel_path = self.logic.import_file_asset(src_path, asset_type)
            if rel_path:
                # 记录导入信息
                self._imported_files[field_name] = (src_path, rel_path)
            return rel_path

    def _create_file_field_ui(self, row, variable):
        """Helper to create file fields with correct layout, scoping, and Drag-and-Drop"""
        frame = ttk.Frame(self.form_frame)
        frame.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))
        
        # 1. Entry (Left side, fill)
        entry = tk.Entry(frame)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 2. Buttons container (Right side)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.RIGHT, padx=(5, 0))
        
        sv = tk.StringVar()
        sv.trace_add("write", lambda *args, v=variable, w=entry: self._on_field_change(v, w))
        entry.config(textvariable=sv)
        entry.textvariable = sv
        
        # 拖放功能支持 (tkinterdnd2)
        def setup_drag_drop(widget):
            """设置拖放支持"""
            # 检查是否有全局拖放支持标记 (在main中初始化)
            if not hasattr(self.root, '_dnd_available'):
                # 简单检测是否是 DnD 实例
                try:
                    self.root.tk.call('package', 'require', 'tkdnd')
                    self.root._dnd_available = True
                except:
                    self.root._dnd_available = False
            
            if not getattr(self.root, '_dnd_available', False):
                self.create_tooltip(widget, "使用「📂 浏览」按钮选择文件")
                return
                
            # 拖放可用，注册目标
            try:
                from tkinterdnd2 import DND_FILES
                
                def on_drop(event):
                    """处理文件拖放"""
                    files = self.root.tk.splitlist(event.data)
                    if files:
                        file_path = files[0].strip('{}').strip('"')
                        
                        # 验证文件类型
                        if variable == 'pipeline_image':
                            valid_exts = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
                            if not file_path.lower().endswith(valid_exts):
                                messagebox.showerror("错误", "仅支持图片文件 (PNG, JPG, JPEG, GIF, BMP)")
                                return
                        elif variable == 'paper_file':
                            if not file_path.lower().endswith('.pdf'):
                                messagebox.showerror("错误", "仅支持 PDF 文件")
                                return
                        
                        # 导入文件
                        if os.path.exists(file_path):
                            asset_type = 'figure' if variable == 'pipeline_image' else 'paper'
                            rel_path = self._import_file_asset_once(file_path, asset_type, variable)
                            if rel_path:
                                sv.set(rel_path)
                        else:
                            messagebox.showerror("错误", "文件不存在")
                
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', on_drop)
                self.create_tooltip(widget, "可拖放文件到此，或使用「📂 浏览」按钮")
                
            except Exception as e:
                print(f"DnD Registration failed: {e}")
        
        # 应用拖放支持
        setup_drag_drop(entry)
        
        # FocusOut Event (手动输入路径后的处理)
        def on_focus_out(event):
            path = sv.get().strip()
            if path and os.path.isabs(path) and os.path.exists(path):
                asset_type = 'figure' if variable == 'pipeline_image' else 'paper'
                rel_path = self._import_file_asset_once(path, asset_type, variable)
                if rel_path:
                    sv.set(rel_path)
        entry.bind("<FocusOut>", on_focus_out)

        # Browse Button
        def browse_file():
            ft = [("Images", "*.png;*.jpg;*.jpeg")] if variable == 'pipeline_image' else [("PDF", "*.pdf")]
            path = filedialog.askopenfilename(filetypes=ft)
            if path:
                asset_type = 'figure' if variable == 'pipeline_image' else 'paper'
                rel_path = self._import_file_asset_once(path, asset_type, variable)
                if rel_path:
                    sv.set(rel_path)
        
        btn_browse = ttk.Button(btn_frame, text="📂", width=3, command=browse_file)
        btn_browse.pack(side=tk.LEFT, padx=1)
        
        # Reveal/Open Location (📍)
        def reveal_file():
            path = sv.get().strip()
            if not path: return
            abs_path = os.path.abspath(path) if os.path.isabs(path) else os.path.join(BASE_DIR, path)
            if not os.path.exists(abs_path):
                return messagebox.showerror("Error", "文件不存在")
            
            try:
                if sys.platform == 'win32':
                    subprocess.run(['explorer', '/select,', abs_path])
                elif sys.platform == 'darwin':
                    subprocess.run(['open', '-R', abs_path])
                else: # Linux
                    subprocess.run(['xdg-open', os.path.dirname(abs_path)])
            except Exception as e:
                messagebox.showerror("Error", f"无法定位文件: {e}")

        btn_reveal = ttk.Button(btn_frame, text="📍", width=3, command=reveal_file)
        btn_reveal.pack(side=tk.LEFT, padx=1)

        # Open (👁️)
        def open_file():
            path = sv.get().strip()
            if not path: return
            abs_path = os.path.abspath(path) if os.path.isabs(path) else os.path.join(BASE_DIR, path)
            if os.path.exists(abs_path):
                try:
                    if sys.platform == 'win32': os.startfile(abs_path)
                    elif sys.platform == 'darwin': subprocess.call(['open', abs_path])
                    else: subprocess.call(['xdg-open', abs_path])
                except: messagebox.showerror("Error", "无法打开文件")
        
        btn_open = ttk.Button(btn_frame, text="👁️", width=3, command=open_file)
        btn_open.pack(side=tk.LEFT, padx=1)

        # Paste (Image only)
        if variable == 'pipeline_image':
            def paste_img():
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grabclipboard()
                    if img:
                        import time
                        temp_path = os.path.join(BASE_DIR, f'temp_paste_{int(time.time())}.png')
                        img.save(temp_path)
                        rel_path = self._import_file_asset_once(temp_path, 'figure', variable)
                        if rel_path: sv.set(rel_path)
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    else:
                        messagebox.showinfo("Info", "剪贴板中没有图片")
                except ImportError:
                    messagebox.showerror("Error", "需要安装 Pillow 库支持粘贴: pip install Pillow")
                except Exception as ex:
                    messagebox.showerror("Error", str(ex))

            btn_paste = ttk.Button(btn_frame, text="📋", width=3, command=paste_img)
            btn_paste.pack(side=tk.LEFT, padx=1)
        
        self.form_fields[variable] = entry
        self.field_widgets[variable] = entry

    def _gui_add_category_row(self, value_display: str = ""):
        container = getattr(self, 'category_container', None)
        if container is None: return

        is_first = len(getattr(self, 'category_rows', [])) == 0
        row_frame = ttk.Frame(container)
        row_frame.pack(fill='x', pady=1)

        btn_text = '+' if is_first else '-'
        btn = ttk.Button(row_frame, text=btn_text, width=2)
        btn.pack(side='left', padx=(0, 4))

        combo = ttk.Combobox(
            row_frame, 
            state='readonly', 
            values=[cat['name'] for cat in self.config.get_active_categories()]
        )
        combo.pack(side='left', fill='x', expand=True)
        
        if value_display: combo.set(value_display)
            
        combo.bind("<<ComboboxSelected>>", lambda e: [
            self._show_category_tooltip(combo),
            self._on_category_change()
        ])
        self._bind_widget_scroll_events(combo)
        
        combo.bind("<Enter>", lambda e, c=combo: self._show_category_tooltip(c), add='+')
        combo.bind("<Leave>", lambda e: self._hide_inline_tooltip(), add='+')

        def tree_cb(c=combo):
            self.show_category_tree(target_combo=c)
            
        btn_tree = ttk.Button(row_frame, text="🌳", width=3, command=tree_cb)
        btn_tree.pack(side='left', padx=(4, 0))

        def make_button_callback(frame_ref, is_first_row):
            def on_btn_click():
                if is_first_row:
                    if len(self.category_rows) >= self._gui_category_max:
                        messagebox.showwarning('限制', f'最多只能添加 {self._gui_category_max} 个分类')
                        return
                    self._gui_add_category_row('')
                    if len(self.category_rows) >= self._gui_category_max:
                        self.category_rows[0][1].config(state='disabled')
                else:
                    try:
                        for idx, (f, b, c) in enumerate(self.category_rows):
                            if f is frame_ref:
                                f.destroy()
                                self.category_rows.pop(idx)
                                break
                        if self.category_rows and len(self.category_rows) < self._gui_category_max:
                            self.category_rows[0][1].config(state='normal')
                        self._on_category_change()
                    except Exception: pass
            return on_btn_click

        btn.config(command=make_button_callback(row_frame, is_first))
        self.category_rows.append((row_frame, btn, combo))
        
        if len(self.category_rows) >= self._gui_category_max and is_first:
            btn.config(state='disabled')

    def setup_buttons_frame(self, parent):
        """底部按钮区域"""
        buttons_frame = ttk.Frame(parent)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=(15, 10))
        
        # Group 1: Script Tools
        script_frame = ttk.LabelFrame(buttons_frame, text="Script Tools")
        script_frame.grid(row=0, column=0, padx=5, sticky="ns")
        ttk.Button(script_frame, text="🔄 运行更新", command=self.run_update_script, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(script_frame, text="✅ 运行验证", command=self.run_validate_script, width=12).pack(side=tk.LEFT, padx=5, pady=5)

        # Group 2: File Operations (增加打开数据库)
        file_frame = ttk.LabelFrame(buttons_frame, text="File Operations")
        file_frame.grid(row=0, column=1, padx=5, sticky="ns")
        
        ttk.Button(file_frame, text="💾 打开数据库", command=self._open_database_action, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(file_frame, text="📤 保存文件", command=self.save_all_papers, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(file_frame, text="📂 加载文件", command=self.load_template, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        
        if getattr(self.logic, 'pr_enabled', True):
            ttk.Button(file_frame, text="🚀 提交PR", command=self.submit_pr, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Group 3: AI Tools (增加 LabelFrame)
        ai_frame = ttk.LabelFrame(buttons_frame, text="AI Assistant")
        ai_frame.grid(row=0, column=2, padx=5, sticky="ns")
        
        self.ai_btn_var = tk.StringVar(value="🤖 AI 助手 ▾")
        ai_btn = ttk.Button(ai_frame, textvariable=self.ai_btn_var, width=15)
        ai_btn.pack(padx=5, pady=5)
        
        self.ai_menu = tk.Menu(self.root, tearoff=0)
        self.ai_menu.add_command(label="🧰 AI 工具箱", command=self.ai_toolbox_window)
        self.ai_menu.add_command(label="⚙️ AI 配置", command=self.open_ai_config_dialog)
        self.ai_menu.add_separator()
        self.ai_menu.add_command(label="✨ 生成所有空字段", command=lambda: self.run_ai_task(self.ai_generate_field, None))
        self.ai_menu.add_command(label="🏷️分类建议", command=self.ai_suggest_category)
        
        def show_ai_menu(event):
            self.ai_menu.post(event.x_root, event.y_root)
        ai_btn.bind("<Button-1>", show_ai_menu)

    # ================= 管理员逻辑 =================

    def _toggle_admin_mode(self):
        """切换管理员模式"""
        if self.logic.is_admin:
            # 退出管理员模式
            self.logic.set_admin_mode(False)
            self._update_admin_ui_state()
            self._refresh_ui_fields()
        else:
            # 进入管理员模式
            # 检查是否有密码配置
            if not self.logic.check_admin_password_configured():
                # 首次设置
                pwd = simpledialog.askstring("设置管理员密码", "首次进入管理员模式，请设置密码:", show='*')
                if pwd:
                    self.logic.set_admin_password(pwd)
                    self.logic.set_admin_mode(True)
                    self._update_admin_ui_state()
                    self._refresh_ui_fields()
            else:
                # 验证密码
                pwd = simpledialog.askstring("管理员验证", "请输入管理员密码:", show='*')
                if pwd:
                    if self.logic.verify_admin_password(pwd):
                        self.logic.set_admin_mode(True)
                        self._update_admin_ui_state()
                        self._refresh_ui_fields()
                    else:
                        messagebox.showerror("错误", "密码错误")

    def _update_admin_ui_state(self):
        """更新UI以反映管理员状态"""
        if self.logic.is_admin:
            self.admin_btn.config(text="🔓 管理员: ON")
            self.root.title("Awesome 论文提交系统 [管理员模式]")
        else:
            self.admin_btn.config(text="🔒 管理员: OFF")
            self.root.title("Awesome 论文提交系统")

    def _refresh_ui_fields(self):
        """完全重建表单字段 (根据管理员模式显示/隐藏字段)"""
        # 清除现有
        for widget in self.form_frame.winfo_children():
            widget.destroy()
        
        # 重建
        self.create_form_fields()
        
        # 重新加载当前论文（如果已选）
        if self.current_paper_index >= 0 and self.current_paper_index < len(self.filtered_indices):
            # 需要映射回真实 index
            real_idx = self.filtered_indices[self.current_paper_index]
            if 0 <= real_idx < len(self.logic.papers):
                self.load_paper_to_form(self.logic.papers[real_idx])

    # ================= 筛选与列表逻辑 =================

    def _get_search_keyword(self) -> str:
        if getattr(self, '_search_is_placeholder', False):
            return ""
        kw = self.search_var.get()
        if kw == getattr(self, '_search_placeholder', ""):
            return ""
        return kw

    def _on_search_change(self, *args):
        kw = self._get_search_keyword()
        cat = self.cat_filter_combo.get()
        self.refresh_list_view(kw, cat)


    def on_paper_selected(self, event):
        if self._suppress_select_event: return
        selection = self.paper_tree.selection()
        if not selection:
            self.current_paper_index = -1
            self.show_placeholder()
            return
        
        item = selection[0]
        values = self.paper_tree.item(item, 'values')
        
        # values[0] 是显示序号 (1-based)，转换为 0-based index
        display_index = int(values[0]) - 1
        
        if 0 <= display_index < len(self.filtered_indices):
            # 获取在 logic.papers 中的真实索引
            self.current_paper_index = display_index # 记录当前显示列表的选中索引
            real_index = self.filtered_indices[display_index]
            
            self.show_form()
            self.load_paper_to_form(self.logic.papers[real_index])
            self._validate_all_fields_visuals(real_index)
            self.update_status(f"正在编辑: {self.logic.papers[real_index].title[:30]}...")

    def load_paper_to_form(self, paper):
        self._disable_callbacks = True
        
        # 清空文件导入缓存
        self._imported_files = {'pipeline_image': None, 'paper_file': None}
        
        try:
            for variable, widget in self.form_fields.items():
                value = getattr(paper, variable, "")
                if value is None: value = ""
                
                # 记录文件字段缓存
                if variable in ['pipeline_image', 'paper_file'] and value:
                    self._imported_files[variable] = (value, value)
                
                if variable == 'category':
                    unique_names = [v.strip() for v in str(value).split(';') if v.strip()]
                    current_rows = getattr(self, 'category_rows', [])
                    needed_rows = len(unique_names) if unique_names else 1
                    while len(current_rows) < needed_rows: self._gui_add_category_row('')
                    while len(current_rows) > needed_rows: 
                        row_frame, _, _ = current_rows.pop()
                        row_frame.destroy()
                    for i in range(needed_rows):
                        uname = unique_names[i] if i < len(unique_names) else ""
                        display_name = self.category_reverse_mapping.get(uname, '')
                        _, _, combo = current_rows[i]
                        combo.set(display_name)
                
                elif isinstance(widget, ttk.Combobox): widget.set(str(value) if value else "")
                elif isinstance(widget, tk.BooleanVar): widget.set(bool(value))
                elif isinstance(widget, scrolledtext.ScrolledText):
                    widget.delete(1.0, tk.END)
                    widget.insert(1.0, str(value))
                    widget.edit_reset()
                elif isinstance(widget, tk.Entry):
                    widget.delete(0, tk.END)
                    widget.insert(0, str(value))
        finally: self._disable_callbacks = False

    def _on_field_change(self, variable, widget_or_var):
        if getattr(self, '_disable_callbacks', False): return
        if self.current_paper_index < 0: return
        
        # 获取真实论文对象
        real_idx = self.filtered_indices[self.current_paper_index]
        current_paper = self.logic.papers[real_idx]
        
        new_value = ""
        if variable == 'category': pass
        elif isinstance(widget_or_var, tk.BooleanVar): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, scrolledtext.ScrolledText): new_value = widget_or_var.get(1.0, tk.END).strip()
        elif isinstance(widget_or_var, ttk.Combobox): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, tk.Entry): new_value = widget_or_var.get()
        
        setattr(current_paper, variable, new_value)
        self._validate_single_field_visuals(variable, real_idx)
        
        if variable in ['title', 'authors']: 
            self._refresh_list_item(self.current_paper_index, current_paper)

    def _on_category_change(self, variable=None, widget_or_var=None):
        if getattr(self, '_disable_callbacks', False): return
        if self.current_paper_index < 0: return
        
        real_idx = self.filtered_indices[self.current_paper_index]
        current_paper = self.logic.papers[real_idx]
        
        unique_names = self._gui_get_category_values()
        cat_str = ";".join(unique_names)
        current_paper.category = cat_str
        
        self._validate_single_field_visuals('category', real_idx)
        # Category change doesn't update treeview column in this version, but good to have logic ready

    def _refresh_list_item(self, display_index, paper):
        """更新列表中的单项显示"""
        children = self.paper_tree.get_children()
        if display_index < len(children):
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            
            status_str = "Conflict" if paper.conflict_marker else ("New" if not paper.doi else "OK")
            tags = ('conflict',) if paper.conflict_marker else ()
            
            self.paper_tree.item(children[display_index], values=(display_index+1, title, status_str), tags=tags)

    # ================= 验证视觉效果 =================

    def _validate_single_field_visuals(self, variable, paper_idx):
        paper = self.logic.papers[paper_idx]
        # 调用 Logic 层的验证
        is_valid, _, _ = paper.validate_paper_fields(self.config, True, True, variable=variable, no_normalize=True)
        
        tag_config = self.config.get_tag_by_variable(variable)
        if not tag_config:
            for t in self.config.get_active_tags():
                if t.get('variable') == variable: tag_config = t; break
                
        is_required = tag_config.get('required', False) if tag_config else False
        val = getattr(paper, variable, "")
        is_empty = not val if variable == 'category' else (val is None or str(val).strip() == "" or str(val) == self.logic.PLACEHOLDER)
        
        self._apply_widget_style(variable, is_valid, is_required, is_empty)

    def _validate_all_fields_visuals(self, paper_idx=None):
        if paper_idx is None:
            if self.current_paper_index < 0: return
            paper_idx = self.filtered_indices[self.current_paper_index]
            
        paper = self.logic.papers[paper_idx]
        _, _, invalid_vars = paper.validate_paper_fields(self.config, True, True, no_normalize=True)
        invalid_set = set(invalid_vars)
        
        for variable in self.form_fields.keys():
            # 获取配置
            tag_config = None
            for t in self.config.get_active_tags():
                if t.get('variable') == variable: tag_config = t; break
            
            is_required = tag_config.get('required', False) if tag_config else False
            val = getattr(paper, variable, "")
            is_empty = not val if variable == 'category' else (val is None or str(val).strip() == "" or str(val) == self.logic.PLACEHOLDER)
            is_valid = (variable not in invalid_set)
            
            self._apply_widget_style(variable, is_valid, is_required, is_empty)

    def _apply_widget_style(self, variable, is_valid, is_required, is_empty):
        widget = self.field_widgets.get(variable)
        if not widget: return
        
        bg_color = self.color_normal
        if is_required and is_empty: bg_color = self.color_required_empty
        elif not is_valid and not is_empty: bg_color = self.color_invalid
        
        try:
            if isinstance(widget, scrolledtext.ScrolledText): widget.config(background=bg_color)
            elif isinstance(widget, tk.Entry): widget.config(background=bg_color)
            elif isinstance(widget, ttk.Combobox):
                style_name = "TCombobox"
                if bg_color == self.color_invalid: style_name = "Invalid.TCombobox"
                elif bg_color == self.color_required_empty: style_name = "Required.TCombobox"
                widget.configure(style=style_name)
        except: pass

    # ================= 业务操作按钮 =================

    def add_paper(self):
        self.logic.create_new_paper()
        self.refresh_list_view(self._get_search_keyword(), self.cat_filter_combo.get())
        
        # 选中最后一个
        new_display_idx = len(self.filtered_indices) - 1
        if new_display_idx >= 0:
            self.current_paper_index = new_display_idx
            self._suppress_select_event = True
            child_id = self.paper_tree.get_children()[new_display_idx]
            self.paper_tree.selection_set(child_id)
            self.paper_tree.see(child_id)
            self._suppress_select_event = False
            
            self.show_form()
            real_idx = self.filtered_indices[new_display_idx]
            self.load_paper_to_form(self.logic.papers[real_idx])
            self._validate_all_fields_visuals(real_idx)
            self.update_status("已创建新论文")

    def delete_paper(self):
        if self.current_paper_index < 0: return messagebox.showwarning("警告", "请先选择一篇论文")
        if messagebox.askyesno("确认", "确定要删除这篇论文吗？"):
            real_idx = self.filtered_indices[self.current_paper_index]
            if self.logic.delete_paper(real_idx):
                self.current_paper_index = -1
                self.refresh_list_view(self._get_search_keyword(), self.cat_filter_combo.get())
                self.show_placeholder()
                self.update_status("论文已删除")

    def clear_papers(self):
        if not self.logic.papers: return
        if messagebox.askyesno("警告", "警告！确定要清空所有论文吗？"):
            if messagebox.askyesno("警告", "二次警告！确定要清空？"):
                self.logic.clear_papers()
                self.current_paper_index = -1
                self.refresh_list_view()
                self.show_placeholder()
                self.update_status("所有论文已清空")

    def save_all_papers(self):
        if not self.logic.papers: return messagebox.showwarning("警告", "没有论文可以保存")
        
        # 1. 验证
        invalid_papers = self.logic.validate_papers_for_save()
        if invalid_papers:
            msg = "以下论文未通过验证，建议修正:\n\n" + "\n".join([f"#{i} {t[:20]}..." for i, t, e in invalid_papers[:5]])
            if not messagebox.askyesno("验证警告", msg + "\n\n是否仍要强制保存？"):
                return

        # 2. 选择路径
        initial_file = os.path.basename(self.logic.current_file_path) if self.logic.current_file_path else "submit_template.json"
        target_path = filedialog.asksaveasfilename(
            title="选择保存位置", 
            defaultextension='.json', 
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
            initialfile=initial_file,
            initialdir=BASE_DIR
        )
        if not target_path: return

        # 3. 判断是否为数据库
        is_db = self.logic._is_database_file(target_path)
        
        if is_db:
            if not self.logic.is_admin:
                return messagebox.showerror("权限错误", "写入数据库需要管理员权限。")
            if messagebox.askyesno("警告", "正在写入核心数据库！\n\n数据库模式仅支持【全量重写】。\n这将用当前列表完全覆盖数据库内容。\n\n是否继续？"):
                self.logic.save_to_file_rewrite(target_path)
                messagebox.showinfo("成功", "数据库已更新")
            return

        # 4. 普通文件：使用简单的 Yes/No/Cancel 对话框
        # Yes = 增量, No = 重写, Cancel = 取消
        choice = messagebox.askyesnocancel("选择保存模式", 
            "请选择保存模式：\n\n"
            "【是 (Yes)】：增量模式 (智能合并)\n"
            "   - 适合多人协作或追加更新。\n"
            "   - 若遇重复项，将逐一询问覆盖或跳过。\n\n"
            "【否 (No)】：重写模式 (完全覆盖)\n"
            "   - 适合完全替换目标文件内容。\n"
            "   - 当前工作区将完全覆盖目标文件。")
        
        if choice is None: return # Cancel

        try:
            if choice is False: # No -> Rewrite
                self.logic.save_to_file_rewrite(target_path)
                messagebox.showinfo("成功", "文件已重写保存")
            else: # Yes -> Incremental
                # 增量模式：检查冲突
                conflicts = self.logic.get_conflicts_for_save(target_path)
                decisions = {}
                
                if conflicts:
                    # 循环询问
                    for i, p in enumerate(conflicts):
                        msg = f"发现重复论文 ({i+1}/{len(conflicts)}):\n\n标题: {p.title}\nDOI: {p.doi}\n\n目标文件中已存在该论文。"
                        res = messagebox.askyesnocancel("处理重复", msg + "\n\n是(Yes) = 覆盖旧条目\n否(No) = 跳过 (保留旧条目)")
                        
                        if res is None: 
                            self.update_status("保存已取消")
                            return
                        
                        key = p.get_key()
                        decisions[key] = 'overwrite' if res else 'skip'
                
                self.logic.save_to_file_incremental(target_path, decisions)
                messagebox.showinfo("成功", "增量保存完成")
                
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def submit_pr(self):
        if not messagebox.askyesno("须知", f"将自动通过 PR 提交论文...\n\n1. 创建新分支\n2. 提交更新文件和 Assets 资源\n3. 推送并创建 PR"): return
        
        if not self.logic.has_update_files():
             if messagebox.askyesno("确认", "未检测到有效更新文件，是否先保存当前内容？"): 
                self.save_all_papers()
                if not self.logic.has_update_files(): return # 用户取消保存
        
        def on_status(msg): self.root.after(0, lambda: self.update_status(msg))
        def on_result(url, branch, manual):
            if manual: self.root.after(0, lambda: self.show_github_cli_guide(branch))
            else: self.root.after(0, lambda: self.show_pr_result(url))
        def on_error(msg): 
            self.root.after(0, lambda: messagebox.showerror("提交失败", msg))
            self.root.after(0, lambda: self.update_status("提交失败"))
            
        self.logic.execute_pr_submission(on_status, on_result, on_error)

    def show_github_cli_guide(self, branch): 
        messagebox.showinfo("手动创建PR指引", f"GitHub CLI 未安装或认证失败。\n\n代码已推送至分支: {branch}\n请打开 GitHub 网页手动创建 Pull Request。")
    
    def show_pr_result(self, url):
        w = tk.Toplevel(self.root); w.title("PR Result"); w.geometry("500x200")
        ttk.Label(w, text="PR 创建成功！", font=("Arial", 12, "bold")).pack(pady=10)
        entry = ttk.Entry(w, width=60)
        entry.pack(pady=5)
        entry.insert(0, url)
        entry.config(state='readonly')
        ttk.Button(w, text="复制链接", command=lambda: [self.root.clipboard_clear(), self.root.clipboard_append(url)]).pack(pady=10)

    def load_template(self):
        # 新增：确认提示
        if self.logic.papers:
            if not messagebox.askyesno("确认", "加载新文件将覆盖当前工作区。\n\n是否继续？(建议先保存)"):
                return
            
        path = filedialog.askopenfilename(title="选择文件", filetypes=[("Data", "*.json *.csv")])
        if not path: return
        
        # 权限检查：如果用户试图打开数据库文件且不是管理员
        try:
            cnt = self.logic.load_papers_from_file(path)
            self.refresh_list_view() # 刷新列表
            self.current_paper_index = -1
            self.show_placeholder()
            
            fname = os.path.basename(path)
            messagebox.showinfo("成功", f"已从 {fname} 加载 {cnt} 篇论文")
            self.update_status(f"当前文件: {fname}")
            
        except PermissionError:
            if messagebox.askyesno("需要管理员权限", "打开核心数据库文件需要管理员权限。\n\n是否立即切换模式？"):
                self._toggle_admin_mode()
                if self.logic.is_admin:
                    self.load_template() # 重试
        except Exception as e:
            messagebox.showerror("Error", f"加载失败: {e}")

    def _open_database_action(self):
        """打开数据库文件的快捷操作"""
        if self.logic.papers:
            if not messagebox.askyesno("确认", "加载新文件将覆盖当前工作区。\n\n是否继续？(建议先保存)"):
                return
            
        if not self.logic.is_admin:
            if messagebox.askyesno("权限限制", "打开核心数据库需要管理员权限。\n是否立即切换模式？"):
                self._toggle_admin_mode()
                if not self.logic.is_admin: return
        
        db_path = os.path.join(BASE_DIR, self.config.settings['paths']['database'])
        try:
            cnt = self.logic.load_papers_from_file(db_path)
            self.refresh_list_view()
            self.current_paper_index = -1
            self.show_placeholder()
            self.update_status(f"已加载数据库: {os.path.basename(db_path)}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_update_script(self):
        if messagebox.askyesno("Run Update", "将合并更新文件到数据库并生成 README。\n此操作会修改核心数据库。\n\n是否继续？"):
            cmd = [sys.executable, os.path.join(BASE_DIR, "src/update.py")]
            # 使用 Popen 不阻塞 GUI，但无法实时获取输出到 status bar (为了简单)
            # 或者使用 invoke 方式
            try:
                subprocess.Popen(cmd, cwd=BASE_DIR)
                self.update_status("正在后台运行更新脚本...")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def run_validate_script(self):
        cmd = [sys.executable, os.path.join(BASE_DIR, "src/validate.py")]
        try:
            # 开启新窗口运行以便查看输出
            if sys.platform == 'win32':
                subprocess.Popen(cmd, cwd=BASE_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(cmd, cwd=BASE_DIR)
            self.update_status("已启动验证脚本...")
        except Exception as e:
            messagebox.showerror("Error", str(e))




    def fill_from_zotero_meta(self):
        if self.current_paper_index < 0: return messagebox.showwarning("提示", "请先选择论文")
        s = self._show_zotero_input_dialog("填充表单")
        if not s: return
        new_p = self.logic.process_zotero_json(s)
        if not new_p: return messagebox.showwarning("提示", "无有效数据")
        
        real_idx = self.filtered_indices[self.current_paper_index]
        conflicts, updates = self.logic.get_zotero_fill_updates(new_p[0], real_idx)
        
        if not updates: return messagebox.showinfo("提示", "Zotero数据中没有有效内容可填充")
        
        overwrite = True
        if conflicts:
            msg = f"检测到 {len(conflicts)} 个字段已有内容（如 {conflicts[0]} 等）。\n\n是否覆盖已有内容？\n\n是(Yes): 覆盖所有字段\n否(No): 仅填充空白字段 (保留已有内容)\n取消(Cancel): 取消操作"
            res = messagebox.askyesnocancel("覆盖确认", msg)
            if res is None: return
            overwrite = res
        
        cnt = self.logic.apply_paper_updates(real_idx, updates, overwrite)
        self.load_paper_to_form(self.logic.papers[real_idx])
        self.update_status(f"已从Zotero数据更新 {cnt} 个字段")

    def _show_zotero_input_dialog(self, title):
        d = tk.Toplevel(self.root); d.title(title); d.geometry("600x400")
        ttk.Label(d, text="请粘贴Zotero导出的元数据JSON (支持单个对象或列表):", padding=10).pack()
        t = scrolledtext.ScrolledText(d, height=15); t.pack(fill=tk.BOTH, expand=True, padx=10)
        res = {"d":None}
        def ok(): 
            val = t.get("1.0", tk.END).strip()
            if not val: return messagebox.showwarning("提示", "输入内容为空", parent=d)
            res['d'] = val; d.destroy()
        
        btn_frame = ttk.Frame(d)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="✅ 确定", command=ok).pack(side=tk.LEFT, padx=5)
        
        self.root.wait_window(d)
        return res['d']

    def ai_toolbox_window(self):
        self.ai_toolbox_window_impl()

    def ai_toolbox_window_impl(self):
        if self.current_paper_index < 0:
            messagebox.showwarning("Warning", "请先选择一篇论文")
            return

        if hasattr(self, '_ai_toolbox') and self._ai_toolbox.winfo_exists():
            self._ai_toolbox.lift()
            return

        menu_win = tk.Toplevel(self.root)
        self._ai_toolbox = menu_win
        menu_win.title("AI 工具箱")
        menu_win.geometry("260x420")
        
        # 保持与 Part 1 中按钮逻辑一致，复用 run_ai_task
        ttk.Button(menu_win, text="🏷️分类建议", command=self.ai_suggest_category).pack(fill=tk.X, padx=10, pady=(10, 2))
        ttk.Separator(menu_win, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        
        gen_frame = ttk.LabelFrame(menu_win, text="字段生成", padding=5)
        gen_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(gen_frame, text="✨ 所有空字段", 
                   command=lambda: self.run_ai_task(self.ai_generate_field, None)).pack(fill=tk.X, pady=3)
        
        fields = [
            ('title_translation', '标题翻译'),
            ('analogy_summary', '类比总结'),
            ('summary_motivation', '动机'),
            ('summary_innovation', '创新点'),
            ('summary_method', '方法'),
            ('summary_conclusion', '结论'),
            ('summary_limitation', '局限性')
        ]
        
        for var, label in fields:
            ttk.Button(gen_frame, text=f"生成 {label}", 
                       command=lambda v=var: self.run_ai_task(self.ai_generate_field, v)).pack(fill=tk.X, pady=1)
            
    def run_ai_task(self, target_func, *args):
        """通用AI异步执行器"""
        if self.current_paper_index < 0:
            messagebox.showwarning("Warning", "请先选择一篇论文")
            return
            
        self.update_status("🤖 AI 正在处理中，请稍候...")
        
        # 并发修复: 启动任务前强制保存当前UI状态到 Paper 对象
        self.save_current_ui_to_paper()
        
        def task_thread():
            try:
                target_func(*args)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("AI Error", str(e)))
                self.root.after(0, lambda: self.update_status("AI 处理出错"))
        
        threading.Thread(target=task_thread, daemon=True).start()

    def save_current_ui_to_paper(self):
        """强制将当前UI值写回Paper对象 (供AI任务前调用)"""
        if self.current_paper_index < 0: return
        paper = self.logic.papers[self.current_paper_index]
        
        for var, widget in self.form_fields.items():
            if var in ['category', 'pipeline_image', 'paper_file']: continue 
            
            val = None
            if isinstance(widget, tk.Entry): val = widget.get()
            elif isinstance(widget, scrolledtext.ScrolledText): val = widget.get("1.0", "end-1c")
            elif isinstance(widget, ttk.Combobox): val = widget.get()
            elif isinstance(widget, tk.BooleanVar): val = widget.get()
            
            if val is not None:
                setattr(paper, var, val)

    def ai_generate_field(self, target_field=None):
        """执行AI生成 (需在线程中运行)"""
        idx = self.current_paper_index
        # 获取 Paper 引用 (内容已被 save_current_ui_to_paper 更新)
        paper_ref = self.logic.papers[idx]
        
        paper_text = ""
        if paper_ref.paper_file:
            abs_path = os.path.join(BASE_DIR, paper_ref.paper_file)
            gen_reader = AIGenerator()
            paper_text = gen_reader.read_paper_file(abs_path)
            
        gen = AIGenerator()
        fields_to_gen = [target_field] if target_field else None
        
        # 1. 仅生成内容，不直接覆盖 Paper 对象（避免并发冲突）
        temp_paper, changed = gen.enhance_paper_with_ai(paper_ref, paper_text, fields_to_gen)
        
        # 2. 提取生成的字段值
        generated_data = {}
        if changed:
            check_fields = fields_to_gen if fields_to_gen else [
                'title_translation', 'analogy_summary', 'summary_motivation', 
                'summary_innovation', 'summary_method', 'summary_conclusion', 'summary_limitation'
            ]
            for f in check_fields:
                new_val = getattr(temp_paper, f)
                if new_val:
                    generated_data[f] = new_val

        def update_ui_callback():
            if generated_data:
                # 3. 在主线程中，更新当前的 Paper 对象
                # 注意：此时 self.logic.papers[idx] 可能已经被用户修改了其他字段
                # 我们只更新 AI 生成的那些字段
                live_paper = self.logic.papers[idx]
                for f, v in generated_data.items():
                    setattr(live_paper, f, v)
                
                # 4. 如果当前界面还停留在该论文，刷新UI显示
                if self.current_paper_index == idx:
                    self.load_paper_to_form(live_paper)
                
                field_name = target_field if target_field else "所有空字段"
                self.update_status(f"AI 生成完成: {field_name}")
            else:
                self.update_status("没有生成新内容 (或内容未变)")

        self.root.after(0, update_ui_callback)

    def _set_window_ontop(self, win):
        """Helper to keep secondary windows usable"""
        win.transient(self.root)
        win.lift()

    def open_ai_config_dialog(self):
        """AI 配置窗口 (单例、密钥池同步、明文存储)"""
        if hasattr(self, '_ai_config_win') and self._ai_config_win.winfo_exists():
            self._ai_config_win.lift()
            return

        win = tk.Toplevel(self.root)
        self._ai_config_win = win
        win.title("AI 配置管理")
        win.geometry("600x600")
        self._set_window_ontop(win)
        
        gen = AIGenerator()
        
        # --- Top: Global Settings ---
        global_frame = ttk.LabelFrame(win, text="全局设置", padding=10)
        global_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(global_frame, text="全局密钥池路径 (Key Pool):").grid(row=0, column=0, sticky="w")
        
        key_pool_frame = ttk.Frame(global_frame)
        key_pool_frame.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        
        key_pool_entry = tk.Entry(key_pool_frame)
        key_pool_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        current_pool = self.config.settings['ai'].get('key_path', '')
        key_pool_entry.insert(0, current_pool)
        
        def browse_pool():
            path = filedialog.askopenfilename(title="选择密钥文件(.txt)")
            if not path:
                if messagebox.askyesno("文件不存在", "未选择文件。是否创建新的密钥池文件？"):
                    path = filedialog.asksaveasfilename(title="创建密钥池文件", defaultextension=".txt")
                    if path:
                        with open(path, 'w', encoding='utf-8') as f: f.write("")
            if path:
                try:
                    rel = os.path.relpath(path, BASE_DIR)
                    if not rel.startswith(".."): path = rel
                except: pass
                key_pool_entry.delete(0, tk.END)
                key_pool_entry.insert(0, path)
        
        ttk.Button(key_pool_frame, text="📂", width=3, command=browse_pool).pack(side=tk.LEFT, padx=2)
        
        def save_global_path():
            path = key_pool_entry.get().strip()
            if path:
                # 仅保存 key_path
                profiles = gen.get_all_profiles()
                active = gen.active_profile_name
                enable = self.config.settings['ai'].get('enable_ai_generation') == 'true'
                gen.save_profiles(profiles, enable, active, path)
                messagebox.showinfo("OK", "全局路径已保存")

        ttk.Button(key_pool_frame, text="💾 保存设置", width=10, command=save_global_path).pack(side=tk.LEFT, padx=5)
        global_frame.columnconfigure(0, weight=1)

        # --- Middle: Profile List ---
        list_frame = ttk.Frame(win, padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("Name", "Provider", "Model", "Key Status")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=6)
        for c in columns: tree.heading(c, text=c)
        tree.column("Name", width=100)
        tree.column("Provider", width=80)
        tree.column("Model", width=120)
        tree.column("Key Status", width=100)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Bottom: Edit Profile ---
        edit_frame = ttk.LabelFrame(win, text="编辑配置", padding=10)
        edit_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Row 0: Name (Cross)
        ttk.Label(edit_frame, text="配置名称:").grid(row=0, column=0, sticky="e")
        name_entry = tk.Entry(edit_frame)
        name_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=5)
        
        # Row 1: Provider & Model
        ttk.Label(edit_frame, text="服务商:").grid(row=1, column=0, sticky="e")
        provider_cb = ttk.Combobox(edit_frame, values=[p["provider"] for p in PROVIDER_CONFIGS], state="readonly")
        provider_cb.grid(row=1, column=1, sticky="ew", padx=5)
        
        ttk.Label(edit_frame, text="模型名称:").grid(row=1, column=2, sticky="e")
        model_cb = ttk.Combobox(edit_frame) 
        model_cb.grid(row=1, column=3, sticky="ew", padx=5)
        
        # Row 2: Base URL & API Key
        ttk.Label(edit_frame, text="Base URL:").grid(row=2, column=0, sticky="e")
        url_entry = tk.Entry(edit_frame)
        url_entry.grid(row=2, column=1, sticky="ew", padx=5)
        
        ttk.Label(edit_frame, text="API Key:").grid(row=2, column=2, sticky="e")
        key_entry = tk.Entry(edit_frame, show="*") 
        key_entry.grid(row=2, column=3, sticky="ew", padx=5)
        self.create_tooltip(key_entry, "Key将写入密钥池文件，不保存在Config中")

        edit_frame.columnconfigure(1, weight=1)
        edit_frame.columnconfigure(3, weight=1)

        # --- Helpers for Key Pool Management ---
        def get_pool_keys() -> List[str]:
            path = key_pool_entry.get().strip()
            abs_path = os.path.abspath(path) if os.path.isabs(path) else os.path.join(BASE_DIR, path)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        return [line.strip() for line in f.readlines()]
                except: return []
            return []

        def save_pool_keys(keys: List[str]):
            path = key_pool_entry.get().strip()
            abs_path = os.path.abspath(path) if os.path.isabs(path) else os.path.join(BASE_DIR, path)
            try:
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(keys))
            except Exception as e:
                messagebox.showerror("Error", f"无法写入密钥池: {e}")

        # Logic
        def on_provider_change(event):
            prov = provider_cb.get()
            defaults = gen.get_provider_defaults(prov)
            url_entry.delete(0, tk.END)
            url_entry.insert(0, defaults.get('api_url', ''))
            models = defaults.get('models', [])
            model_cb['values'] = models
            if models: model_cb.set(models[0])
            else: model_cb.set('')
            
        provider_cb.bind("<<ComboboxSelected>>", on_provider_change)

        def refresh_list():
            for item in tree.get_children(): tree.delete(item)
            profiles = gen.get_all_profiles()
            active = gen.active_profile_name
            pool_keys = get_pool_keys()
            
            for i, p in enumerate(profiles):
                d_name = p['name'] + (" (当前)" if p['name'] == active else "")
                status = "✅ Present" if i < len(pool_keys) and pool_keys[i] else "⚠️ Empty"
                tree.insert("", "end", values=(d_name, p.get('provider'), p.get('model'), status), tags=(p['name'],))

        def load_selection(event):
            sel = tree.selection()
            if not sel: return
            real_name = tree.item(sel[0])['tags'][0]
            p = gen.get_profile(real_name)
            if p:
                provider_cb.set(p.get('provider', ''))
                name_entry.delete(0, tk.END); name_entry.insert(0, p.get('name', ''))
                
                defaults = gen.get_provider_defaults(p.get('provider', ''))
                model_cb['values'] = defaults.get('models', [])
                model_cb.set(p.get('model', ''))
                
                url_entry.delete(0, tk.END); url_entry.insert(0, p.get('api_url', ''))
                
                # Load Key from Pool for display (Masked)
                idx = gen.get_profile_index(real_name)
                pool_keys = get_pool_keys()
                key_entry.delete(0, tk.END)
                if idx < len(pool_keys):
                    key_entry.insert(0, pool_keys[idx])

        tree.bind("<<TreeviewSelect>>", load_selection)

        def perform_save_logic(set_active=False):
            name = name_entry.get().strip()
            if not name: return messagebox.showwarning("Err", "Name required")
            
            profiles = gen.get_all_profiles()
            pool_keys = get_pool_keys()
            
            # Find index
            idx = next((i for i, p in enumerate(profiles) if p['name'] == name), -1)
            is_new = (idx == -1)
            
            if is_new:
                idx = len(profiles)
                profiles.append({}) # Placeholder
                while len(pool_keys) < len(profiles): pool_keys.append("")
            
            # Update Profile Data (Source always empty/index-based)
            profiles[idx] = {
                "name": name,
                "provider": provider_cb.get(),
                "model": model_cb.get(),
                "api_url": url_entry.get().strip(),
                "api_key_source": "" 
            }
            
            # Update Key Pool
            new_key = key_entry.get().strip()
            while len(pool_keys) <= idx: pool_keys.append("")
            pool_keys[idx] = new_key
            
            save_pool_keys(pool_keys)
            
            new_active = name if set_active else gen.active_profile_name
            current_enable = self.config.settings['ai'].get('enable_ai_generation') == 'true'
            gen.save_profiles(profiles, current_enable, new_active, key_pool_entry.get().strip())
            
            refresh_list()
            messagebox.showinfo("OK", f"配置 '{name}' 已保存")

        def delete_logic():
            sel = tree.selection()
            if not sel: return
            real_name = tree.item(sel[0])['tags'][0]
            if messagebox.askyesno("Delete", f"确定删除配置 {real_name}? (对应Key也会被移除)"):
                profiles = gen.get_all_profiles()
                idx = next((i for i, p in enumerate(profiles) if p['name'] == real_name), -1)
                
                if idx != -1:
                    pool_keys = get_pool_keys()
                    
                    # Remove from profiles
                    del profiles[idx]
                    # Remove from keys if exists
                    if idx < len(pool_keys):
                        del pool_keys[idx]
                        save_pool_keys(pool_keys)
                    
                    new_active = gen.active_profile_name
                    if real_name == new_active:
                        new_active = profiles[0]['name'] if profiles else ""
                    
                    current_enable = self.config.settings['ai'].get('enable_ai_generation') == 'true'
                    gen.save_profiles(profiles, current_enable, new_active, key_pool_entry.get().strip())
                    
                    # Clear inputs
                    name_entry.delete(0, tk.END)
                    key_entry.delete(0, tk.END)
                    refresh_list()

        def set_active_only():
            sel = tree.selection()
            if not sel: return
            real_name = tree.item(sel[0])['tags'][0]
            current_enable = self.config.settings['ai'].get('enable_ai_generation') == 'true'
            gen.save_profiles(gen.get_all_profiles(), current_enable, real_name, key_pool_entry.get().strip())
            refresh_list()

        def add_new():
            name_entry.delete(0, tk.END); name_entry.insert(0, "New Profile")
            key_entry.delete(0, tk.END)
            provider_cb.set('deepseek')
            provider_cb.event_generate("<<ComboboxSelected>>")

        # Buttons
        btn_frame = ttk.Frame(win, padding=10)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="✅ 设为当前", command=set_active_only).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="➕ 添加配置", command=add_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑️ 删除配置", command=delete_logic).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="💾 保存并选中", command=lambda: perform_save_logic(True)).pack(side=tk.RIGHT, padx=5)
        
        refresh_list()

    def show_category_tree(self, target_combo=None):
        """显示分类树结构，双击填充"""
        win = tk.Toplevel(self.root)
        win.title("分类结构")
        win.geometry("600x600")
        self._set_window_ontop(win)
        
        # 创建主框架
        main_frame = ttk.Frame(win)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建树视图
        tree = ttk.Treeview(main_frame, columns=("ID", "Desc"), show="tree headings")
        tree.heading("#0", text="Name")
        tree.heading("ID", text="Unique Name")
        tree.heading("Desc", text="Description")
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        cats = self.config.get_active_categories()
        parents = {c['unique_name']: c for c in cats if not c.get('primary_category')}
        children = {}
        for c in cats:
            p = c.get('primary_category')
            if p:
                children.setdefault(p, []).append(c)
        
        for pid, p in parents.items():
            node = tree.insert("", "end", text=p['name'], values=(p['unique_name'], p.get('description','')))
            for c in children.get(pid, []):
                tree.insert(node, "end", text=c['name'], values=(c['unique_name'], c.get('description','')))

        def on_double_click(event):
            if not target_combo: return
            try:
                item_id = tree.selection()[0]
                cat_name = tree.item(item_id, "text")
                if cat_name:
                    target_combo.set(cat_name)
                    target_combo.event_generate("<<ComboboxSelected>>")
                    win.destroy()
            except IndexError: pass

        def copy_tree_structure():
            """复制分类树结构到剪贴板"""
            try:
                text_lines = []
                
                # 遍历所有父分类
                for pid, p in sorted(parents.items()):
                    # 添加父分类
                    text_lines.append(f"{p['name']}")
                    text_lines.append(f"Unique Name: {p['unique_name']}")
                    if p.get('description'):
                        text_lines.append(f"Description: {p.get('description')}")
                    text_lines.append("")
                    
                    # 添加子分类
                    child_list = children.get(pid, [])
                    if child_list:
                        for c in child_list:
                            text_lines.append(f"└── {c['name']}")
                            text_lines.append(f"     Unique Name: {c['unique_name']}")
                            if c.get('description'):
                                text_lines.append(f"     Description: {c.get('description')}")
                            text_lines.append("")
                
                
                # 将文本复制到剪贴板
                result_text = "\n".join(text_lines)
                win.clipboard_clear()
                win.clipboard_append(result_text)
                win.update()  # 确保剪贴板更新
                
                messagebox.showinfo("成功", "分类树结构已复制到剪贴板！", parent=win)
            except Exception as e:
                messagebox.showerror("错误", f"复制失败: {str(e)}", parent=win)

        # 创建按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 添加复制按钮
        copy_button = ttk.Button(button_frame, text="📋 复制结构到剪贴板", command=copy_tree_structure)
        copy_button.pack(side=tk.LEFT, padx=5)

        if target_combo:
            tree.bind("<Double-1>", on_double_click)
            hint_label = ttk.Label(button_frame, text="双击分类以填充", foreground="blue")
            hint_label.pack(side=tk.LEFT, padx=10)

    def _bind_widget_scroll_events(self, widget):
        widget.bind("<Enter>", lambda e: self._unbind_global_scroll())
        widget.bind("<Leave>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
        pass

    def ai_suggest_category(self):
        self.run_ai_task(self._ai_suggest_category_task)

    def _ai_suggest_category_task(self):
        idx = self.current_paper_index
        if idx < 0: return
        paper = self.logic.papers[idx]
        paper_text = ""
        if paper.paper_file:
             paper_text = AIGenerator().read_paper_file(os.path.join(BASE_DIR, paper.paper_file))
        gen = AIGenerator()
        cat, reasoning = gen.generate_category(paper, paper_text)
        
        def update_ui():
            self.update_status("AI 分类建议已就绪")
            msg = f"AI Suggested: {cat}\n\nReasoning:\n{reasoning}"
            if messagebox.askyesno("AI Category", msg + "\n\nAccept suggestion?"):
                if cat:
                    paper.category = cat
                    self.load_paper_to_form(paper)
        self.root.after(0, update_ui)

    def _gui_clear_category_rows(self):
        try:
            for frame, btn, combo in getattr(self, 'category_rows', []): frame.destroy()
        except Exception: pass
        self.category_rows = []

    def _show_inline_tooltip(self, widget, text):
        try: self._hide_inline_tooltip()
        except Exception: pass
        try:
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            ttk.Label(tip, text=text, background="#ffffe0", relief="solid", borderwidth=1, padding=5).pack()
            self._inline_tooltip = tip
            try:
                if hasattr(self, '_inline_tooltip_after_id') and self._inline_tooltip_after_id:
                    self.root.after_cancel(self._inline_tooltip_after_id)
                self._inline_tooltip_after_id = self.root.after(1500, self._hide_inline_tooltip)
            except Exception: self._inline_tooltip_after_id = None
        except Exception: self._inline_tooltip = None

    def _hide_inline_tooltip(self):
        try:
            tip = getattr(self, '_inline_tooltip', None)
            if tip: tip.destroy()
            aid = getattr(self, '_inline_tooltip_after_id', None)
            if aid: self.root.after_cancel(aid)
        finally: self._inline_tooltip = None

    def _show_category_tooltip(self, combo_widget):
        try:
            name = combo_widget.get().strip()
            if not name: return
            desc = getattr(self, 'category_description_mapping', {}).get(name, '')
            if desc: self._show_inline_tooltip(combo_widget, desc)
        except Exception: return

    def _gui_get_category_values(self) -> List[str]:
        values = []
        for frame, btn, combo in getattr(self, 'category_rows', []):
            display_name = combo.get().strip()
            if display_name:
                unique_name = self.category_mapping.get(display_name, display_name)
                if unique_name: values.append(unique_name)
        return values

    def _bind_global_scroll(self, target_scroll_func):
        self._unbind_global_scroll()
        def _on_mousewheel(event):
            try:
                if event.widget.winfo_class() == 'TCombobox': return "break"
            except Exception: pass
            try:
                delta = int(-1 * (event.delta / 120)) if hasattr(event, 'delta') else (1 if getattr(event, 'num', 5) == 5 else -1)
                if delta == 0: delta = -1 if event.delta > 0 else 1
                target_scroll_func(delta, 'units')
                return "break"
            except Exception: return
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self.root.bind_all("<Button-4>", _on_mousewheel)
        self.root.bind_all("<Button-5>", _on_mousewheel)

    def _unbind_global_scroll(self):
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")

    def create_tooltip(self, widget, text):
        def enter(event):
            x, y = widget.winfo_rootx() + 20, widget.winfo_rooty() + 20
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            ttk.Label(self.tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1, padding=5).pack()
        def leave(event):
            if getattr(self, 'tooltip', None):
                self.tooltip.destroy()
                self.tooltip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def setup_status_bar(self, parent):
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(parent, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=4, column=0, columnspan=2, sticky="we", pady=(5, 0))

    def update_status(self, message):
        self.status_var.set(message)
        self.root.update_idletasks()

    def show_placeholder(self):
        self.form_container.grid_forget()
        self.placeholder_label.grid(row=0, column=0, sticky="nsew")

    def show_form(self):
        self.placeholder_label.grid_forget()
        self.form_container.grid(row=0, column=0, sticky="nsew")
        self.root.update_idletasks()
        current_width = self.form_canvas.winfo_width()
        if current_width > 1:
             self.form_canvas.itemconfig(self.form_canvas_window, width=current_width)
        self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))
        self.form_canvas.xview_moveto(0)
        self.form_canvas.yview_moveto(0)
    
    def update_paper_list(self):
        """兼容旧调用的包装器"""
        self.refresh_list_view(self._get_search_keyword(), self.cat_filter_combo.get())

    def refresh_list_view(self, keyword="", category=""):
        """根据搜索条件刷新列表 (修复列数据对应)"""
        # 1. 获取筛选后的索引
        self.filtered_indices = self.logic.filter_papers(keyword, category)
        
        # 2. 清空列表
        for item in self.paper_tree.get_children():
            self.paper_tree.delete(item)
            
        # 3. 填充列表
        for display_i, real_idx in enumerate(self.filtered_indices):
            paper = self.logic.papers[real_idx]
            
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            
            # 状态显示
            status_str = ""
            if paper.conflict_marker:
                status_str = "Conflict"
            elif not paper.doi:
                status_str = "New"
            else:
                status_str = "OK"
            
            tags = ('conflict',) if paper.conflict_marker else ()
            
            # 修复：values 必须与 columns=("ID", "Title", "Status") 对应
            self.paper_tree.insert("", "end", iid=str(real_idx), values=(display_i + 1, title, status_str), tags=tags)
        
        # 恢复选中状态
        if self.current_paper_index >= 0 and self.current_paper_index < len(self.filtered_indices):
             # 这里逻辑有点复杂，简化为如果不匹配则重置
             pass
        else:
             self.current_paper_index = -1
             self.show_placeholder()


    # ================= 右键菜单功能 =================

    def _show_context_menu(self, event):
        item_id = self.paper_tree.identify_row(event.y)
        if not item_id: return
        
        self.paper_tree.selection_set(item_id)
        # item_id 是 real_index (str)
        real_idx = int(item_id)
        paper = self.logic.papers[real_idx]
        
        menu = tk.Menu(self.root, tearoff=0)
        
        # 通用功能
        menu.add_command(label="📄 拷贝条目", command=lambda: self._action_duplicate(real_idx))
        
        # 冲突项特有功能
        if paper.conflict_marker:
            menu.add_separator()
            menu.add_command(label="⚔️ 处理冲突...", command=lambda: self._open_conflict_resolution_dialog(real_idx))
            
            base_idx = self.logic.find_base_paper_index(real_idx)
            if base_idx != -1:
                menu.add_command(label="🔗 转到基论文", command=lambda: self._highlight_paper(base_idx))
            else:
                menu.add_command(label="⚠️ 未找到基论文", state="disabled")
        
        menu.post(event.x_root, event.y_root)

    def _action_duplicate(self, index):
        new_idx = self.logic.duplicate_paper(index)
        self.refresh_list_view(self._get_search_keyword(), self.cat_filter_combo.get())
        self._highlight_paper(new_idx)
        self.update_status("条目已拷贝")

    def _highlight_paper(self, real_idx):
        """在列表中高亮显示指定真实索引的论文"""
        # 检查该 real_idx 是否在当前筛选视图中
        if real_idx in self.filtered_indices:
            # 找到对应的 display index
            display_idx = self.filtered_indices.index(real_idx)
            self.current_paper_index = display_idx
            
            # Treeview操作
            if self.paper_tree.exists(str(real_idx)):
                self.paper_tree.selection_set(str(real_idx))
                self.paper_tree.see(str(real_idx))
                
            # 加载表单
            self.show_form()
            self.load_paper_to_form(self.logic.papers[real_idx])
        else:
            messagebox.showinfo("提示", "目标论文不在当前筛选视图中，请清除搜索条件。")

    # ================= 冲突处理窗口 (新功能) =================

    def _open_conflict_resolution_dialog(self, conflict_idx):
        base_idx = self.logic.find_base_paper_index(conflict_idx)
        if base_idx == -1:
            messagebox.showerror("错误", "无法找到对应的基论文。")
            return

        base_paper = self.logic.papers[base_idx]
        conflict_paper = self.logic.papers[conflict_idx]

        win = tk.Toplevel(self.root)
        win.title(f"冲突处理")
        win.geometry("1100x700")
        win.transient(self.root)
        win.grab_set()

        # 1. 顶部说明
        top_frame = ttk.Frame(win, padding=5)
        top_frame.pack(fill=tk.X)
        ttk.Label(top_frame, text="提示：对比两栏内容，勾选要保留的版本。可直接在文本框中修改最终结果。", font=("Arial", 9), foreground="gray").pack()

        # 标题行
        header_frame = ttk.Frame(win)
        header_frame.pack(fill=tk.X, padx=25, pady=5)
        header_frame.columnconfigure(2, weight=1)
        header_frame.columnconfigure(5, weight=1) # Widget Col is 5
        
        h_font = ("Arial", 10, "bold")
        
        ttk.Label(header_frame, text="字段名", width=15, font=h_font).grid(row=0, column=0, sticky="w")
        ttk.Label(header_frame, text="  ", width=4).grid(row=0, column=1) 
        ttk.Label(header_frame, text="基论文 (保留)", foreground="blue", font=h_font).grid(row=0, column=2, sticky="w")
        ttk.Label(header_frame, text="", width=2).grid(row=0, column=3) 
        ttk.Label(header_frame, text="  ", width=4).grid(row=0, column=4) # Checkbox Col
        ttk.Label(header_frame, text="冲突/新论文 (删除)", foreground="red", font=h_font).grid(row=0, column=5, sticky="w")

        # 2. 滚动区域
        canvas_frame = ttk.Frame(win)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas = tk.Canvas(canvas_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.columnconfigure(2, weight=1)
        scroll_frame.columnconfigure(5, weight=1) # Widget Col is 5

        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)

        scroll_frame.bind("<Configure>", configure_scroll_region)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 智能滚动
        def _smart_mousewheel(event):
            try:
                widget_under_mouse = win.winfo_containing(event.x_root, event.y_root)
                if widget_under_mouse and "text" in widget_under_mouse.winfo_class().lower():
                    return 
            except: pass
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        win.bind_all("<MouseWheel>", _smart_mousewheel)
        win.bind("<Destroy>", lambda e: win.unbind_all("<MouseWheel>"))

        # 3. 字段生成
        self.conflict_ui_data = {} 
        tags = self.config.get_non_system_tags()
        row = 0
        
        for tag in tags:
            field = tag['variable']
            name = tag['display_name']
            ftype = tag.get('type', 'string')
            
            val_base = getattr(base_paper, field, "")
            val_conflict = getattr(conflict_paper, field, "")
            is_diff = str(val_base) != str(val_conflict)
            bg_color = "#FFF5F5" if is_diff else "#FFFFFF"
            
            # Label
            lbl = tk.Label(scroll_frame, text=name, width=15, anchor="e", bg=bg_color, font=("Arial", 9))
            lbl.grid(row=row, column=0, sticky="nsew", padx=1, pady=1)
            
            choice_var = tk.IntVar(value=0)
            if not val_base and val_conflict: choice_var.set(1)
            self.conflict_ui_data[field] = {'var': choice_var, 'type': ftype}

            # Base Side
            rb1 = tk.Radiobutton(scroll_frame, variable=choice_var, value=0, bg=bg_color)
            rb1.grid(row=row, column=1, sticky="nsew", pady=1)
            
            if ftype == 'text':
                wb = scrolledtext.ScrolledText(scroll_frame, height=4, width=30, font=("Arial", 9))
                wb.insert(1.0, str(val_base))
            else:
                wb = tk.Entry(scroll_frame, font=("Arial", 9), relief="flat", bg="white")
                wb.insert(0, str(val_base))
            wb.grid(row=row, column=2, sticky="nsew", pady=1, padx=2)
            self.conflict_ui_data[field]['w_base'] = wb
            
            # Separator
            line = tk.Frame(scroll_frame, width=2, bg="#cccccc")
            line.grid(row=row, column=3, sticky="ns", pady=1)
            
            # Conflict Side (复选框在前)
            rb2 = tk.Radiobutton(scroll_frame, variable=choice_var, value=1, bg=bg_color)
            rb2.grid(row=row, column=4, sticky="nsew", pady=1)
            
            if ftype == 'text':
                wc = scrolledtext.ScrolledText(scroll_frame, height=4, width=30, font=("Arial", 9))
                wc.insert(1.0, str(val_conflict))
            else:
                wc = tk.Entry(scroll_frame, font=("Arial", 9), relief="flat", bg="white")
                wc.insert(0, str(val_conflict))
            wc.grid(row=row, column=5, sticky="nsew", pady=1, padx=2)
            self.conflict_ui_data[field]['w_conflict'] = wc

            row += 1

        # 4. 底部按钮
        btm_frame = ttk.Frame(win, padding=5)
        btm_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def select_all(val):
            for data in self.conflict_ui_data.values():
                data['var'].set(val)
        
        ttk.Button(btm_frame, text="全选左侧 (基论文)", command=lambda: select_all(0)).pack(side=tk.LEFT)
        ttk.Button(btm_frame, text="全选右侧 (新论文)", command=lambda: select_all(1)).pack(side=tk.LEFT, padx=10)
        
        def on_confirm():
            final_data = {}
            for field, data in self.conflict_ui_data.items():
                choice = data['var'].get()
                widget = data['w_conflict'] if choice == 1 else data['w_base']
                
                if data['type'] == 'text':
                    val = widget.get("1.0", "end-1c").strip()
                else:
                    val = widget.get().strip()
                final_data[field] = val
                
            if messagebox.askyesno("确认", "确定应用合并并删除冲突条目吗？"):
                self.logic.merge_papers_custom(base_idx, conflict_idx, final_data)
                win.destroy()
                self.refresh_list_view(self._get_search_keyword(), self.cat_filter_combo.get())
                
                new_base_idx = base_idx if base_idx < conflict_idx else base_idx - 1
                self._highlight_paper(new_base_idx)
                self.update_status("冲突处理完成")

        ttk.Button(btm_frame, text="✅ 确认合并", command=on_confirm, width=20).pack(side=tk.RIGHT)


    # ================= 拖拽排序功能 (修改：增加跟随窗口) =================

    def _on_drag_start(self, event):
        if self._get_search_keyword() or self.cat_filter_combo.get() != "All Categories": return
        item = self.paper_tree.identify_row(event.y)
        if item:
            self.drag_item = item
            # 获取显示文本
            item_text = self.paper_tree.item(item, "values")[1] # Title
            self._create_drag_ghost(item_text)

    def _create_drag_ghost(self, text):
        if hasattr(self, 'drag_ghost') and self.drag_ghost:
            self.drag_ghost.destroy()
        
        self.drag_ghost = tk.Toplevel(self.root)
        self.drag_ghost.overrideredirect(True) # 无边框
        self.drag_ghost.attributes('-alpha', 0.8) # 半透明
        self.drag_ghost.attributes('-topmost', True)
        
        label = tk.Label(self.drag_ghost, text=text[:30]+"...", bg="#e1e1e1", borderwidth=1, relief="solid", padx=5, pady=2)
        label.pack()
        
        # 初始位置
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        self.drag_ghost.geometry(f"+{x+15}+{y+10}")

    def _update_drag_ghost(self, event):
        if hasattr(self, 'drag_ghost') and self.drag_ghost:
            # 使用 root coordinates
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
            self.drag_ghost.geometry(f"+{x+15}+{y+10}")

    def _destroy_drag_ghost(self):
        if hasattr(self, 'drag_ghost') and self.drag_ghost:
            self.drag_ghost.destroy()
            self.drag_ghost = None

    def _on_drag_motion(self, event):
        """拖拽中预览 (仅移动 Ghost，不改变 Listbox 选中)"""
        if not hasattr(self, 'drag_item') or not self.drag_item: return
        self._update_drag_ghost(event)
        
        # 可选：绘制一条插入线 (TreeView 比较难实现插入线，这里保持简单，不乱动 Selection)
        # 移除原有的 selection_set 代码，避免鼠标划过时疯狂切换选中项

    def _on_drag_release(self, event):
        self._destroy_drag_ghost()
        if not hasattr(self, 'drag_item') or not self.drag_item: return
        
        # 检测释放位置是否在 Treeview 内
        tv_width = self.paper_tree.winfo_width()
        tv_height = self.paper_tree.winfo_height()
        
        if event.x < 0 or event.x > tv_width or event.y < 0 or event.y > tv_height:
            # 在框外释放，取消移动
            self.drag_item = None
            return

        target_item = self.paper_tree.identify_row(event.y)
        
        if target_item and target_item != self.drag_item:
            try:
                real_from = int(self.drag_item)
                real_to_target = int(target_item)
                
                from_index = self.filtered_indices.index(real_from)
                to_index = self.filtered_indices.index(real_to_target)
                
                self.logic.move_paper(from_index, to_index)
                self.refresh_list_view()
                self._highlight_paper(to_index) 
                
            except ValueError:
                pass 
            
        self.drag_item = None


    def _on_text_undo(self, event):
        try: event.widget.edit_undo(); return "break"
        except: return "break"
    def _on_text_redo(self, event):
        try: event.widget.edit_redo(); return "break"
        except: return "break"


    def on_closing(self):
        if self.logic.papers:
            choice = messagebox.askyesnocancel("确认", "注意！是否保存当前所有论文？如果否，当前所有内容会丢失")
            if choice is None: return
            if choice and self.save_all_papers() == False: return
        self.root.destroy()

    def add_from_zotero_meta(self):
        s = self._show_zotero_input_dialog("从Zotero Meta新建论文")
        if not s: return
        new_p = self.logic.process_zotero_json(s)
        if not new_p: return messagebox.showwarning("提示", "未解析到有效的Zotero数据")
        self.logic.add_zotero_papers(new_p)
        self.update_paper_list()
        idx = len(self.logic.papers)-1
        self.current_paper_index = idx
        self._suppress_select_event = True
        self.paper_tree.selection_set(self.paper_tree.get_children()[idx])
        self._suppress_select_event = False
        self.load_paper_to_form(self.logic.papers[idx])
        self.show_form()
        messagebox.showinfo("成功", f"已添加 {len(new_p)} 篇论文")



def main():
    # 尝试使用 tkinterdnd2 初始化根窗口以支持拖放
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except Exception:
        # 完全回退到普通 Tk
        root = tk.Tk()
        print("ℹ tkinterdnd2 未安装，拖放功能不可用")
        
    app = PaperSubmissionGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()