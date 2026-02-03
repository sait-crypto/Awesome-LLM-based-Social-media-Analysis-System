"""
图形化界面提交系统
它由submit.py调用
业务逻辑在submit_logic.py中实现，这里主要负责UI交互
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
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
        self.root.title("Awesome 论文规范化提交处理界面")
        self.root.geometry("1200x800")
        
        # 初始化业务逻辑控制器
        self.logic = SubmitLogic()
        
        # 快捷引用
        self.config = self.logic.config
        self.settings = self.logic.settings
        
        self.current_paper_index = -1
        
        # 尺寸调整：紧凑 (1.1)
        self.root.tk.call('tk', 'scaling', 1.3)
        
        self.color_invalid = "#FFC0C0" 
        self.color_required_empty = "#E6F7FF"
        self.color_normal = "white"
        
        self.style = ttk.Style()
        self.style.map('Invalid.TCombobox', fieldbackground=[('readonly', self.color_invalid)])
        self.style.map('Required.TCombobox', fieldbackground=[('readonly', self.color_required_empty)])

        self._suppress_select_event = False
        
        # 跟踪已导入的文件，避免重复导入
        # 格式: {'pipeline_image': (源路径, 目标相对路径), 'paper_file': (源路径, 目标相对路径)}
        self._imported_files: Dict[str, Optional[Tuple[str, str]]] = {
            'pipeline_image': None,
            'paper_file': None
        }

        self.setup_ui()
        self.load_initial_data()
        
        messagebox.showinfo("须知",f"该界面用于:\n    1.规范化生成的处理json更新文件\n    2.自动分支并提交PR（完整版功能）\n如果根目录中的submit_template.xlsx或submit_template.json已按规范填写内容，你可以手动提交PR或使用该界面自动分支并提交PR，您提交的内容会自动更新到仓库论文列表")
        
        self.tooltip = None
        self.show_placeholder()
    
    def load_initial_data(self):
        try:
            count = self.logic.load_existing_updates()
            if count > 0:
                self.update_paper_list()
                self.update_status(f"已从{self.logic.update_json_path}加载 {count} 篇论文")
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
        
        title_label = ttk.Label(main_frame, text="🎓 Awesome 论文规范化提交处理界面", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 5))
        
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.paned_window.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=(0,0), pady=(0,0))

        left_frame = ttk.Frame(self.paned_window)
        self.right_container = ttk.Frame(self.paned_window)

        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        self.right_container.columnconfigure(0, weight=1)
        self.right_container.rowconfigure(0, weight=1)
        
        self.setup_paper_list_frame(left_frame)
        self.setup_paper_form_frame(self.right_container)
        
        self.paned_window.add(left_frame, weight=1)
        self.paned_window.add(self.right_container, weight=7)

        self.placeholder_label = ttk.Label(
            self.right_container,
            text="👈 请从左侧列表选择一篇论文以进行编辑",
            font=("Arial", 12),
            foreground="gray",
            anchor="center"
        )
        
        self.setup_buttons_frame(main_frame)
        self.setup_status_bar(main_frame)
    
    def setup_paper_list_frame(self, parent):
        list_title = ttk.Label(parent, text="📚 论文列表", font=("Arial", 11, "bold"))
        list_title.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew")
        
        list_frame.columnconfigure(1, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        columns = ("ID", "标题", "作者", "分类")
        self.paper_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.paper_tree.heading(col, text=col)
            if col == "ID": self.paper_tree.column(col, width=30)
            elif col == "标题": self.paper_tree.column(col, width=180)
            elif col == "作者": self.paper_tree.column(col, width=70)
            else: self.paper_tree.column(col, width=100)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.paper_tree.yview)
        self.paper_tree.configure(yscrollcommand=scrollbar.set)
        
        self.paper_tree.grid(row=0, column=1, sticky="nsew")
        scrollbar.grid(row=0, column=0, sticky="ns")
    
        self.paper_tree.bind('<<TreeviewSelect>>', self.on_paper_selected)
        self.paper_tree.bind('<Enter>', lambda e: self._bind_global_scroll(self.paper_tree.yview_scroll))
        
        list_buttons_frame = ttk.Frame(parent)
        list_buttons_frame.grid(row=2, column=0, pady=(5, 0))
        
        add_button = ttk.Button(list_buttons_frame, text="➕ 添加论文", command=self.add_paper, width=15)
        add_button.grid(row=0, column=0, padx=(0, 5))
        
        delete_button = ttk.Button(list_buttons_frame, text="🗑 删除论文", command=self.delete_paper, width=15)
        delete_button.grid(row=0, column=1, padx=(0, 5))
        
        clear_button = ttk.Button(list_buttons_frame, text="🧹 清空列表", command=self.clear_papers, width=15)
        clear_button.grid(row=0, column=2)
    
    def setup_paper_form_frame(self, parent):
        self.form_container = ttk.Frame(parent)
        
        title_frame = ttk.Frame(self.form_container)
        title_frame.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        form_title = ttk.Label(title_frame, text="📝 论文详情", font=("Arial", 11, "bold"))
        form_title.pack(side=tk.LEFT, padx=(0, 10))
        
        fill_zotero_btn = ttk.Button(title_frame, text="📋 从Zotero Meta填充表单", command=self.fill_from_zotero_meta, width=200)
        fill_zotero_btn.pack(side=tk.LEFT, padx=(55, 0))
        
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
        row = 0
        active_tags = self.config.get_active_tags()
        
        self.form_fields = {}
        self.field_widgets = {}
        
        for tag in active_tags:
            if not tag.get('show_in_readme', True) and tag.get('variable') not in [
                'doi', 'title', 'authors', 'date', 'category', 'status',
                'paper_url', 'project_url', 'abstract',
                'conference', 'contributor', 'notes','is_placeholder',
                'paper_file', 'title_translation'
            ]:
                continue
            
            variable = tag['variable']
            display_name = tag['display_name']
            description = tag.get('description', '')
            required = tag.get('required', False)
            field_type = tag.get('type', 'string')
            
            label_text = f"{display_name}* :" if required else f"{display_name} :"
            
            label = ttk.Label(self.form_frame, text=label_text)
            label_sticky = tk.NW if field_type == 'text' else tk.W
            
            label.grid(row=row, column=0, sticky=label_sticky, pady=(2, 2))
            if description: self.create_tooltip(label, description)
            
            # === 1. Category Field ===
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

            # === 2. File Fields ===
            elif variable in ['pipeline_image', 'paper_file']:
                self._create_file_field_ui(row, variable)

            # === 3. Standard Enum ===
            elif field_type == 'enum':
                values = tag.get('options', [])
                if variable == 'status': values = ['unread', 'reading', 'done', 'skimmed', 'adopted']
                
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
                
                height = 4 if variable in ['abstract', 'notes'] else 2#最小貌似就是4行
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
        
        # 3. 检查是否已经导入过这个源文件
        if field_name in self._imported_files and self._imported_files[field_name]:
            cached_src, cached_dest = self._imported_files[field_name]
            # 如果源文件相同，直接返回之前的目标路径
            if cached_src == src_path:
                return cached_dest
        
        # 4. 需要导入新文件，调用底层方法
        rel_path = self.logic.import_file_asset(src_path, asset_type)
        if rel_path:
            # 记录导入信息
            self._imported_files[field_name] = (src_path, rel_path)
        return rel_path

    def _create_file_field_ui(self, row, variable):
        """Helper to create file fields with correct layout and scoping"""
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
        
        # 拖放功能支持 (可选依赖 tkinterdnd2)
        def setup_drag_drop(widget):
            """设置拖放支持"""
            # 检查是否有全局拖放支持标记
            if not hasattr(self.root, '_dnd_available'):
                try:
                    import tkinterdnd2
                    from tkinterdnd2 import TkinterDnD, DND_FILES
                    
                    # 检查root是否已经是TkinterDnD实例
                    if not isinstance(self.root, TkinterDnD.Tk):
                        # 如果不是，标记为不可用
                        self.root._dnd_available = False
                        self.root._dnd_reason = "需要使用 TkinterDnD.Tk 初始化根窗口"
                    else:
                        # 测试 tkdnd 是否可用
                        try:
                            self.root.tk.call('package', 'require', 'tkdnd')
                            self.root._dnd_available = True
                        except Exception:
                            self.root._dnd_available = False
                            self.root._dnd_reason = "tkdnd 库未正确加载"
                            
                except ImportError:
                    self.root._dnd_available = False
                    self.root._dnd_reason = "未安装 tkinterdnd2"
                except Exception as e:
                    self.root._dnd_available = False
                    self.root._dnd_reason = str(e)
            
            if not self.root._dnd_available:
                # 拖放不可用，提供替代提示
                tooltip_text = "使用「📂 浏览」按钮选择文件"
                self.create_tooltip(widget, tooltip_text)
                
                # 绑定点击事件，提示用户安装
                def on_click_show_tip(event):
                    reason = getattr(self.root, '_dnd_reason', '未知原因')
                    field_name = "Pipeline图" if variable == 'pipeline_image' else "论文文件"
                    messagebox.showinfo(
                        "拖放功能不可用", 
                        f"拖放功能暂不可用（{reason}）\n\n"
                        f"您仍可以使用「📂 浏览」按钮选择{field_name}。\n\n"
                        f"如需启用拖放功能，请安装完整环境：\n"
                        f"pip install tkinterdnd2"
                    )
                    # 只提示一次
                    widget.unbind('<Button-1>')
                
                widget.bind('<Button-1>', on_click_show_tip, add='+')
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
                tooltip_text = "可拖放文件到此，或使用「📂 浏览」按钮"
                self.create_tooltip(widget, tooltip_text)
                
            except Exception as e:
                self.root._dnd_available = False
                self.root._dnd_reason = f"注册失败: {str(e)}"
        
        # 应用拖放支持
        setup_drag_drop(entry)
        
        # FocusOut Event
        def on_focus_out(event):
            path = sv.get().strip()
            if path and os.path.isabs(path) and os.path.exists(path):
                asset_type = 'figure' if variable == 'pipeline_image' else 'paper'
                rel_path = self._import_file_asset_once(path, asset_type, variable)
                if rel_path:
                    sv.set(rel_path)
        entry.bind("<FocusOut>", on_focus_out)

        # Browse
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
        """底部按钮区域重构"""
        buttons_frame = ttk.Frame(parent)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=(15, 10))
        
        # Left Group: Data & PR
        add_zotero_btn = ttk.Button(buttons_frame, text="📑 从Zotero新建论文", command=self.add_from_zotero_meta, width=18)
        add_zotero_btn.grid(row=0, column=0, padx=3)

        save_all_button = ttk.Button(buttons_frame, text="📤 保存到文件", command=self.save_all_papers, width=18)
        save_all_button.grid(row=0, column=1, padx=3)
        
        if getattr(self.logic, 'pr_enabled', True):
            submit_button = ttk.Button(buttons_frame, text="🚀 自动提交PR", command=self.submit_pr, width=18)
            submit_button.grid(row=0, column=2, padx=3)
        
        load_template_button = ttk.Button(buttons_frame, text="📂 从文件加载", command=self.load_template, width=18)
        load_template_button.grid(row=0, column=3, padx=3)
        
        # Spacer
        ttk.Frame(buttons_frame, width=20).grid(row=0, column=4)
        
        # Right Group: AI Tools (Single Dropdown Button)
        ai_frame = ttk.Frame(buttons_frame)
        ai_frame.grid(row=0, column=5, padx=5, sticky="ns")
        
        self.ai_btn_var = tk.StringVar(value="🤖 AI 助手 ▾")
        ai_btn = ttk.Button(ai_frame, textvariable=self.ai_btn_var, width=18)
        ai_btn.pack()
        
        self.ai_menu = tk.Menu(self.root, tearoff=0)
        
        # Group 1: Config & Tools
        self.ai_menu.add_command(label="🧰 AI 工具箱", command=self.ai_toolbox_window)
        self.ai_menu.add_command(label="⚙️ AI 配置", command=self.open_ai_config_dialog)
        
        self.ai_menu.add_separator()
        
        # Group 2: Actions
        self.ai_menu.add_command(label="✨ 生成所有空字段", command=lambda: self.run_ai_task(self.ai_generate_field, None))
        self.ai_menu.add_command(label="🏷️分类建议", command=self.ai_suggest_category)
        
        def show_ai_menu(event):
            self.ai_menu.post(event.x_root, event.y_root)
        ai_btn.bind("<Button-1>", show_ai_menu)

    def ai_toolbox_window(self):
        """弹出AI生成工具箱 (非模态)"""
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
        
        # --- Config & Category ---
        # 移除 LabelFrame，直接放置按钮，用分割线分开
        
        ttk.Button(menu_win, text="🏷️分类建议", command=self.ai_suggest_category).pack(fill=tk.X, padx=10, pady=(10, 2))
        ttk.Separator(menu_win, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(menu_win, text="⚙️ AI 配置", command=self.open_ai_config_dialog).pack(fill=tk.X, padx=10, pady=(2, 10))
        
        # --- Generators Group ---
        gen_frame = ttk.LabelFrame(menu_win, text="字段生成", padding=5)
        gen_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(gen_frame, text="✨ 所有空字段", 
                   command=lambda: self.run_ai_task(self.ai_generate_field, None)).pack(fill=tk.X, pady=3)
        
        ttk.Separator(gen_frame, orient='horizontal').pack(fill=tk.X, pady=5)
        
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
        
        tree = ttk.Treeview(win, columns=("ID", "Desc"), show="tree headings")
        tree.heading("#0", text="Name")
        tree.heading("ID", text="Unique Name")
        tree.heading("Desc", text="Description")
        tree.pack(fill=tk.BOTH, expand=True)
        
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

        if target_combo:
            tree.bind("<Double-1>", on_double_click)
            ttk.Label(win, text="双击分类以填充", foreground="blue").pack()

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
        for item in self.paper_tree.get_children():
            self.paper_tree.delete(item)
        for i, paper in enumerate(self.logic.papers):
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            cat_disp = paper.category
            if hasattr(self, 'category_mapping') and paper.category:
                parts = [p.strip() for p in str(paper.category).split(';') if p.strip()]
                cat_disp = ", ".join([self.category_reverse_mapping.get(p, p) for p in parts])
            item = self.paper_tree.insert("", "end", values=(i+1, title, authors, cat_disp))
            if self.current_paper_index == i:
                self.paper_tree.selection_set(item)
                self.paper_tree.see(item)
    
    def on_paper_selected(self, event):
        if self._suppress_select_event: return
        selection = self.paper_tree.selection()
        if not selection:
            self.current_paper_index = -1
            self.show_placeholder()
            return
        item = selection[0]
        values = self.paper_tree.item(item, 'values')
        paper_index = int(values[0]) - 1
        if 0 <= paper_index < len(self.logic.papers):
            self.current_paper_index = paper_index
            self.show_form()
            self.load_paper_to_form(self.logic.papers[paper_index])
            self._validate_all_fields_visuals()
            self.update_status(f"正在编辑: {self.logic.papers[paper_index].title[:30]}...")

    def load_paper_to_form(self, paper):
        self._disable_callbacks = True
        
        # 清空文件导入缓存，为新论文准备
        self._imported_files = {
            'pipeline_image': None,
            'paper_file': None
        }
        
        try:
            for variable, widget in self.form_fields.items():
                value = getattr(paper, variable, "")
                if value is None: value = ""
                
                # 对于文件字段，记录当前值到缓存
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
        new_value = ""
        if variable == 'category': pass
        elif isinstance(widget_or_var, tk.BooleanVar): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, scrolledtext.ScrolledText): new_value = widget_or_var.get(1.0, tk.END).strip()
        elif isinstance(widget_or_var, ttk.Combobox): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, tk.Entry): new_value = widget_or_var.get()
        current_paper = self.logic.papers[self.current_paper_index]
        setattr(current_paper, variable, new_value)
        self._validate_single_field_visuals(variable)
        if variable in ['title', 'authors']: self._refresh_list_item(self.current_paper_index)

    def _on_category_change(self, variable=None, widget_or_var=None):
        if getattr(self, '_disable_callbacks', False): return
        if self.current_paper_index < 0: return
        unique_names = self._gui_get_category_values()
        cat_str = ";".join(unique_names)
        current_paper = self.logic.papers[self.current_paper_index]
        current_paper.category = cat_str
        self._validate_single_field_visuals('category')
        self._refresh_list_item(self.current_paper_index)

    def _on_text_undo(self, event):
        try:
            event.widget.edit_undo()
            variable = next((var for var, w in self.form_fields.items() if w == event.widget), None)
            if variable: self._on_field_change(variable, event.widget)
            return "break"
        except: return "break"

    def _on_text_redo(self, event):
        try:
            event.widget.edit_redo()
            variable = next((var for var, w in self.form_fields.items() if w == event.widget), None)
            if variable: self._on_field_change(variable, event.widget)
            return "break"
        except: return "break"

    def _refresh_list_item(self, index):
        children = self.paper_tree.get_children()
        if index < len(children):
            paper = self.logic.papers[index]
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            cat_disp = paper.category
            if hasattr(self, 'category_mapping') and paper.category:
                parts = [p.strip() for p in str(paper.category).split(';') if p.strip()]
                cat_disp = ", ".join([self.category_reverse_mapping.get(p, p) for p in parts])
            self.paper_tree.item(children[index], values=(index+1, title, authors, cat_disp))

    def _validate_single_field_visuals(self, variable):
        if self.current_paper_index < 0: return
        paper = self.logic.papers[self.current_paper_index]
        is_valid, _, _ = paper.validate_paper_fields(self.config, True, True, variable=variable, no_normalize=True)
        tag_config = self.config.get_tag_by_variable(variable)
        is_required = tag_config.get('required', False) if tag_config else False
        val = getattr(paper, variable, "")
        is_empty = not val if variable == 'category' else (val is None or str(val).strip() == "" or str(val) == self.logic.PLACEHOLDER)
        self._apply_widget_style(variable, is_valid, is_required, is_empty)

    def _validate_all_fields_visuals(self, variable=None, widget_or_var=None):
        if self.current_paper_index < 0: return
        paper = self.logic.papers[self.current_paper_index]
        _, _, invalid_vars = paper.validate_paper_fields(self.config, True, True, no_normalize=True)
        invalid_set = set(invalid_vars)
        for variable in self.form_fields.keys():
            tag_config = self.config.get_tag_by_variable(variable)
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

    def add_paper(self):
        placeholder = self.logic.create_new_paper()
        self.update_paper_list()
        new_index = len(self.logic.papers) - 1
        children = self.paper_tree.get_children()
        self.current_paper_index = new_index
        self._suppress_select_event = True
        if new_index < len(children):
            self.paper_tree.selection_set(children[new_index])
            self.paper_tree.see(children[new_index])
        self._suppress_select_event = False
        self.load_paper_to_form(placeholder)
        self.show_form()
        self._validate_all_fields_visuals()
        self.update_status("已创建新论文，请在右侧编辑")
        self.root.update_idletasks()
        try: next(w for w in self.form_fields.values() if isinstance(w, (tk.Entry, ttk.Combobox))).focus_force()
        except: pass

    def delete_paper(self):
        if self.current_paper_index < 0: return messagebox.showwarning("警告", "请先选择一篇论文")
        if messagebox.askyesno("确认", "确定要删除这篇论文吗？"):
            if self.logic.delete_paper(self.current_paper_index):
                self.current_paper_index = -1
                self.update_paper_list()
                self.show_placeholder()
                self.update_status("论文已删除")

    def clear_papers(self):
        if not self.logic.papers: return
        if messagebox.askyesno("警告", "警告！确定要清空所有论文吗？\n\n⚠️ 这将丢失目前已添加的所有论文！"):
            if messagebox.askyesno("警告", "二次警告！确定要清空所有论文吗？\n\n⚠️ 这将丢失目前已添加的所有论文！"):
                self.logic.clear_papers()
                self.current_paper_index = -1
                self.update_paper_list()
                self.show_placeholder()
                self.update_status("所有论文已清空")

    def save_all_papers(self):
        if not self.logic.papers: return messagebox.showwarning("警告", "没有论文可以保存")
        invalid_papers = self.logic.validate_papers_for_save()
        if invalid_papers:
            msg = "保存被阻止！列表中发现验证失败的论文:\n\n" + "\n".join([f"#{i} {t[:30]}... - {', '.join(e[:2])}" for i, t, e in invalid_papers])
            msg += "\n请在左侧列表中选择对应论文，修正红色标记的字段后再保存。"
            return messagebox.showerror("验证错误", msg)
        target_path = filedialog.asksaveasfilename(title="选择保存到的更新文件（JSON）", defaultextension='.json', filetypes=[("JSON", "*.json")], initialfile='submit_template.json', initialdir=BASE_DIR)
        if not target_path: return self.update_status("保存已取消")
        
        _, has_conflict = self.logic.check_save_conflicts(target_path)
        conflict_mode = 'overwrite_duplicates'
        if has_conflict:
            msg = f"检测到部分论文已存在于更新文件中（基于DOI或Title）。\n\n是否覆盖这些重复的条目？"
            res = messagebox.askyesnocancel("发现重复论文", msg)
            if res is None: return self.update_status("保存操作已取消")
            conflict_mode = 'overwrite_all' if res else 'skip_all'
        
        try:
            merged = self.logic.perform_save(target_path, conflict_mode)
            messagebox.showinfo("成功", f"成功保存 {len(merged)} 篇论文到更新文件:\n{target_path}")
            self.update_status(f"已更新文件: {target_path}")
        except Exception as e: messagebox.showerror("Error", str(e))

    def submit_pr(self):
        if not messagebox.askyesno("须知", f"将自动通过pull request提交论文...\n\n1.若当前在main分支，将创建新分支提交PR；\n2.提交PR后将切回原分支；\n3.收到PR后github action将自动读取submit_template.xlsx和submit_template.json中的论文进行更新\n"): return
        if not self.logic.has_update_files():
             if messagebox.askyesno("确认", "注意！是否保存当前所有论文？如果否，当前工作区内容将不会提交PR"): 
                if self.save_all_papers()==False: return
        if not messagebox.askyesno("确认", f"确定要提交submit_template.xlsx和submit_template.json中的论文吗？"): return
        
        def on_status(msg): self.root.after(0, lambda: self.update_status(msg))
        def on_result(url, branch, manual):
            if manual: self.root.after(0, lambda: self.show_github_cli_guide(branch))
            else: self.root.after(0, lambda: self.show_pr_result(url))
        def on_error(msg): 
            self.root.after(0, lambda: messagebox.showerror("提交失败", msg))
            self.root.after(0, lambda: self.update_status("提交失败"))
        self.logic.execute_pr_submission(on_status, on_result, on_error)

    def show_github_cli_guide(self, branch): messagebox.showinfo("手动创建PR指引", f"请打开项目的github页面，按照引导手动创建PR。分支: {branch}")
    def show_pr_result(self, url):
        w = tk.Toplevel(self.root); w.title("PR提交结果"); w.geometry("400x200")
        ttk.Label(w, text=f"PR Link: {url or '代码已推送，请手动创建PR'}", wraplength=380).pack(pady=20)

    def load_template(self):
        path = filedialog.askopenfilename(title="选择模板文件", filetypes=[("Excel和JSON文件", "*.xlsx *.json"), ("Excel文件", "*.xlsx"), ("JSON文件", "*.json"), ("所有文件", "*.*")])
        if not path: return
        if self.logic.papers:
            choice = messagebox.askyesnocancel("确认", "注意！是否保存当前所有论文？如果否，当前所有内容会丢失")
            if choice is None: return
            if choice and self.save_all_papers() == False: return
        try:
            cnt = self.logic.load_from_template(path)
            self.update_paper_list()
            self.current_paper_index = -1
            self.show_placeholder()
            messagebox.showinfo("成功", f"已加载 {cnt} 篇论文")
        except Exception as e: messagebox.showerror("Error", f"加载模板失败: {e}")

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

    def fill_from_zotero_meta(self):
        if self.current_paper_index < 0: return messagebox.showwarning("提示", "请先在左侧选择要填充的论文条目")
        s = self._show_zotero_input_dialog("填充当前表单")
        if not s: return
        new_p = self.logic.process_zotero_json(s)
        if not new_p: return
        conflicts, updates = self.logic.get_zotero_fill_updates(new_p[0], self.current_paper_index)
        if not updates: return messagebox.showinfo("提示", "Zotero数据中没有有效内容可填充")
        overwrite = True
        if conflicts:
            msg = f"检测到 {len(conflicts)} 个字段已有内容（如 {conflicts[0]} 等）。\n\n是否覆盖已有内容？\n\n是(Yes): 覆盖所有字段\n否(No): 仅填充空白字段 (保留已有内容)\n取消(Cancel): 取消操作"
            res = messagebox.askyesnocancel("覆盖确认", msg)
            if res is None: return
            overwrite = res
        cnt = self.logic.apply_paper_updates(self.current_paper_index, updates, overwrite)
        self.load_paper_to_form(self.logic.papers[self.current_paper_index])
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
        def help():
            msg = "1. 推荐使用特意开发的zotero插件'One-Click Copy Metadata'\n可从项目的tools文件夹拿到One-Click Copy Metadata.xpi）。\n也可在github主页面的readme中找到下载链接。\n2. 安装后右键点击条目 -> ==Copy Meta to JSON Format==。就会将所需meta数据拷贝到剪贴板\n\n注：也可以手动从Zotero导出为CSL JSON格式。（因数据不完全，不推荐）\n\n支持单个条目 {...} 或 条目列表 [...]"
            messagebox.showinfo("获取帮助", msg, parent=d)
        
        bf = ttk.Frame(d); bf.pack(pady=10)
        ttk.Button(bf, text="✅ 确定", command=ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(bf, text="❓ 帮助", command=help).pack(side=tk.LEFT, padx=10)
        
        self.root.wait_window(d)
        return res['d']

def main():
    # 尝试使用 tkinterdnd2 初始化根窗口以支持拖放
    dnd_enabled = False
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
        
        # # 验证 tkdnd 是否真正可用
        # try:
        #     version = root.tk.call('tkdnd::version')
        #     dnd_enabled = True
        #     print(f"✓ 拖放功能已启用 (tkdnd {version})")
        # except Exception:
        #     # tkdnd 不可用，但已经创建了 root，继续使用
        #     print("ℹ tkinterdnd2 已安装但拖放不可用，使用浏览按钮选择文件")
            
    except Exception:
        # 完全回退到普通 Tk
        root = tk.Tk()
        print("ℹ 使用浏览按钮选择文件")
        
    app = PaperSubmissionGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()