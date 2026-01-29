"""
图形化界面提交系统
它由submit.py调用
为方便贡献者，该脚本的运行不需要任何额外的非官方第三方包
"""
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 统一根目录锚定到 config_loader.py 的 project_root
from src.core.config_loader import get_config_instance
BASE_DIR = str(get_config_instance().project_root)

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity
from src.core.update_file_utils import get_update_file_utils
from src.process_zotero_meta import ZoteroProcessor

from src.utils import clean_doi

class PaperSubmissionGUI:
    """论文提交图形界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Awesome 论文规范化提交处理界面")
        self.root.geometry("1200x800")
        
        # 设置图标和主题
        self.root.tk.call('tk', 'scaling', 1.5)
        
        # 加载配置
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.update_utils = get_update_file_utils()
        self.zotero_processor = ZoteroProcessor()
        
        
        # 论文列表
        self.papers = []  # 存储Paper对象
        self.current_paper_index = -1
        
        # 定义占位符常量
        self.PLACEHOLDER = "to be filled in"
        
        # 更新文件路径
        # 路径全部基于项目根目录（project_root）
        self.update_json_path = os.path.join(BASE_DIR, self.settings['paths']['update_json'])
        self.update_excel_path = os.path.join(BASE_DIR, self.settings['paths']['update_excel'])
        # 其他配置
        self.conflict_marker = self.settings['database']['conflict_marker']

        # 获取配置中的颜色（用于验证反馈）
        self.color_invalid = "#FFC0C0" 
        self.color_required_empty = "#E6F7FF"  # 浅蓝色
        self.color_normal = "white"

        # 是否启用自动提交 PR 功能
        try:
            ui_cfg = self.settings.get('ui', {}) or {}
            enable_pr_val = ui_cfg.get('enable_pr', 'true')
            self.pr_enabled = str(enable_pr_val).strip().lower() in ('1', 'true', 'yes', 'on')
        except Exception:
            self.pr_enabled = True

        # 命令行或环境变量也可以强制禁用
        if '--no-pr' in sys.argv or os.environ.get('NO_PR', '').lower() in ('1', 'true'):
            self.pr_enabled = False
        
        # 配置样式
        self.style = ttk.Style()
        self.style.map('Invalid.TCombobox', fieldbackground=[('readonly', self.color_invalid)])
        self.style.map('Required.TCombobox', fieldbackground=[('readonly', self.color_required_empty)])

        # 防闪烁标志位
        self._suppress_select_event = False

        # 创建界面
        self.setup_ui()
        
        # 加载现有的更新文件（如果有）
        self.load_existing_updates()
        messagebox.showinfo("须知",f"该界面用于:\n    1.规范化生成的处理json更新文件\n    2.自动分支并提交PR（完整版功能）\n如果根目录中的submit_template.xlsx或submit_template.json已按规范填写内容，你可以手动提交PR或使用该界面自动分支并提交PR，您提交的内容会自动更新到仓库论文列表")
        
        # 初始化tooltip
        self.tooltip = None
        
        # 初始状态：未选中任何论文，显示占位符
        self.show_placeholder()
    
    def setup_ui(self):
        """设置用户界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1) # 修正：让第0列（PanedWindow所在列）自动扩展
        main_frame.columnconfigure(1, weight=1) # 保持兼容性（如果有组件跨列）
        main_frame.rowconfigure(1, weight=1)
        
        # 标题
        title_label = ttk.Label(
            main_frame, 
            text="🎓 Awesome 论文规范化提交处理界面",
            font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 12))
        
        # 创建可拖动的分割窗口 (PanedWindow) 代替原来的左右Grid布局
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.paned_window.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=(0,0), pady=(0,0))

        # 创建左右主要区域的容器
        left_frame = ttk.Frame(self.paned_window)
        self.right_container = ttk.Frame(self.paned_window)

        # 配置左右框架内部的网格权重（原逻辑保留）
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        self.right_container.columnconfigure(0, weight=1)
        self.right_container.rowconfigure(0, weight=1)
        
        # 初始化左右内容
        self.setup_paper_list_frame(left_frame)
        self.setup_paper_form_frame(self.right_container)
        
        # 将左右框架添加到 PanedWindow
        self.paned_window.add(left_frame, weight=1)
        self.paned_window.add(self.right_container, weight=7) # 右侧默认分配更多空间，奇怪差异怎么这大

        # 右侧：占位提示 (默认显示)
        self.placeholder_label = ttk.Label(
            self.right_container,
            text="👈 请从左侧列表选择一篇论文以进行编辑",
            font=("Arial", 14),
            foreground="gray",
            anchor="center"
        )
        
        # 底部按钮
        self.setup_buttons_frame(main_frame)
        
        # 状态栏
        self.setup_status_bar(main_frame)
    
    def setup_paper_list_frame(self, parent):
        """设置论文列表框架"""
        # 列表标题
        list_title = ttk.Label(parent, text="📚 论文列表", font=("Arial", 12, "bold"))
        list_title.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # 论文列表框架
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew")
        
        # 配置网格权重
        list_frame.columnconfigure(1, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 创建Treeview（列表）
        columns = ("ID", "标题", "作者", "分类")
        self.paper_tree = ttk.Treeview(
            list_frame, 
            columns=columns,
            show="headings",
            height=15
        )
        
        # 设置列标题
        for col in columns:
            self.paper_tree.heading(col, text=col)
            if col == "ID":
                self.paper_tree.column(col, width=10)
            elif col == "标题":
                self.paper_tree.column(col, width=220)
            elif col == "作者":
                self.paper_tree.column(col, width=80)
            else:
                self.paper_tree.column(col, width=120)
        
        # 设置滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.paper_tree.yview)
        self.paper_tree.configure(yscrollcommand=scrollbar.set)
        
        # 网格布局
        self.paper_tree.grid(row=0, column=1, sticky="nsew")
        scrollbar.grid(row=0, column=0, sticky="ns")
    

        
        # 绑定选择事件
        self.paper_tree.bind('<<TreeviewSelect>>', self.on_paper_selected)
        
        # 绑定鼠标进入事件以处理滚动焦点 (鼠标在列表框时滚动列表)
        self.paper_tree.bind('<Enter>', lambda e: self._bind_global_scroll(self.paper_tree.yview_scroll))
        
        # 列表操作按钮框架
        list_buttons_frame = ttk.Frame(parent)
        list_buttons_frame.grid(row=2, column=0, pady=(10, 0))
        
        # 添加论文按钮
        add_button = ttk.Button(
            list_buttons_frame, 
            text="➕ 添加论文",
            command=self.add_paper,
            width=15
        )
        add_button.grid(row=0, column=0, padx=(0, 5))
        
        # 删除论文按钮
        delete_button = ttk.Button(
            list_buttons_frame,
            text="🗑️删除论文",
            command=self.delete_paper,
            width=15
        )
        delete_button.grid(row=0, column=1, padx=(0, 5))
        
        # 清空列表按钮
        clear_button = ttk.Button(
            list_buttons_frame,
            text="🧹 清空列表",
            command=self.clear_papers,
            width=15
        )
        clear_button.grid(row=0, column=2)
    
    def setup_paper_form_frame(self, parent):
        """设置论文表单框架"""
        # 整个表单的容器（包括标题和滚动区域）
        self.form_container = ttk.Frame(parent)
        
        # 表单标题栏容器
        title_frame = ttk.Frame(self.form_container)
        title_frame.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # 表单标题
        form_title = ttk.Label(title_frame, text="📝 论文详情", font=("Arial", 12, "bold"))
        form_title.pack(side=tk.LEFT, padx=(0, 10))
        
        # Zotero填入按钮
        fill_zotero_btn = ttk.Button(
            title_frame,
            text="📋 从Zotero Meta填充表单",
            command=self.fill_from_zotero_meta,
            width=200#暂时用足够宽的宽度模拟伸缩
        )
        fill_zotero_btn.pack(side=tk.LEFT, padx=(52, 0))
        
        # 创建Canvas和滚动条
        self.form_canvas = tk.Canvas(self.form_container)
        scrollbar = ttk.Scrollbar(self.form_container, orient=tk.VERTICAL, command=self.form_canvas.yview)
        
        # 表单内部框架（放在Canvas中）
        self.form_frame = ttk.Frame(self.form_canvas)
        
        # 配置Canvas
        self.form_canvas.configure(yscrollcommand=scrollbar.set)
        
        # 显式指定 width=800，防止初始不可见时宽度塌缩导致无法点击
        self.form_canvas_window = self.form_canvas.create_window(
            (0, 0), 
            window=self.form_frame, 
            anchor=tk.NW,
            width=800 
        )

        # 绑定鼠标进入事件以处理滚动焦点
        self.form_canvas.bind('<Enter>', lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
        self.form_frame.bind('<Enter>', lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))

        # 网格布局
        self.form_canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        
        # 配置网格权重
        self.form_container.columnconfigure(0, weight=1)
        self.form_container.rowconfigure(1, weight=1)
        
        # 绑定Canvas大小变化事件
        self.form_frame.bind("<Configure>", lambda e: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all")))
        self.form_canvas.bind("<Configure>", self._on_canvas_configure)
        
        # 创建表单字段
        self.create_form_fields()
    
    def _on_canvas_configure(self, event):
        """当Canvas大小改变时调整内部Frame宽度"""
        # 始终同步宽度，确保 Inner Frame 填满 Canvas，保证点击区域有效
        if event.width > 1:
            self.form_canvas.itemconfig(self.form_canvas_window, width=event.width)

    def create_form_fields(self):
        """创建表单字段"""
        row = 0
        active_tags = self.config.get_active_tags()
        
        self.form_fields = {}
        self.field_widgets = {}
        
        for tag in active_tags:
            if not tag.get('show_in_readme', True) and tag.get('variable') not in [
                'doi', 'title', 'authors', 'date', 'category', 'status',
                'paper_url', 'project_url', 'abstract',
                'conference', 'contributor', 'notes','is_placeholder'
            ]:
                continue
            
            variable = tag['variable']
            display_name = tag['display_name']
            description = tag.get('description', '')
            required = tag.get('required', False)
            field_type = tag.get('type', 'string')
            
            # 标签
            if required:
                label_text = f"{display_name}* :"
            else:
                label_text = f"{display_name} :"
            
            label = ttk.Label(self.form_frame, text=label_text)
            label_sticky = tk.W
            if field_type == 'text' :
                label_sticky = tk.NW
            
            label.grid(row=row, column=0, sticky=label_sticky, pady=(5, 4))
            
            if description:
                self.create_tooltip(label, description)
            
            # --- 字段创建逻辑 ---

            if field_type == 'enum[]' and variable == 'category':
                # 分类输入支持多个
                container = ttk.Frame(self.form_frame)
                container.grid(row=row, column=1, sticky="we", pady=(5, 4), padx=(10, 0))

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
            
            # 普通的 enum 下拉框
            elif field_type == 'enum':
                values = tag.get('options', [])
                if variable == 'status':
                    values = ['unread', 'reading', 'done', 'skimmed', 'adopted']

                # 使用 sticky="we" 并在 grid 中设置 padx 以匹配 Entry 的宽度
                combo = ttk.Combobox(self.form_frame, values=values, state='readonly')
                combo.grid(row=row, column=1, sticky="we", pady=(5, 4), padx=(10, 0))
                
                combo.bind("<<ComboboxSelected>>", lambda e, v=variable, w=combo: self._on_field_change(v, w))
                
                # 绑定进入事件以处理滚动 (虽然全局逻辑已经处理，但双重保险)
                combo.bind("<Enter>", lambda e: self._unbind_global_scroll())
                combo.bind("<Leave>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
                
                # 明确禁止滚动穿透
                combo.bind("<MouseWheel>", lambda e: "break")
                combo.bind("<Button-4>", lambda e: "break")
                combo.bind("<Button-5>", lambda e: "break")
                
                self.form_fields[variable] = combo
                self.field_widgets[variable] = combo

            elif field_type == 'bool':
                var = tk.BooleanVar()
                var.trace_add("write", lambda *args, v=variable, val=var: self._on_field_change(v, val))
                checkbox = ttk.Checkbutton(self.form_frame, variable=var)
                checkbox.grid(row=row, column=1, sticky=tk.W, pady=(5, 4), padx=(10, 0))
                self.form_fields[variable] = var
                self.field_widgets[variable] = checkbox 
                
            elif field_type == 'text':
                text_frame = ttk.Frame(self.form_frame)
                text_frame.grid(row=row, column=1, sticky="we", pady=(5, 4), padx=(10, 0))
                
                height=5 if variable == 'abstract' or variable == 'notes' else 3
                text_widget = scrolledtext.ScrolledText(text_frame, height=height, width=50, undo=True, maxundo=-1)
                text_widget.grid(row=0, column=0, sticky="nsew")
                
                text_frame.columnconfigure(0, weight=1)
                text_frame.rowconfigure(0, weight=1)
                
                self.form_fields[variable] = text_widget
                self.field_widgets[variable] = text_widget
                
                text_widget.bind("<KeyRelease>", lambda e, v=variable, w=text_widget: self._on_field_change(v, w))
                text_widget.bind("<Enter>", lambda e: self._unbind_global_scroll())
                text_widget.bind("<Leave>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))

                text_widget.bind('<Control-z>', lambda e: self._on_text_undo(e))
                text_widget.bind('<Control-y>', lambda e: self._on_text_redo(e))
                
            else:
                entry = tk.Entry(self.form_frame, width=60, relief=tk.GROOVE, borderwidth=2)
                entry.grid(row=row, column=1, sticky="we", pady=(5, 4), padx=(10, 0))
                
                sv = tk.StringVar()
                sv.trace_add("write", lambda *args, v=variable, w=entry: self._on_field_change(v, w))
                entry.config(textvariable=sv)
                entry.textvariable = sv  # tkinter Entry 推荐使用 textvariable
                
                entry.bind("<Enter>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))

                self.form_fields[variable] = entry
                self.field_widgets[variable] = entry
            
            row += 1
        
        self.form_frame.columnconfigure(1, weight=1)

    # ---------- Category GUI helpers ----------
    def _gui_add_category_row(self, value_display: str = ""):
        container = getattr(self, 'category_container', None)
        if container is None:
            return

        is_first = len(getattr(self, 'category_rows', [])) == 0
        row_frame = ttk.Frame(container)
        row_frame.pack(fill='x', pady=2)

        btn_text = '+' if is_first else '-'
        btn = ttk.Button(row_frame, text=btn_text, width=2)
        btn.pack(side='left', padx=(0, 6))

        combo = ttk.Combobox(
            row_frame, 
            state='readonly', 
            values=[cat['name'] for cat in self.config.get_active_categories()]
        )
        combo.pack(side='left', fill='x', expand=True)
        
        if value_display:
            combo.set(value_display)
            
        combo.bind("<<ComboboxSelected>>", lambda e: [
            self._show_category_tooltip(combo),
            self._on_category_change()
        ])
        
        # 绑定进入事件以处理滚动
        combo.bind("<Enter>", lambda e: self._unbind_global_scroll())
        combo.bind("<Leave>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
        
        # 明确禁止滚动穿透，防止滚动下拉框时带动Canvas
        combo.bind("<MouseWheel>", lambda e: "break")
        combo.bind("<Button-4>", lambda e: "break")
        combo.bind("<Button-5>", lambda e: "break")
        
        combo.bind("<Enter>", lambda e, c=combo: self._show_category_tooltip(c), add='+')
        combo.bind("<Leave>", lambda e: self._hide_inline_tooltip(), add='+')

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
                    except Exception:
                        pass
            return on_btn_click

        btn.config(command=make_button_callback(row_frame, is_first))
        self.category_rows.append((row_frame, btn, combo))
        
        if len(self.category_rows) >= self._gui_category_max and is_first:
            btn.config(state='disabled')

    def _gui_clear_category_rows(self):
        try:
            for frame, btn, combo in getattr(self, 'category_rows', []):
                frame.destroy()
        except Exception:
            pass
        self.category_rows = []

    def _show_inline_tooltip(self, widget, text):
        try:
            self._hide_inline_tooltip()
        except Exception:
            pass
        try:
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            label = ttk.Label(tip, text=text, background="#ffffe0", relief="solid", borderwidth=1, padding=5)
            label.pack()
            self._inline_tooltip = tip
            try:
                if hasattr(self, '_inline_tooltip_after_id') and self._inline_tooltip_after_id:
                    try:
                        self.root.after_cancel(self._inline_tooltip_after_id)
                    except Exception:
                        pass
                self._inline_tooltip_after_id = self.root.after(1500, self._hide_inline_tooltip)
            except Exception:
                self._inline_tooltip_after_id = None
        except Exception:
            self._inline_tooltip = None

    def _hide_inline_tooltip(self):
        try:
            tip = getattr(self, '_inline_tooltip', None)
            if tip is not None:
                tip.destroy()
            aid = getattr(self, '_inline_tooltip_after_id', None)
            if aid:
                self.root.after_cancel(aid)
                self._inline_tooltip_after_id = None
        finally:
            self._inline_tooltip = None

    def _show_category_tooltip(self, combo_widget):
        try:
            name = combo_widget.get().strip()
            if not name: return
            desc = getattr(self, 'category_description_mapping', {}).get(name, '')
            if desc:
                self._show_inline_tooltip(combo_widget, desc)
        except Exception:
            return

    def _gui_get_category_values(self) -> List[str]:
        values = []
        for frame, btn, combo in getattr(self, 'category_rows', []):
            display_name = combo.get().strip()
            if display_name:
                unique_name = self.category_mapping.get(display_name, display_name)
                if unique_name:
                    values.append(unique_name)
        return values
    
    # ---------- Scrolling Logic ----------
    def _bind_global_scroll(self, target_scroll_func):
        """绑定全局滚轮事件到指定滚动函数"""
        # 先解绑
        self._unbind_global_scroll()
        
        # 定义回调
        def _on_mousewheel(event):
            # 【修复：防穿透核心】检查事件源组件是否为 Combobox (下拉框)
            # 如果鼠标在下拉框上，阻止 Canvas 滚动
            try:
                widget = event.widget
                # 向上查找组件层级，看是否包含 Combobox
                # Tkinter 的 Combobox 内部可能包含 Entry 或 Listbox，需要判断 class
                if widget.winfo_class() == 'TCombobox':
                    return "break"
            except Exception:
                pass

            try:
                if hasattr(event, 'delta'):
                    delta = int(-1 * (event.delta / 120))
                    if delta == 0: delta = -1 if event.delta > 0 else 1
                else:
                    delta = 1 if getattr(event, 'num', 5) == 5 else -1
                target_scroll_func(delta, 'units')
                return "break"
            except Exception:
                return
        
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self.root.bind_all("<Button-4>", _on_mousewheel)
        self.root.bind_all("<Button-5>", _on_mousewheel)

    def _unbind_global_scroll(self):
        """解绑全局滚轮事件"""
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")

    def create_tooltip(self, widget, text):
        def enter(event):
            try:
                x = widget.winfo_rootx() + 20
                y = widget.winfo_rooty() + widget.winfo_height() + 5
            except Exception:
                x, y = widget.winfo_rootx() + 20, widget.winfo_rooty() + 20
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            label = ttk.Label(self.tooltip, text=text, background="#ffffe0",
                              relief="solid", borderwidth=1, padding=5)
            label.pack()
        def leave(event):
            if getattr(self, 'tooltip', None):
                if self.tooltip is not None:
                    self.tooltip.destroy()
                self.tooltip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)
    
    def setup_buttons_frame(self, parent):
        buttons_frame = ttk.Frame(parent)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=(20, 10))
        
        # Zotero新建按钮 (最左侧)
        add_zotero_btn = ttk.Button(
            buttons_frame,
            text="📑 从Zotero新建论文",
            command=self.add_from_zotero_meta,
            width=20
        )
        add_zotero_btn.grid(row=0, column=0, padx=5)

        save_all_button = ttk.Button(
            buttons_frame,
            text="📤 保存所有论文到文件",
            command=self.save_all_papers,
            width=20
        )
        save_all_button.grid(row=0, column=1, padx=5)
        
        if getattr(self, 'pr_enabled', True):
            submit_button = ttk.Button(
                buttons_frame,
                text="🚀 自动提交PR",
                command=self.submit_pr,
                width=20
            )
            submit_button.grid(row=0, column=2, padx=5)
        
        load_template_button = ttk.Button(
            buttons_frame,
            text="📂 加载模板文件",
            command=self.load_template,
            width=20
        )
        load_template_button.grid(row=0, column=3, padx=5)
    
    def setup_status_bar(self, parent):
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(
            parent,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.grid(row=3, column=0, columnspan=2, sticky="we", pady=(10, 0))
    
    def update_status(self, message):
        self.status_var.set(message)
        self.root.update_idletasks()

    def show_placeholder(self):
        self.form_container.grid_forget()
        self.placeholder_label.grid(row=0, column=0, sticky="nsew")

    def show_form(self):
        """显示表单，隐藏占位符"""
        self.placeholder_label.grid_forget()
        self.form_container.grid(row=0, column=0, sticky="nsew")
        
        # 强制刷新布局，确保 Canvas 正确计算
        self.root.update_idletasks()
        current_width = self.form_canvas.winfo_width()
        if current_width > 1:
             self.form_canvas.itemconfig(self.form_canvas_window, width=current_width)
        
        self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))
        self.form_canvas.xview_moveto(0)
        self.form_canvas.yview_moveto(0)
    
    def load_existing_updates(self):
        if os.path.exists(self.update_json_path):
            try:
                self.papers.extend(self.update_utils.load_papers_from_json(self.update_json_path, skip_invalid=False))
                self.update_paper_list()
                self.update_status(f"已从{self.update_json_path}加载 {len(self.papers)} 篇论文")
            except Exception as e:
                messagebox.showerror("错误", f"加载更新文件失败: {e}")
    
    def update_paper_list(self):
        for item in self.paper_tree.get_children():
            self.paper_tree.delete(item)
        
        for i, paper in enumerate(self.papers):
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            
            category_display = paper.category
            if hasattr(self, 'category_mapping') and paper.category:
                parts = [p.strip() for p in str(paper.category).split(';') if p.strip()]
                display_parts = []
                for p in parts:
                    disp = self.category_reverse_mapping.get(p)
                    if disp:
                        display_parts.append(disp)
                    else:
                        display_parts.append(p)
                category_display = ", ".join(display_parts)
            
            new_item = self.paper_tree.insert("", "end", values=(i+1, title, authors, category_display))
            
            if self.current_paper_index == i:
                self.paper_tree.selection_set(new_item)
                self.paper_tree.see(new_item)
    
    def on_paper_selected(self, event):
        # 如果事件被屏蔽，直接返回
        if self._suppress_select_event:
            return

        selection = self.paper_tree.selection()
        if not selection:
            self.current_paper_index = -1
            self.show_placeholder()
            return
        
        item = selection[0]
        values = self.paper_tree.item(item, 'values')
        paper_index = int(values[0]) - 1
        
        if 0 <= paper_index < len(self.papers):
            self.current_paper_index = paper_index
            self.show_form()
            self.load_paper_to_form(self.papers[paper_index])
            self._validate_all_fields_visuals()
            self.update_status(f"正在编辑: {self.papers[paper_index].title[:30]}...")

    def load_paper_to_form(self, paper):
        """加载论文数据到表单"""
        self._disable_callbacks = True
        try:
            for variable, widget in self.form_fields.items():
                value = getattr(paper, variable, "")
                if value is None: value = ""
                
                if variable == 'category':
                    # 【修复：防闪烁核心】Category 增量更新逻辑
                    unique_names = [v.strip() for v in str(value).split(';') if v.strip()]
                    
                    # 获取当前已存在的行
                    current_rows = getattr(self, 'category_rows', [])
                    needed_rows = len(unique_names) if unique_names else 1
                    
                    # 1. 补齐行数 (如果不够)
                    while len(current_rows) < needed_rows:
                        # 参数无所谓，稍后会统一设置值
                        self._gui_add_category_row('')
                    
                    # 2. 删除多余行 (如果多了) - 从末尾删除
                    while len(current_rows) > needed_rows:
                        row_frame, _, _ = current_rows.pop()
                        row_frame.destroy()
                    
                    # 3. 更新所有行的值
                    for i in range(needed_rows):
                        uname = unique_names[i] if i < len(unique_names) else ""
                        display_name = self.category_reverse_mapping.get(uname, '')
                        # current_rows[i] 是 (row_frame, btn, combo)
                        _, _, combo = current_rows[i]
                        combo.set(display_name)
                
                elif isinstance(widget, ttk.Combobox):
                    widget.set(str(value) if value else "")

                elif isinstance(widget, tk.BooleanVar):
                    widget.set(bool(value))
                
                elif isinstance(widget, scrolledtext.ScrolledText):
                    widget.delete(1.0, tk.END)
                    widget.insert(1.0, str(value))
                    widget.edit_reset()
                
                elif isinstance(widget, tk.Entry):
                    widget.delete(0, tk.END)
                    widget.insert(0, str(value))
        finally:
            self._disable_callbacks = False
        

    def _on_field_change(self, variable, widget_or_var):
        if getattr(self, '_disable_callbacks', False):
            return
        
        if self.current_paper_index < 0:
            return

        new_value = ""
        if variable == 'category':
            pass
        elif isinstance(widget_or_var, tk.BooleanVar):
            new_value = widget_or_var.get()
        elif isinstance(widget_or_var, scrolledtext.ScrolledText):
            new_value = widget_or_var.get(1.0, tk.END).strip()
        elif isinstance(widget_or_var, ttk.Combobox):
            new_value = widget_or_var.get()
        elif isinstance(widget_or_var, tk.Entry):
            new_value = widget_or_var.get()
        
        current_paper = self.papers[self.current_paper_index]
        setattr(current_paper, variable, new_value)
        
        self._validate_single_field_visuals(variable)
        
        if variable in ['title', 'authors']:
            self._refresh_list_item(self.current_paper_index)

    def _on_category_change(self, variable=None, widget_or_var=None):
        if getattr(self, '_disable_callbacks', False):
            return
        if self.current_paper_index < 0:
            return

        unique_names = self._gui_get_category_values()
        cat_str = ";".join(unique_names)
        
        current_paper = self.papers[self.current_paper_index]
        current_paper.category = cat_str
        
        self._validate_single_field_visuals('category')
        self._refresh_list_item(self.current_paper_index)

    def _on_text_undo(self, event):
        try:
            event.widget.edit_undo()
            variable = None
            for var, w in self.form_fields.items():
                if w == event.widget:
                    variable = var
                    break
            if variable:
                self._on_field_change(variable, event.widget)
            return "break"
        except Exception:
            return "break"

    def _on_text_redo(self, event):
        try:
            event.widget.edit_redo()
            variable = None
            for var, w in self.form_fields.items():
                if w == event.widget:
                    variable = var
                    break
            if variable:
                self._on_field_change(variable, event.widget)
            return "break"
        except Exception:
            return "break"

    def _refresh_list_item(self, index):
        children = self.paper_tree.get_children()
        if index < len(children):
            paper = self.papers[index]
            item_id = children[index]
            
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            
            category_display = paper.category
            if hasattr(self, 'category_mapping') and paper.category:
                parts = [p.strip() for p in str(paper.category).split(';') if p.strip()]
                display_parts = []
                for p in parts:
                    disp = self.category_reverse_mapping.get(p)
                    if disp:
                        display_parts.append(disp)
                    else:
                        display_parts.append(p)
                category_display = ", ".join(display_parts)
            
            self.paper_tree.item(item_id, values=(index+1, title, authors, category_display))

    def _validate_single_field_visuals(self, variable):
        if self.current_paper_index < 0: return
        paper = self.papers[self.current_paper_index]
        
        is_valid, _, _ = paper.validate_paper_fields(
            self.config,
            check_required=True,
            check_non_empty=True,
            variable=variable,
            no_normalize=True
        )
        
        tag_config = self.config.get_tag_by_variable(variable)
        is_required = tag_config.get('required', False) if tag_config else False
        
        val = getattr(paper, variable, "")
        if variable == 'category':
            is_empty = not val
        else:
            is_empty = (val is None or str(val).strip() == "" or str(val) == self.PLACEHOLDER)
        
        self._apply_widget_style(variable, is_valid, is_required, is_empty)

    def _validate_all_fields_visuals(self, variable=None, widget_or_var=None):
        if self.current_paper_index < 0: return
        paper = self.papers[self.current_paper_index]
        
        _, _, invalid_vars = paper.validate_paper_fields(
            self.config,
            check_required=True,
            check_non_empty=True,
            no_normalize=True
        )
        
        invalid_set = set(invalid_vars)
        
        for variable in self.form_fields.keys():
            tag_config = self.config.get_tag_by_variable(variable)
            is_required = tag_config.get('required', False) if tag_config else False
            
            val = getattr(paper, variable, "")
            if variable == 'category':
                is_empty = not val
            else:
                is_empty = (val is None or str(val).strip() == "" or str(val) == self.PLACEHOLDER)
            
            is_valid = (variable not in invalid_set)
            self._apply_widget_style(variable, is_valid, is_required, is_empty)

    def _apply_widget_style(self, variable, is_valid, is_required, is_empty):
        widget = self.field_widgets.get(variable)
        if not widget: return

        bg_color = self.color_normal
        
        if is_required and is_empty:
            bg_color = self.color_required_empty
        elif not is_valid and not is_empty:
            bg_color = self.color_invalid
        
        try:
            if isinstance(widget, scrolledtext.ScrolledText):
                widget.config(background=bg_color)
            elif isinstance(widget, tk.Entry):
                widget.config(background=bg_color)
            elif isinstance(widget, ttk.Combobox):
                style_name = "TCombobox"
                if bg_color == self.color_invalid:
                    style_name = "Invalid.TCombobox"
                elif bg_color == self.color_required_empty:
                    style_name = "Required.TCombobox"
                widget.configure(style=style_name)
        except Exception:
            pass

    def add_paper(self):
        """添加新论文"""
        placeholder_data = {
            'title': self.PLACEHOLDER,
            'authors': self.PLACEHOLDER,
            'category': '',
            'doi': '',
            'paper_url': '',
            'project_url': '',
            'conference': '',
            'contributor': '',
            'notes': '',
            'status': ''
        }
        try:
            placeholder = Paper.from_dict(placeholder_data)
        except Exception:
            placeholder = Paper.from_dict({'title': self.PLACEHOLDER})
            
        self.papers.append(placeholder)
        self.update_paper_list()
        
        new_index = len(self.papers) - 1
        children = self.paper_tree.get_children()
        
        self.current_paper_index = new_index

        # 设置事件抑制标志，防止 selection_set 触发 on_paper_selected 造成重复加载
        self._suppress_select_event = True
        if new_index < len(children):
            self.paper_tree.selection_set(children[new_index])
            self.paper_tree.see(children[new_index])
        self._suppress_select_event = False

        # 手动顺序执行加载和显示，避免布局震荡
        self.load_paper_to_form(placeholder)
        self.show_form()
        
        self._validate_all_fields_visuals()
        self.update_status("已创建新论文，请在右侧编辑")
        
        self.root.update_idletasks()
        
        target_widget = None
        for key, widget in self.form_fields.items():
            if isinstance(widget, (tk.Entry, ttk.Combobox, scrolledtext.ScrolledText)):
                target_widget = widget
                break
        
        if target_widget:
            try:
                target_widget.focus_force()
            except Exception:
                pass
    
    def delete_paper(self):
        if self.current_paper_index < 0:
            messagebox.showwarning("警告", "请先选择一篇论文")
            return
        
        if messagebox.askyesno("确认", "确定要删除这篇论文吗？"):
            del self.papers[self.current_paper_index]
            self.current_paper_index = -1
            self.update_paper_list()
            self.show_placeholder()
            self.update_status("论文已删除")
    
    def clear_papers(self):
        if not self.papers:
            return
        if messagebox.askyesno("警告", "警告！确定要清空所有论文吗？\n\n⚠️ 这将丢失目前已添加的所有论文！"):
            if messagebox.askyesno("警告", "二次警告！确定要清空所有论文吗？\n\n⚠️ 这将丢失目前已添加的所有论文！"):
                self.papers = []
                self.current_paper_index = -1
                self.update_paper_list()
                self.show_placeholder()
                self.update_status("所有论文已清空")
    
    def save_all_papers(self):
        if not self.papers:
            messagebox.showwarning("警告", "没有论文可以保存")
            return False
        
        invalid_papers = []
        for i, paper in enumerate(self.papers):
             valid, errors, _ = paper.validate_paper_fields(
                self.config,
                check_required=True,
                check_non_empty=True,
                no_normalize=False
            )
             if not valid:
                 invalid_papers.append((i+1, paper.title[:50], errors[:2]))

        if invalid_papers:
            error_msg = "保存被阻止！列表中发现验证失败的论文:\n\n"
            for idx, title, errors in invalid_papers:
                error_msg += f"#{idx} {title}...\n   - {', '.join(errors)}\n"
            
            error_msg += "\n请在左侧列表中选择对应论文，修正红色标记的字段后再保存。"
            messagebox.showerror("验证错误", error_msg)
            return False

        target_path = filedialog.asksaveasfilename(
            title="选择保存到的更新文件（JSON）",
            defaultextension='.json',
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialfile='submit_template.json',
            initialdir=BASE_DIR
        )

        if not target_path:
            self.update_status("保存已取消")
            return False

        existing_papers = []
        try:
            if os.path.exists(target_path):
                existing_papers = self.update_utils.load_papers_from_json(target_path, skip_invalid=False)
        except Exception as e:
            messagebox.showerror("错误", f"读取现有JSON文件失败: {e}")
            return False

        merged_papers = list(existing_papers)
        existing_map = {}
        for p in existing_papers:
            key = p.get_key()
            existing_map[key] = p

        for paper in self.papers:
            paper.doi = clean_doi(paper.doi, self.conflict_marker) if paper.doi else ""
            paper.category = self.update_utils.normalize_category_value(paper.category, self.config)
            
            key = paper.get_key()
            if key in existing_map:
                existing_p = existing_map[key]
                msg = f"论文已存在于更新文件中:\n\n标题: {paper.title}\nDOI: {paper.doi}\n\n是否覆盖原有条目？"
                choice = messagebox.askyesnocancel("发现重复论文", msg)
                
                if choice is None:
                    self.update_status("保存操作已取消")
                    return False
                elif choice:
                    for i, mp in enumerate(merged_papers):
                        if is_same_identity(mp, paper):
                            merged_papers[i] = paper
                            break
            else:
                merged_papers.append(paper)

        try:
            self.update_utils.save_papers_to_json(target_path, merged_papers, skip_invalid=False)
        except Exception as e:
            messagebox.showerror("错误", f"保存JSON文件失败: {e}")
            return False
        
        messagebox.showinfo("成功", f"成功保存 {len(merged_papers)} 篇论文到更新文件:\n{target_path}")
        self.update_status(f"已更新文件: {target_path}")
        return True
    
    def submit_pr(self):
        if not messagebox.askyesno("须知", f"将自动通过pull request提交论文...\n\n1.若当前在main分支，将创建新分支提交PR；\n2.提交PR后将切回原分支；\n3.收到PR后github action将自动读取submit_template.xlsx和submit_template.json中的论文进行更新\n"):
            return
        
        if not os.path.exists(self.update_json_path):
             if messagebox.askyesno("确认", "注意！是否保存当前所有论文？如果否，当前工作区内容将不会提交PR"):
                if self.save_all_papers()==False:
                    return

        if not messagebox.askyesno("确认", f"确定要提交submit_template.xlsx和submit_template.json中的论文吗？"):
            return
        
        def submit_thread():
            try:
                import subprocess
                import time
                
                try:
                    subprocess.run(["git", "--version"], check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    raise Exception("Git未安装！")
                
                result = subprocess.run(["git", "branch", "--show-current"], 
                                       capture_output=True, text=True, cwd=BASE_DIR)
                current_branch = result.stdout.strip()
                original_branch = current_branch
                created_new_branch = False
                
                if current_branch == "main":
                    branch_name = f"paper-submission-{int(time.time())}"
                    try:
                        subprocess.run(["git", "checkout", "-b", branch_name], 
                                      check=True, capture_output=True, text=True, cwd=BASE_DIR)
                        created_new_branch = True
                        self.root.after(0, lambda: self.update_status(f"已创建并切换到新分支: {branch_name}"))
                    except subprocess.CalledProcessError as e:
                        raise Exception(f"创建分支失败: {e.stderr}")
                else:
                    branch_name = current_branch
                have_update_files = False
                try:
                    if os.path.exists(self.update_json_path):
                        have_update_files = True
                        subprocess.run(["git", "add", self.update_json_path], 
                                     check=True, capture_output=True, cwd=BASE_DIR)
                    if os.path.exists(self.update_excel_path):
                        have_update_files = True
                        subprocess.run(["git", "add", self.update_excel_path], 
                                     check=True, capture_output=True, cwd=BASE_DIR)
                    if not have_update_files:
                        raise Exception("没有找到可提交的更新文件！本次PR不会有任何论文更新") 
                    subprocess.run(["git", "commit", "-m", f"Add {len(self.papers)} papers via GUI"], 
                                   check=True, capture_output=True, cwd=BASE_DIR)
                    self.root.after(0, lambda: self.update_status("已提交更改到本地仓库"))
                except subprocess.CalledProcessError as e:
                    raise Exception(f"提交更改失败: {e.stderr}")
                
                try:
                    subprocess.run(["git", "push", "origin", branch_name], 
                                 check=True, capture_output=True, text=True, cwd=BASE_DIR)
                    self.root.after(0, lambda: self.update_status(f"已推送到远程分支: {branch_name}"))
                except subprocess.CalledProcessError as e:
                    raise Exception(f"推送失败: {e.stderr}")
                
                try:
                    pr_title = f"论文提交: {len(self.papers)} 篇新论文"
                    pr_body = f"通过GUI提交了 {len(self.papers)} 篇论文。"
                    
                    try:
                        subprocess.run(["gh", "--version"], check=True, capture_output=True)
                        use_gh = True
                    except: use_gh = False

                    if use_gh:
                        result = subprocess.run(
                            ["gh", "pr", "create", "--base", "main", "--head", branch_name,
                             "--title", pr_title, "--body", pr_body],
                            capture_output=True, text=True, cwd=BASE_DIR
                        )
                        if result.returncode == 0:
                            pr_url = result.stdout.strip()
                            self.root.after(0, lambda: self.show_pr_result(pr_url))
                        else:
                            raise Exception(f"GitHub CLI创建PR失败: {result.stderr}")
                    else:
                        self.root.after(0, lambda: self.show_github_cli_guide(branch_name))

                except Exception as e:
                    if "GitHub CLI" in str(e):
                        self.root.after(0, lambda: self.show_github_cli_guide(branch_name))
                    else:
                        self.root.after(0, lambda: self.show_pr_result(""))

                if created_new_branch:
                    subprocess.run(["git", "checkout", original_branch], check=True, capture_output=True, text=True, cwd=BASE_DIR)

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("提交失败", f"{str(e)}"))
                self.root.after(0, lambda: self.update_status("提交失败"))
        
        threading.Thread(target=submit_thread, daemon=True).start()
    
    def show_github_cli_guide(self, branch_name):
        guide = f"请打开项目的github页面，按照引导手动创建PR。分支: {branch_name}"
        messagebox.showinfo("手动创建PR指引", guide)

    def show_pr_result(self, pr_url=None):
        result_window = tk.Toplevel(self.root)
        result_window.title("PR提交结果")
        result_window.geometry("600x400")
        msg = f"PR链接: {pr_url}" if pr_url else "代码已推送，请手动创建PR"
        lbl = ttk.Label(result_window, text=msg, wraplength=500)
        lbl.pack(pady=20)
        
    def load_template(self):
        filepath = filedialog.askopenfilename(
            title="选择模板文件",
            filetypes=[("Excel和JSON文件", "*.xlsx *.json"), ("Excel文件", "*.xlsx"), ("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if not filepath: return
        
        if self.papers:
            choice = messagebox.askyesnocancel("确认", "注意！是否保存当前所有论文？如果否，当前所有内容会丢失")
            if choice is None:
                return
            elif choice:
                    if self.save_all_papers()==False: return
            else:
                if messagebox.askyesno("二次确认", "二次确认！是否要保存当前论文后再加载新模板？\n\n⚠️ 如果选择否，当前所有内容会丢失！"):
                    if self.save_all_papers()==False: return
        try:
            if filepath.endswith('.json'):
                data = self.update_utils.read_json_file(filepath)
                if data and 'papers' in data:
                    self.papers = []
                    for paper_data in data['papers']:
                        self.papers.append(Paper.from_dict(paper_data))
            elif filepath.endswith('.xlsx'):
                try: import pandas as pd
                except: return
                df = pd.read_excel(filepath, engine='openpyxl')
                self.papers = self.update_utils.excel_to_paper(df, only_non_system=True)
            
            self.update_paper_list()
            self.current_paper_index = -1
            self.show_placeholder()
            messagebox.showinfo("成功", f"已加载 {len(self.papers)} 篇论文")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载模板失败: {e}")

    def on_closing(self):
        if self.papers:
            choice = messagebox.askyesnocancel("确认", "注意！是否保存当前所有论文？如果否，当前所有内容会丢失")
            if choice is None:
                return
            elif choice:
                if self.save_all_papers()==False: return
            else:
                if messagebox.askyesno("二次确认", "二次确认！是否要保存当前所有论文后再关闭程序？\n\n⚠️ 如果否，当前所有内容会丢失"):
                    if self.save_all_papers()==False: return
        self.root.destroy()

    # ================= Zotero 交互相关 =================
    
    def _show_zotero_input_dialog(self, title: str) -> Optional[str]:
        """弹出Zotero JSON输入对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("600x400")
        
        # 布局
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        
        lbl = ttk.Label(dialog, text="请粘贴Zotero导出的元数据JSON (支持单个对象或列表):", padding=10)
        lbl.grid(row=0, column=0, sticky="w")
        
        # 帮助按钮
        def show_help():
            msg = (
		        "How to Obtain Zotero Meta JSON?/如何获取Zotero Meta JSON?\n\n"
                "1. It is recommended to use the specially developed Zotero plugin 'One-Click Copy Metadata'\n"
                "You can get One-Click Copy Metadata.xpi from the tools folder of the project).\n"
                "The download link can also be found in the README on the GitHub homepage.\n"
                "2. After installation, right-click the item -> ==Copy Meta to JSON Format==. The required metadata will be copied to the clipboard\n\n"
                "Note: You can also manually export CSL JSON format from Zotero. (Not recommended due to incomplete data)\n\n"
                "Supports single item {...} or item list [...]\n\n"
                "1. 推荐使用特意开发的zotero插件'One-Click Copy Metadata'\n"
		        "可从项目的tools文件夹拿到One-Click Copy Metadata.xpi）。\n"
		        "也可在github主页面的readme中找到下载链接。\n"
                "2. 安装后右键点击条目 -> ==Copy Meta to JSON Format==。就会将所需meta数据拷贝到剪贴板\n\n"
                "注：也可以手动从Zotero导出为CSL JSON格式。（因数据不完全，不推荐）\n\n"
                "支持单个条目 {...} 或 条目列表 [...]"
            )
            messagebox.showinfo("获取帮助", msg, parent=dialog)
            
        help_btn = ttk.Button(dialog, text="❓", width=3, command=show_help)
        help_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=5)

        text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=15)
        text_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=2, column=0, pady=10)
        
        result_container = {"data": None}
        
        def on_confirm():
            content = text_area.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("提示", "输入内容为空", parent=dialog)
                return
            result_container["data"] = content
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
            
        confirm_btn = ttk.Button(btn_frame, text="✅ 确定", command=on_confirm)
        confirm_btn.pack(side=tk.LEFT, padx=10)
        
        cancel_btn = ttk.Button(btn_frame, text="❌ 取消", command=on_cancel)
        cancel_btn.pack(side=tk.LEFT, padx=10)
        
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)
        
        return result_container["data"]

    def add_from_zotero_meta(self):
        """从Zotero Meta批量新建论文"""
        json_str = self._show_zotero_input_dialog("从Zotero Meta新建论文")
        if not json_str:
            return
            
        new_papers = self.zotero_processor.process_meta_data(json_str)
        if not new_papers:
            messagebox.showwarning("提示", "未解析到有效的Zotero数据")
            return
            
        self.papers.extend(new_papers)
        self.update_paper_list()
        
        # 选中最后一个新增的
        new_index = len(self.papers) - 1
        children = self.paper_tree.get_children()
        
        self.current_paper_index = new_index
        self._suppress_select_event = True
        if new_index < len(children):
            self.paper_tree.selection_set(children[new_index])
            self.paper_tree.see(children[new_index])
        self._suppress_select_event = False
        
        self.load_paper_to_form(self.papers[new_index])
        self.show_form()
        self._validate_all_fields_visuals()
        
        messagebox.showinfo("成功", f"已添加 {len(new_papers)} 篇论文")
        self.update_status(f"已批量添加 {len(new_papers)} 篇论文")

    def fill_from_zotero_meta(self):
        """填充当前表单"""
        if self.current_paper_index < 0:
            messagebox.showwarning("提示", "请先在左侧选择要填充的论文条目")
            return
            
        json_str = self._show_zotero_input_dialog("填充当前表单")
        if not json_str:
            return

        new_papers = self.zotero_processor.process_meta_data(json_str)
        if not new_papers:
            messagebox.showwarning("提示", "未解析到有效的Zotero数据")
            return
            
        source_paper = new_papers[0]
        target_paper = self.papers[self.current_paper_index]
        
        conflicts = []
        fields_to_update = []
        
        # 跳过系统字段
        system_fields = [t["variable"] for t in get_config_instance().get_system_tags()]
        for field in source_paper.__dataclass_fields__:
            if field in ['invalid_fields', 'is_placeholder'] or field in system_fields:
                continue
            val = getattr(source_paper, field)
            if val:
                target_val = getattr(target_paper, field)
                fields_to_update.append((field, val))
                # 只要 target_val 非空且非 PLACEHOLDER，才算冲突
                if target_val and str(target_val).strip() and str(target_val).strip() != self.PLACEHOLDER:
                    conflicts.append(field)
        
        if not fields_to_update:
             messagebox.showinfo("提示", "Zotero数据中没有有效内容可填充")
             return

        overwrite_mode = True # 默认覆盖
        
        if conflicts:
            msg = f"检测到 {len(conflicts)} 个字段已有内容（如 {conflicts[0]} 等）。\n\n是否覆盖已有内容？\n\n是(Yes): 覆盖所有字段\n否(No): 仅填充空白字段 (保留已有内容)\n取消(Cancel): 取消操作"
            choice = messagebox.askyesnocancel("覆盖确认", msg)
            
            if choice is None: # Cancel
                return
            elif choice is False: # No
                overwrite_mode = False
            # Yes -> overwrite_mode = True
            
        # 执行更新
        updated_count = 0
        for field, val in fields_to_update:
            target_val = getattr(target_paper, field)
            if overwrite_mode or (not target_val or not str(target_val).strip()):
                 setattr(target_paper, field, val)
                 updated_count += 1
                
        # 刷新UI
        self.load_paper_to_form(target_paper)
        self._validate_all_fields_visuals()
        self._refresh_list_item(self.current_paper_index)
        
        self.update_status(f"已从Zotero数据更新 {updated_count} 个字段")


def main():
    root = tk.Tk()
    app = PaperSubmissionGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()