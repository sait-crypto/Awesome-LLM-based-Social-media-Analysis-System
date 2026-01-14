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

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity
from src.core.update_file_utils import get_update_file_utils
from src.utils import validate_figure, normalize_figure_path



from src.utils import (
    get_current_timestamp, 
    validate_url, 
    validate_doi, 
    clean_doi,
    validate_figure,
    normalize_figure_path,
)



class PaperSubmissionGUI:
    """论文提交图形界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Awesome 论文提交界面")
        self.root.geometry("1200x800")
        
        # 设置图标和主题
        self.root.tk.call('tk', 'scaling', 1.5)
        
        # 加载配置
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.update_utils = get_update_file_utils()
        
        
        # 论文列表
        self.papers = []  # 存储Paper对象
        self.current_paper_index = -1
        
        # 更新文件路径
        self.update_json_path = self.settings['paths']['update_json']
        self.update_excel_path = self.settings['paths']['update_excel']
        # 其他配置
        self.conflict_marker = self.settings['database']['conflict_marker']
        # 表单首次打开？
        self.first_open = True
        
        # 创建界面
        self.setup_ui()
        
        # 加载现有的更新文件（如果有）
        self.load_existing_updates()
        
        # 初始化tooltip
        self.tooltip = None
        # 内部标志：当程序性改变 selection 时，防止重复触发选择事件导致弹窗循环
        self._ignore_selection_event = False
    
    def setup_ui(self):
        """设置用户界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 标题
        title_label = ttk.Label(
            main_frame, 
            text="🎓 Awesome 论文提交界面",
            font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 创建左右两个主要区域
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=1, column=1, sticky="nsew")
        
        # 配置左右框架的网格权重
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)
        # 使右侧表单的第1行（canvas）和左侧列表在垂直方向上有相同的弹性
        right_frame.rowconfigure(1, weight=1)
        
        # 左侧：论文列表
        self.setup_paper_list_frame(left_frame)
        
        # 右侧：论文详情表单
        self.setup_paper_form_frame(right_frame)
        
        # 底部按钮
        self.setup_buttons_frame(main_frame)
        
        # 状态栏
        self.setup_status_bar(main_frame)

        # 绑定 Enter 键到保存操作（在多行文本框中按 Enter 保持换行）
        # 使用 root 绑定并在处理时判断焦点所在的控件类型，确保只有在表单字段时触发保存
        self.root.bind('<Return>', self._on_enter_pressed)
    
    def setup_paper_list_frame(self, parent):
        """设置论文列表框架"""
        # 列表标题
        list_title = ttk.Label(parent, text="📚 论文列表", font=("Arial", 12, "bold"))
        list_title.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # 论文列表框架
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew")
        
        # 配置网格权重
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 创建Treeview（列表）
        columns = ("序号", "标题", "作者", "分类")
        self.paper_tree = ttk.Treeview(
            list_frame, 
            columns=columns,
            show="headings",
            height=15
        )
        
        # 设置列标题
        for col in columns:
            self.paper_tree.heading(col, text=col)
            self.paper_tree.column(col, width=150)
        
        # 设置滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.paper_tree.yview)
        self.paper_tree.configure(yscrollcommand=scrollbar.set)
        
        # 网格布局
        self.paper_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 绑定选择事件
        self.paper_tree.bind('<<TreeviewSelect>>', self.on_paper_selected)
        # 支持鼠标滚轮在列表上滚动（Windows/Mac 和 X11）
        self.paper_tree.bind('<MouseWheel>', self._on_mousewheel_tree)
        self.paper_tree.bind('<Button-4>', self._on_mousewheel_tree)
        self.paper_tree.bind('<Button-5>', self._on_mousewheel_tree)
        
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
        # 表单标题
        form_title = ttk.Label(parent, text="📝 论文详情", font=("Arial", 12, "bold"))
        form_title.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # 创建Canvas和滚动条
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        
        # 表单框架（放在Canvas中）
        self.form_frame = ttk.Frame(canvas)
        
        # 配置Canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.create_window((0, 0), window=self.form_frame, anchor=tk.NW)

        # 保存 canvas 引用并绑定鼠标滚轮事件（Windows/Mac 使用 <MouseWheel>，X11 使用 Button-4/5）
        self.form_canvas = canvas
        canvas.bind('<MouseWheel>', self._on_mousewheel_canvas)
        canvas.bind('<Button-4>', self._on_mousewheel_canvas)
        canvas.bind('<Button-5>', self._on_mousewheel_canvas)

        # 网格布局
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        
        # 配置网格权重
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # 绑定Canvas大小变化事件
        self.form_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # 创建表单字段
        self.create_form_fields()
    
    def create_form_fields(self):
        """创建表单字段"""
        row = 0
        
        # 获取激活的标签
        active_tags = self.config.get_active_tags()
        
        # 创建字段字典
        self.form_fields = {}
        
        for tag in active_tags:
            if not tag.get('show_in_readme', True) and tag.get('variable') not in [
                'doi', 'title', 'authors', 'date', 'category',
                'paper_url', 'project_url', 'abstract'
            ]:
                continue
            
            variable = tag['variable']
            display_name = tag['display_name']
            description = tag.get('description', '')
            required = tag.get('required', False)
            field_type = tag.get('type', 'string')
            
            # 标签
            label_text = f"{display_name}:"
            if required:
                label_text = f"* {label_text}"
            
            label = ttk.Label(self.form_frame, text=label_text)
            # 默认左对齐，若是多行文本（如 abstract）则顶部对齐
            label_sticky = tk.W
            if field_type == 'text' and variable == 'abstract':
                label_sticky = tk.NW
            
            label.grid(row=row, column=0, sticky=label_sticky, pady=(10, 5))
            
            # 工具提示
            if description:
                self.create_tooltip(label, description)
            
            # 输入字段
            if field_type == 'enum' and variable == 'category':
                # 分类下拉框
                combo = ttk.Combobox(self.form_frame, state="readonly")
                combo.grid(row=row, column=1, sticky="we", pady=(10, 5), padx=(10, 0))
                
                # 设置分类选项
                categories = self.config.get_active_categories()
                category_names = [cat['name'] for cat in categories]
                category_values = [cat['unique_name'] for cat in categories]
                
                combo['values'] = category_names
                self.category_mapping = dict(zip(category_names, category_values))
                self.category_mapping[""] = "none"
                
                self.form_fields[variable] = combo
                
            elif field_type == 'bool':
                # 布尔值选择框
                var = tk.BooleanVar()
                checkbox = ttk.Checkbutton(self.form_frame, variable=var)
                checkbox.grid(row=row, column=1, sticky=tk.W, pady=(10, 5), padx=(10, 0))
                
                self.form_fields[variable] = var
                
            elif field_type == 'text':
                # 多行文本框
                text_frame = ttk.Frame(self.form_frame)
                # 对于多行文本，把 label 放到左上（占据左侧），输入区顶对齐
                text_frame.grid(row=row, column=1, sticky="we", pady=(10, 5), padx=(10, 0))
                 
                # 对 abstract 使用更大的高度以保证可见
                height = 8 if variable == 'abstract' else 5
                text_widget = scrolledtext.ScrolledText(text_frame, height=height, width=40)
                text_widget.grid(row=0, column=0, sticky="nsew")
                
                # 配置网格权重
                text_frame.columnconfigure(0, weight=1)
                text_frame.rowconfigure(0, weight=1)
                
                self.form_fields[variable] = text_widget
                # 当鼠标进入多行文本区域时，启用全局滚轮到 form 的绑定，离开时解绑
                text_widget.bind("<Enter>", lambda e: self._bind_form_scroll())
                text_widget.bind("<Leave>", lambda e: self._unbind_form_scroll())
            
            else:
                # 单行文本框
                entry = ttk.Entry(self.form_frame, width=50)
                entry.grid(row=row, column=1, sticky="we", pady=(10, 5), padx=(10, 0))
                
                self.form_fields[variable] = entry
            
            # 根据是否为多行文本调整label对齐
            if field_type == 'text':
                label.grid(row=row, column=0, sticky=tk.NW, pady=(10, 5))
            else:
                label.grid(row=row, column=0, sticky=label_sticky, pady=(10, 5))

            row += 1
        
        # 配置表单框架网格权重
        self.form_frame.columnconfigure(1, weight=1)
    
        # 鼠标进入整个 form_frame 时启用滚轮绑定，离开时解绑（确保在frame任意位置滚动都有效）
        self.form_frame.bind("<Enter>", lambda e: self._bind_form_scroll())
        self.form_frame.bind("<Leave>", lambda e: self._unbind_form_scroll())
    
    def _bind_form_scroll(self):
        """在鼠标悬停表单时绑定全局滚轮事件到 form 的滚动处理器"""
        try:
            self.root.bind_all("<MouseWheel>", self._on_mousewheel_canvas)
            self.root.bind_all("<Button-4>", self._on_mousewheel_canvas)
            self.root.bind_all("<Button-5>", self._on_mousewheel_canvas)
        except Exception:
            pass

    def _unbind_form_scroll(self):
        """在鼠标离开表单时解绑全局滚轮事件"""
        try:
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")
        except Exception:
            pass

    def create_tooltip(self, widget, text):
        """创建工具提示"""
        def enter(event):
            try:
                # 基于 widget 的屏幕坐标定位（兼容 Label、Button 等）
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
            tooltip = getattr(self, 'tooltip', None)
            if tooltip is not None:
                try:
                    tooltip.destroy()
                finally:
                    self.tooltip = None

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)
    
    def setup_buttons_frame(self, parent):
        """设置按钮框架"""
        buttons_frame = ttk.Frame(parent)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=(20, 10))
        
        # 保存当前论文按钮
        save_button = ttk.Button(
            buttons_frame,
            text="💾 保存当前论文",
            command=self.save_current_paper,
            width=20
        )
        save_button.grid(row=0, column=0, padx=5)
        
        # 清空表单按钮
        clear_form_button = ttk.Button(
            buttons_frame,
            text="🧹 清空表单",
            command=self.clear_form,
            width=20
        )
        clear_form_button.grid(row=0, column=1, padx=5)
        
        # 保存到更新文件按钮
        save_all_button = ttk.Button(
            buttons_frame,
            text="📤 保存到更新文件",
            command=self.save_all_papers,
            width=20
        )
        save_all_button.grid(row=0, column=2, padx=5)
        
        # 提交PR按钮
        submit_button = ttk.Button(
            buttons_frame,
            text="🚀 自动提交PR",
            command=self.submit_pr,
            width=20
        )
        submit_button.grid(row=0, column=3, padx=5)
        
        # 加载模板按钮
        load_template_button = ttk.Button(
            buttons_frame,
            text="📂 加载模板",
            command=self.load_template,
            width=20
        )
        load_template_button.grid(row=0, column=4, padx=5)
    
    def setup_status_bar(self, parent):
        """设置状态栏"""
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
        """更新状态栏"""
        self.status_var.set(message)
        self.root.update_idletasks()

    def _on_enter_pressed(self, event):
        """处理回车键：当焦点在表单字段（非多行文本）时，触发保存当前论文。"""
        try:
            focused = self.root.focus_get()
            if focused is None:
                return

            # 如果焦点在多行文本框（ScrolledText / Text），保留换行行为
            if isinstance(focused, scrolledtext.ScrolledText) or isinstance(focused, tk.Text):
                return

            # 仅当焦点位于表单的某个字段上时触发保存
            for variable, widget in self.form_fields.items():
                try:
                    if focused == widget or str(focused).startswith(str(widget)):
                        # 调用保存方法
                        self.save_current_paper()
                        # 阻止后续默认绑定（例如按钮激活等）
                        return "break"
                except Exception:
                    continue
        except Exception:
            # 保守处理：不让回车导致未处理的异常
            return

    def _on_mousewheel_tree(self, event):
        """处理列表（Treeview）的鼠标滚轮事件"""
        try:
            # Windows/Mac 使用 event.delta，X11 使用 event.num（4/5）
            if hasattr(event, 'delta'):
                delta = int(-1 * (event.delta / 120))
                if delta == 0:
                    delta = -1 if event.delta > 0 else 1
            else:
                delta = 1 if getattr(event, 'num', 5) == 5 else -1
            self.paper_tree.yview_scroll(delta, 'units')
            return "break"
        except Exception:
            return

    def _on_mousewheel_canvas(self, event):
        """处理表单 Canvas 的鼠标滚轮事件"""
        try:
            if not hasattr(self, 'form_canvas'):
                return
            if hasattr(event, 'delta'):
                delta = int(-1 * (event.delta / 120))
                if delta == 0:
                    delta = -1 if event.delta > 0 else 1
            else:
                delta = 1 if getattr(event, 'num', 5) == 5 else -1
            self.form_canvas.yview_scroll(delta, 'units')
            return "break"
        except Exception:
            return
    
    def load_existing_updates(self):
        """加载现有的更新文件"""
        if os.path.exists(self.update_json_path):
            try:
                self.papers.extend(self.update_utils.load_papers_from_json(self.update_json_path))
            
                self.update_paper_list()
                self.update_status(f"已从{self.update_json_path}加载 {len(self.papers)} 篇论文")
                messagebox.showinfo("须知",f"该界面用于:\n    1.生成json更新文件\n    2.自动分支并提交PR\n如果根目录中的submit_template.xlsx或submit_template.json已按规范填写内容，你可以手动提交PR或使用该界面自动分支并提交PR，您提交的内容会自动更新到仓库论文列表")

            except Exception as e:
                messagebox.showerror("错误", f"加载更新文件失败: {e}")
    
    def update_paper_list(self):
        """更新论文列表"""
        # 清空现有列表
        for item in self.paper_tree.get_children():
            self.paper_tree.delete(item)
        
        # 添加论文到列表
        for i, paper in enumerate(self.papers):
            # 截断标题和作者
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            
            # 获取分类显示名
            category_display = paper.category
            if hasattr(self, 'category_mapping'):
                for display_name, unique_name in self.category_mapping.items():
                    if unique_name == paper.category:
                        category_display = display_name
                        break
            
            self.paper_tree.insert("", "end", values=(i+1, title, authors, category_display))
    
    def on_paper_selected(self, event):
        """当论文被选中时"""
        selection = self.paper_tree.selection()
        if not selection:
            return
        
        # 检查重入保护（用于程序性修改 selection 时避免重复触发）
        if getattr(self, '_ignore_selection_event', False):
            return

        # 获取当前表单中的论文（如果有正在编辑的）
        if self.current_paper_index >= 0 and self.current_paper_index < len(self.papers):
            # 保存当前编辑的论文
            if not self.save_current_paper():
                # 如果保存失败，恢复为之前的选择（如果存在），并暂时忽略选择事件
                children = self.paper_tree.get_children()
                prev_item = None
                if 0 <= self.current_paper_index < len(children):
                    prev_item = children[self.current_paper_index]
                if prev_item:
                    self._ignore_selection_event = True
                    self.paper_tree.selection_set(prev_item)
                    # 在短时间后恢复事件处理
                    self.root.after(50, lambda: setattr(self, '_ignore_selection_event', False))
                return
        
        # 获取选中的论文索引
        item = selection[0]
        values = self.paper_tree.item(item, 'values')
        paper_index = int(values[0]) - 1
        
        if 0 <= paper_index < len(self.papers):
            self.current_paper_index = paper_index
            self.load_paper_to_form(self.papers[paper_index])
    
    def load_paper_to_form(self, paper):
        """加载论文数据到表单"""
        # 遍历所有字段
        for variable, widget in self.form_fields.items():
            value = getattr(paper, variable, "")
            
            if value is None:
                value = ""
            
            # 根据widget类型设置值
            if isinstance(widget, ttk.Combobox):
                # 分类下拉框
                if variable == 'category':
                    # 查找分类显示名
                    for display_name, unique_name in self.category_mapping.items():
                        if unique_name == value:
                            widget.set(display_name)
                            break
                    else:
                        widget.set("")
            
            elif isinstance(widget, tk.BooleanVar):
                # 复选框
                widget.set(bool(value))
            
            elif isinstance(widget, scrolledtext.ScrolledText):
                # 多行文本框
                widget.delete(1.0, tk.END)
                widget.insert(1.0, str(value))
            
            else:
                # 单行文本框
                widget.delete(0, tk.END)
                widget.insert(0, str(value))
    
    def get_paper_from_form(self) -> Optional[Paper]:
        """从表单获取论文数据"""
        paper_data = {}
        
        # 遍历所有字段
        for variable, widget in self.form_fields.items():
            if isinstance(widget, ttk.Combobox):
                # 分类下拉框
                if variable == 'category':
                    display_name = widget.get()
                    unique_name = self.category_mapping.get(display_name, "")
                    paper_data[variable] = unique_name
                else:
                    paper_data[variable] = widget.get()
            
            elif isinstance(widget, tk.BooleanVar):
                # 复选框
                paper_data[variable] = widget.get()
            
            elif isinstance(widget, scrolledtext.ScrolledText):
                # 多行文本框
                paper_data[variable] = widget.get(1.0, tk.END).strip()
            
            else:
                # 单行文本框
                paper_data[variable] = widget.get()
        
        # 创建Paper对象
        try:
            paper = Paper.from_dict(paper_data)
            
            # 设置提交时间
            if not paper.submission_time:
                paper.submission_time = get_current_timestamp()
            
            # 设置默认贡献者
            if not paper.contributor:
                paper.contributor = self.settings['database']['default_contributor']
            
            return paper
        except Exception as e:
            messagebox.showerror("错误", f"创建论文对象失败: {e}")
            return None
    
    def add_paper(self):
        """添加新论文（仅创建占位条目，不切换选择，不清空表单）"""
        PLACEHOLDER = "to be filled in"

        # 若已有占位条目，则不重复创建
        for p in self.papers:
            try:
                if getattr(p, 'title', '') == PLACEHOLDER:
                    messagebox.showinfo("提示", "已有占位论文，请在列表中选中并填写")
                    return
            except Exception:
                continue

        # 创建占位论文（仅为列表显示填写基本字段）
        placeholder_data = {
            'title': PLACEHOLDER,
            'authors': PLACEHOLDER,
            'category': PLACEHOLDER,
            'doi': '',
            'paper_url': '',
            'project_url': '',
        }
        try:
            placeholder = Paper.from_dict(placeholder_data)
        except Exception:
            # 回退：仅设置必需字段
            placeholder = Paper.from_dict({'title': PLACEHOLDER, 'authors': PLACEHOLDER})

        # 插入占位条目，不改变当前 selection / 表单
        old_index = self.current_paper_index
        self.papers.append(placeholder)
        self.update_paper_list()

        # 恢复之前的选择（若存在）
        if old_index is not None and old_index >= 0 and old_index < len(self.papers):
            children = self.paper_tree.get_children()
            if children and old_index < len(children):
                self.paper_tree.selection_set(children[old_index])

        self.update_status("已创建占位论文：请在列表中选择占位项并填写信息")
    
    def save_current_paper(self):
        """保存当前论文"""
        if self.first_open:
            self.first_open = False
            #return True
        
        paper = self.get_paper_from_form()
        if paper is None:
            return False
        if not paper:
            return False
        
        
        # 验证论文字段 - 使用统一验证函数
        valid, errors = paper.validate_paper_fields(
            self.config,
            check_required=True,
            check_non_empty=True
        )
        
        if not valid:
            # 还原原来的弹窗逻辑
            error_msg = "以下字段验证失败:\n\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n...以及其他 {len(errors)-5} 个错误"
            messagebox.showerror("错误", error_msg)
            return False
        
        # 获取当前选择的列表项（如果有）
        current_selection = self.paper_tree.selection()
        
        if self.current_paper_index >= 0:
            # 更新现有论文
            self.papers[self.current_paper_index] = paper
            
            # 更新列表中的显示
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            
            # 获取分类显示名
            category_display = paper.category
            if hasattr(self, 'category_mapping'):
                for display_name, unique_name in self.category_mapping.items():
                    if unique_name == paper.category:
                        category_display = display_name
                        break
            
            # 更新Treeview中的对应行
            children = self.paper_tree.get_children()
            if self.current_paper_index < len(children):
                item_id = children[self.current_paper_index]
                self.paper_tree.item(item_id, values=(self.current_paper_index + 1, title, authors, category_display))
            
            # 重新选中之前的项（如果存在）
            if current_selection:
                # 使用重入保护，防止selection_set触发 on_paper_selected 导致重复保存/弹窗
                self._ignore_selection_event = True
                self.paper_tree.selection_set(current_selection)
                self.root.after(50, lambda: setattr(self, '_ignore_selection_event', False))
            
            self.update_status(f"论文已更新: {paper.title[:30]}...")
            
        else:
            # 添加新论文
            self.papers.append(paper)
            self.current_paper_index = len(self.papers) - 1
            
            # 准备显示值
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            authors = paper.authors[:30] + "..." if len(paper.authors) > 30 else paper.authors
            
            # 获取分类显示名
            category_display = paper.category
            if hasattr(self, 'category_mapping'):
                for display_name, unique_name in self.category_mapping.items():
                    if unique_name == paper.category:
                        category_display = display_name
                        break
            
            # 在列表末尾添加新项
            item_id = self.paper_tree.insert("", "end", values=(len(self.papers), title, authors, category_display))
            
            # 选中新添加的项
            self.paper_tree.selection_set(item_id)
            
            self.update_status(f"论文已添加: {paper.title[:30]}...")
        
        self.update_status(f"已保存论文: {paper.title[:30]}...")
        return True
    
    def delete_paper(self):
        """删除当前论文"""
        if self.current_paper_index < 0:
            messagebox.showwarning("警告", "请先选择一篇论文")
            return
        
        if messagebox.askyesno("确认", "确定要删除这篇论文吗？"):
            del self.papers[self.current_paper_index]
            self.current_paper_index = -1
            self.clear_form()
            self.update_paper_list()
            self.update_status("论文已删除")
    
    def clear_papers(self):
        """清空所有论文"""
        if not self.papers:
            return
        
        if messagebox.askyesno("确认", "确定要清空所有论文吗？\n\n⚠️ 这将删除所有已添加的论文！"):
            self.papers = []
            self.current_paper_index = -1
            self.clear_form()
            self.update_paper_list()
            self.update_status("所有论文已清空")
    
    def clear_form(self):
        """清空表单"""
        for variable, widget in self.form_fields.items():
            if isinstance(widget, ttk.Combobox):
                widget.set("")
            elif isinstance(widget, tk.BooleanVar):
                widget.set(False)
            elif isinstance(widget, scrolledtext.ScrolledText):
                widget.delete(1.0, tk.END)
            else:
                widget.delete(0, tk.END)
        
        self.current_paper_index = -1
         # 取消列表选择
        self.paper_tree.selection_remove(self.paper_tree.selection())

    def save_all_papers(self):
        """保存所有论文到更新文件（增量更新模式）"""
        if not self.papers:
            messagebox.showwarning("警告", "没有论文可以保存")
            return False
        
        # 1. 先保存当前正在编辑的论文（如果存在）
        if not self.save_current_paper():
            return False
        
        

        # 2. 读取现有JSON文件内容
        existing_papers = []
        try:
            if os.path.exists(self.update_json_path):
                existing_papers = self.update_utils.load_papers_from_json(self.update_json_path)
        except Exception as e:
            messagebox.showerror("错误", f"读取现有JSON文件失败: {e}")
            return False

        # 3. 逐条处理合并与冲突
        merged_papers = list(existing_papers) # 创建副本
        
        # 建立现有论文的快速查找映射 (Key -> Paper)
        existing_map = {}
        for p in existing_papers:
            key = p.get_key()
            existing_map[key] = p

        for paper in self.papers:
            # 清理doi
            paper.doi = clean_doi(paper.doi, self.conflict_marker) if paper.doi else ""
            
            key = paper.get_key()
            
            if key in existing_map:
                # 发现冲突，弹窗询问
                existing_p = existing_map[key]
                msg = f"论文已存在于更新文件中:\n\n标题: {paper.title}\nDOI: {paper.doi}\n\n是否覆盖原有条目？\n\n- 是(Yes): 覆盖旧条目\n- 否(No): 跳过此条目（保留旧的）\n- 取消(Cancel): 停止保存操作"
                
                choice = messagebox.askyesnocancel("发现重复论文", msg)
                
                if choice is None: # Cancel
                    self.update_status("保存操作已取消")
                    return False
                elif choice: # Yes, Overwrite
                    # 在 merged_papers 中找到并替换
                    for i, mp in enumerate(merged_papers):
                        if is_same_identity(mp, paper):
                            merged_papers[i] = paper
                            break
                else: # No, Skip
                    continue
            else:
                # 新论文，直接添加
                merged_papers.append(paper)

        # 4. 统一验证最终列表
        invalid_papers = []
        for i, paper in enumerate(merged_papers):
             valid, errors = paper.validate_paper_fields(
                self.config,
                check_required=True,
                check_non_empty=True
            )
             if not valid:
                 invalid_papers.append((i+1, paper.title[:50], errors[:2]))

        if invalid_papers:
            error_msg = "保存被阻止！合并后的列表中发现验证失败的论文:\n\n"
            for idx, title, errors in invalid_papers:
                error_msg += f"#{idx} {title}...\n   - {', '.join(errors)}\n"
            
            error_msg += "\n请检查并修正错误后再保存。"
            messagebox.showerror("验证错误", error_msg)
            return False

        # 5. 保存到文件 (使用新封装的方法，自动处理 meta)
        try:
            self.update_utils.save_papers_to_json(self.update_json_path, merged_papers)
        except Exception as e:
            messagebox.showerror("错误", f"保存JSON文件失败: {e}")
            return False
        
        messagebox.showinfo("成功", f"成功保存 {len(merged_papers)} 篇论文到更新文件")
        self.update_status(f"已更新文件: {self.update_json_path}")
        return True
    
    def submit_pr(self):
        """提交PR（模拟）"""
        messagebox.showinfo("须知", f"将自动通过pull request提交论文，具体进行以下操作:\n  1.如果当前在main分支，将进行自动创建并切换到新分支\n  2.自动提交PR\n  3.如果根目录中的submit_template.xlsx或submit_template.json已按规范填写，且没有项目中任何其他更改，您提交的论文会自动更新到仓库论文列表\n  4. 提交完成后，程序会自动切回您之前所在的分支（不会保留本次临时分支）\n\n")
        
        # # 检查是否有论文
        # if not self.papers:
        #     messagebox.showwarning("警告", "两个submit_template文件中没有论文可以提交")
        #     return
        # 逻辑错误
        
        # 检查是否已保存
        if not os.path.exists(self.update_json_path):
            if  messagebox.askyesno("确认", "表单内容尚未保存到submit_template.json，是否先保存？取消保存将不会提交表单内容"):
                if self.save_all_papers()==False:
                    return

        # 确认提交
        if not messagebox.askyesno("确认", f"确定要提交submit_template.xlsx和submit_template.json中的论文吗？"):
            return
        
        # 在后台线程中执行
        def submit_thread():
            try:
                import subprocess
                import time
                
                # 1. 检查Git是否安装
                try:
                    subprocess.run(["git", "--version"], check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    raise Exception("Git未安装！请先安装Git：\nWindows: https://git-scm.com/download/win\nmacOS: brew install git\nLinux: sudo apt-get install git")
                
                # 2. 检查当前分支
                result = subprocess.run(["git", "branch", "--show-current"], 
                                       capture_output=True, text=True, cwd=os.getcwd())
                current_branch = result.stdout.strip()
                original_branch = current_branch
                created_new_branch = False
                
                # 3. 如果在main分支，创建新分支
                if current_branch == "main":
                    branch_name = f"paper-submission-{int(time.time())}"
                    try:
                        subprocess.run(["git", "checkout", "-b", branch_name], 
                                      check=True, capture_output=True, text=True, cwd=os.getcwd())
                        created_new_branch = True
                        self.root.after(0, lambda: self.update_status(f"已创建并切换到新分支: {branch_name}"))
                    except subprocess.CalledProcessError as e:
                        raise Exception(f"创建分支失败: {e.stderr}")
                else:
                    branch_name = current_branch
                    self.root.after(0, lambda: self.update_status(f"使用现有分支: {branch_name}"))
                
                # 4. 添加文件并提交
                try:
                    # 添加更新文件
                    subprocess.run(["git", "add", self.update_json_path], 
                                 check=True, capture_output=True, cwd=os.getcwd())
                    
                    # 如果有Excel文件也添加
                    if os.path.exists(self.update_excel_path):
                        subprocess.run(["git", "add", self.update_excel_path], 
                                     check=True, capture_output=True, cwd=os.getcwd())
                    
                    
                    self.root.after(0, lambda: self.update_status("已提交更改到本地仓库"))
                except subprocess.CalledProcessError as e:
                    raise Exception(f"提交更改失败: {e.stderr}")
                
                # 5. 推送到远程
                try:
                    subprocess.run(["git", "push", "origin", branch_name], 
                                 check=True, capture_output=True, text=True, cwd=os.getcwd())
                    self.root.after(0, lambda: self.update_status(f"已推送到远程分支: {branch_name}"))
                except subprocess.CalledProcessError as e:
                    raise Exception(f"推送失败: {e.stderr}\n\n请检查远程仓库配置，或手动执行: git push origin {branch_name}")
                
                # 6. 创建PR（尝试使用GitHub CLI 或 GitHub API）
                try:
                    pr_title = f"论文提交: {len(self.papers)} 篇新论文"
                    pr_body = f"通过GUI提交了 {len(self.papers)} 篇论文。\n\n包含论文:\n" + "\n".join([f"- {paper.title[:50]}..." for paper in self.papers[:5]])
                    if len(self.papers) > 5:
                        pr_body += f"\n...以及其他 {len(self.papers)-5} 篇论文"

                    # 1) 优先使用 GitHub CLI（gh）创建 PR
                    try:
                        subprocess.run(["gh", "--version"], check=True, capture_output=True)
                        use_gh = True
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        use_gh = False

                    if use_gh:
                        result = subprocess.run(
                            ["gh", "pr", "create", "--base", "main", "--head", branch_name,
                             "--title", pr_title, "--body", pr_body],
                            capture_output=True, text=True, cwd=os.getcwd()
                        )

                        if result.returncode == 0:
                            pr_url = result.stdout.strip()
                            # 某些 gh 版本会把链接放到 stderr 或 stdout，尝试从 stderr 获取备用
                            if not pr_url and result.stderr:
                                pr_url = result.stderr.strip()
                            self.root.after(0, lambda: self.show_pr_result(pr_url))
                        else:
                            # 如果 gh 可用但创建失败，抛出以便外层处理
                            raise Exception(f"GitHub CLI创建PR失败: {result.stderr}")

                    else:
                        # 2) 尝试使用 GITHUB_TOKEN 通过 GitHub REST API 创建 PR
                        import os as _os
                        token = _os.environ.get('GITHUB_TOKEN') or _os.environ.get('GH_TOKEN')
                        if token:
                            # 获取 origin 仓库信息 (owner/repo)
                            try:
                                r = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=os.getcwd())
                                repo_url = r.stdout.strip()
                                owner_repo = None
                                if repo_url.startswith('git@'):
                                    # git@github.com:owner/repo.git
                                    owner_repo = repo_url.split(':', 1)[1]
                                elif repo_url.startswith('https://') or repo_url.startswith('http://'):
                                    # https://github.com/owner/repo.git
                                    owner_repo = '/'.join(repo_url.split('/')[3:])
                                if owner_repo and owner_repo.endswith('.git'):
                                    owner_repo = owner_repo[:-4]

                                if not owner_repo:
                                    raise Exception('无法解析远程仓库地址来创建PR')

                                # 使用 requests 发起 API 请求
                                try:
                                    import requests
                                    api_url = f"https://api.github.com/repos/{owner_repo}/pulls"
                                    headers = {
                                        'Authorization': f'token {token}',
                                        'Accept': 'application/vnd.github+json'
                                    }
                                    payload = {
                                        'title': pr_title,
                                        'head': branch_name,
                                        'base': 'main',
                                        'body': pr_body
                                    }
                                    resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
                                    if resp.status_code in (200, 201):
                                        pr_url = resp.json().get('html_url', '')
                                        self.root.after(0, lambda: self.show_pr_result(pr_url))
                                    else:
                                        raise Exception(f"通过GitHub API创建PR失败: {resp.status_code} {resp.text}")
                                except Exception as e_api:
                                    raise Exception(f"尝试使用GitHub API创建PR失败: {e_api}")

                            except Exception as e_remote:
                                raise Exception(f"获取远程仓库信息失败: {e_remote}")

                        else:
                            # 3) 回退：给出手动创建的指引
                            repo_url = ""
                            try:
                                # 尝试获取远程仓库URL
                                result = subprocess.run(["git", "remote", "get-url", "origin"], 
                                                       capture_output=True, text=True, cwd=os.getcwd())
                                repo_url = result.stdout.strip()
                            except Exception:
                                repo_url = ""

                            if repo_url and "github.com" in repo_url:
                                # 将SSH URL转换为HTTPS URL
                                if repo_url.startswith("git@"):
                                    repo_url = repo_url.replace(":", "/").replace("git@", "https://")
                                    repo_url = repo_url.replace(".git", "")
                                manual_pr_url = f"{repo_url}/compare/main...{branch_name}?expand=1"
                                self.root.after(0, lambda: self.show_manual_pr_guide(branch_name, manual_pr_url))
                            else:
                                self.root.after(0, lambda: self.show_github_cli_guide(branch_name))

                except Exception as e:
                    # GitHub CLI相关错误
                    if "GitHub CLI" in str(e):
                        self.root.after(0, lambda: self.show_github_cli_guide(branch_name))
                    else:
                        self.root.after(0, lambda: self.show_pr_result(""))

                # 7. 切回原分支（如果我们创建了临时分支）
                try:
                    if created_new_branch:
                        subprocess.run(["git", "checkout", original_branch], check=True, capture_output=True, text=True, cwd=os.getcwd())
                        self.root.after(0, lambda: self.update_status(f"已切回原分支: {original_branch}"))
                except subprocess.CalledProcessError as e:
                    # 切回失败不致命，只提示
                    self.root.after(0, lambda: self.update_status(f"切回原分支失败: {str(e)}"))

                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("提交失败", f"{str(e)}"))
                self.root.after(0, lambda: self.update_status("提交失败"))
        
        threading.Thread(target=submit_thread, daemon=True).start()
    
    def show_github_cli_guide(self, branch_name):
        """显示GitHub CLI安装指引"""
        guide = f"""
GitHub CLI未安装或配置，无法自动创建PR。

请选择以下任一方式：

1. 安装GitHub CLI（推荐）:
   Windows: winget install --id GitHub.cli
   macOS: brew install gh
   Linux: 查看 https://github.com/cli/cli#installation

   安装后需要登录: gh auth login

2. 手动创建PR:
   a. 访问您的GitHub仓库页面
   b. 点击 "Compare & pull request"
   c. 选择 base: main  ←→ compare: {branch_name}
   d. 填写PR信息并提交

当前分支: {branch_name}
提交完成后本程序会自动切回您之前所在的分支（如果创建了临时分支）。
"""
        messagebox.showinfo("手动创建PR指引", guide)
        self.update_status("需要手动创建PR")
    
    def show_manual_pr_guide(self, branch_name, pr_url):
        """显示手动创建PR的指引"""
        guide = f"""
已成功推送分支 {branch_name}！

请手动创建Pull Request:

1. 打开链接创建PR:
   {pr_url}

2. 或者:
   a. 访问您的GitHub仓库
   b. 点击 "New pull request"
   c. 选择: base: main ←→ compare: {branch_name}
   d. 填写标题和描述
   e. 点击 "Create pull request"

提交的论文数: {len(self.papers)} 篇
\n提交完成后本程序会自动切回您之前所在的分支（如果创建了临时分支）。
"""
        messagebox.showinfo("创建Pull Request", guide)
        self.update_status(f"请手动创建PR: {branch_name}")
    
    def show_pr_result(self, pr_url=None):
        """显示PR提交结果"""
        result_window = tk.Toplevel(self.root)
        result_window.title("PR提交结果")
        result_window.geometry("700x500")
        
        # 标题
        if pr_url:
            title_text = "✅ PR提交成功"
            pr_text = f"PR链接: {pr_url}"
        else:
            title_text = "📤 代码已推送，需要创建PR"
            pr_text = "请按照指引手动创建Pull Request"
        
        title_label = ttk.Label(
            result_window,
            text=title_text,
            font=("Arial", 14, "bold")
        )
        title_label.pack(pady=(20, 10))
        
        # PR链接
        pr_label = ttk.Label(
            result_window,
            text=pr_text,
            wraplength=600,
            justify=tk.LEFT
        )
        pr_label.pack(pady=(0, 20))


        # 如果有PR链接，显示已切回原分支的说明
        if pr_url:
            note_label = ttk.Label(
                result_window,
                text="已切回您先前所在的分支（若创建了临时分支）",
                wraplength=600,
                justify=tk.LEFT,
                foreground='gray'
            )
            note_label.pack(pady=(0, 10))
        
        if pr_url:
            # 添加复制链接按钮
            def copy_url():
                self.root.clipboard_clear()
                self.root.clipboard_append(pr_url)
                self.update_status("PR链接已复制到剪贴板")
            
            copy_button = ttk.Button(
                result_window,
                text="📋 复制PR链接",
                command=copy_url
            )
            copy_button.pack(pady=(0, 10))
        
        # 提交的论文列表
        list_frame = ttk.LabelFrame(result_window, text=f"已提交的论文 ({len(self.papers)}篇)", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # 创建滚动文本框显示论文列表
        text_widget = scrolledtext.ScrolledText(list_frame, height=10)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        for i, paper in enumerate(self.papers, 1):
            text_widget.insert(tk.END, f"{i}. {paper.title}\n")
            text_widget.insert(tk.END, f"   作者: {paper.authors[:50]}...\n")
            text_widget.insert(tk.END, f"   分类: {paper.category}\n")
            if i < len(self.papers):
                text_widget.insert(tk.END, "-" * 60 + "\n")
        
        text_widget.config(state=tk.DISABLED)
        
        # 按钮
        button_frame = ttk.Frame(result_window)
        button_frame.pack(pady=(0, 20))
        
        close_button = ttk.Button(
            button_frame,
            text="关闭",
            command=result_window.destroy,
            width=15
        )
        close_button.pack()
        
        self.update_status("PR提交完成" if pr_url else "代码已推送，等待PR创建")
    

    
    def load_template(self):
        """加载模板文件"""
        filepath = filedialog.askopenfilename(
            title="选择模板文件",
            filetypes=[("Excel文件", "*.xlsx"), ("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not filepath:
            return
        if self.papers:
            if messagebox.askyesno("确认", "有未保存的论文，是否保存？如果取消当前表单内容会丢失"):
                if self.save_all_papers()==False:
                    return
        try:
            if filepath.endswith('.json'):
                data = self.update_utils.read_json_file(filepath)
            elif filepath.endswith('.xlsx'):
                try:
                    import pandas as pd

                except Exception as e:
                    messagebox.showerror("错误", f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
                    return
                df = pd.read_excel(filepath, engine='openpyxl')
                # 转换为Paper对象列表
                papers_data = []
                for _, row in df.iterrows():
                    paper_data = {}
                    for tag in self.config.get_active_tags():
                        column_name = tag['table_name']
                        if column_name in row:
                            value = row[column_name]
                            if pd.isna(value):
                                value = ""
                            paper_data[tag['variable']] = str(value).strip()
                    
                    papers_data.append(paper_data)
                
                data = {'papers': papers_data}
            else:
                messagebox.showerror("错误", "不支持的文件格式，如果想要处理excel文件，你需要安装pandas依赖包")
                return
            
            if data and 'papers' in data:
                # 清空现有论文
                self.papers = []
                
                # 添加新论文
                for paper_data in data['papers']:
                    paper = Paper.from_dict(paper_data)
                    self.papers.append(paper)
                
                self.update_paper_list()
                self.clear_form()
                
                messagebox.showinfo("成功", f"已加载 {len(self.papers)} 篇论文")
                self.update_status(f"已从模板加载 {len(self.papers)} 篇论文")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载模板失败: {e}")
    
    def on_closing(self):
        """关闭窗口时的处理"""
        if self.papers:
            if messagebox.askyesno("确认", "有未保存的论文，是否保存？如果取消当前表单内容会丢失"):
                if self.save_all_papers()==False:
                    return
                    
        
        self.root.destroy()


def main():
    """主函数"""
    root = tk.Tk()
    app = PaperSubmissionGUI(root)
    
    # 绑定关闭事件
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # 运行主循环
    root.mainloop()


if __name__ == "__main__":
    main()