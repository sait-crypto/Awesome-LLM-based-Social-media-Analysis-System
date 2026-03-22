"""
图形化界面提交系统
它由submit.py调用
业务逻辑在submit_logic.py中实现，这里主要负责UI交互
"""
import os
import sys
import re
import copy
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
from typing import Dict, List, Any, Optional, Tuple
import threading 
import subprocess
import time

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
        self.root.title("Awesome 论文规范化处理提交程序")
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
        self.style.configure('NeedsConfirm.TButton', foreground="#0D9ABA")
        self.style.configure('SearchHit.TLabel', foreground="#B54708")

        self._default_status_values = ['unread', 'reading', 'done', 'skimmed', 'other person','adopted', 'rejected']
        self._search_hit_fields_by_real_idx: Dict[int, set] = {}

        try:
            pipeline_cfg_max = int(self.settings['database'].get('max_pipeline_images_per_paper', 4))
        except Exception:
            pipeline_cfg_max = 4
        self._gui_pipeline_max = max(1, min(pipeline_cfg_max, 6)) # 硬限制最大不超过6，避免界面过于复杂

        self._suppress_select_event = False
        self._handling_paper_selection = False
        self._skip_next_selection_confirm = False
        self.drag_item = None
        self.drag_ghost = None
        self._drag_press_item = None
        self._drag_press_xy = None
        self._drag_min_distance = 6
        
        # 跟踪已导入的临时文件，避免重复复制
        self._imported_files: Dict[str, Optional[Tuple[str, str]]] = {
            'pipeline_image': None,
            'paper_file': None
        }

        # file 字段确认(✓)状态
        self._file_field_states: Dict[str, Dict[str, Any]] = {
            'pipeline_image': {},
            'paper_file': {}
        }

        self._field_vars: Dict[str, Any] = {}
        self.field_labels: Dict[str, ttk.Label] = {}
        self._search_fields_popup: Optional[tk.Toplevel] = None
        self._search_field_vars: Dict[str, tk.BooleanVar] = {}
        self._selected_category_filter = ""
        self._category_sidebar_visible = False
        self._updating_category_filter_tree = False
        self._init_keyword_field_filter_config()
        self._init_list_column_config()
        self._list_columns_popup: Optional[tk.Toplevel] = None
        self._list_sort_column: Optional[str] = None
        self._list_sort_desc: bool = False

        self.setup_ui()
        
        # 检查管理员状态并更新UI
        self._update_admin_ui_state()
        
        self.load_initial_data()
        
        messagebox.showinfo("须知",f"该界面用于:\n    1.规范化生成的处理json/csv更新文件\n    2.自动分支并提交PR（完整版功能）\n如果根目录中的submit_template.xlsx或submit_template.json已按规范填写内容，你可以手动提交PR或使用该界面自动分支并提交PR，您提交的内容会自动更新到仓库论文列表")
        
        self.tooltip = None
        self.show_placeholder()

    def _init_keyword_field_filter_config(self):
        self._keyword_field_options = [
            'title',
            'title_translation',
            'abstract',
            'doi',
            'authors',
            'date',
            'summary_motivation',
            'summary_innovation',
            'summary_method',
            'summary_conclusion',
            'summary_limitation',
            'conference',
            'analogy_summary',
            'contributor',
            'notes',
        ]
        self._keyword_field_name_map = {}
        for variable in self._keyword_field_options:
            tag = self.config.get_tag_by_variable(variable) or {}
            self._keyword_field_name_map[variable] = tag.get('display_name', variable)
        self._keyword_default_fields = {'title', 'title_translation', 'abstract'}

    def _get_status_values(self) -> List[str]:
        status_tag = self.config.get_tag_by_variable('status') or {}
        values = status_tag.get('options') or []
        if isinstance(values, list) and values:
            return [str(v).strip() for v in values if str(v).strip()]
        return list(self._default_status_values)

    def _get_selected_keyword_fields(self) -> List[str]:
        return [k for k, v in self._search_field_vars.items() if v.get()]

    def _get_status_filter_value(self) -> str:
        combo = getattr(self, 'status_filter_combo', None)
        if combo is None:
            return 'All Status'
        return combo.get() or 'All Status'

    def _get_category_filter_value(self) -> str:
        return (getattr(self, '_selected_category_filter', '') or '').strip()

    def _is_any_filter_active(self) -> bool:
        return bool(
            self._get_search_keyword()
            or self._get_category_filter_value()
            or self._get_status_filter_value() != 'All Status'
        )

    def _update_keyword_field_button_text(self):
        if not hasattr(self, 'keyword_fields_btn'):
            return
        selected_names = [
            self._keyword_field_name_map.get(v, v)
            for v in self._get_selected_keyword_fields()
        ]
        if len(selected_names) <= 2:
            text = '筛选字段: ' + '/'.join(selected_names)
        else:
            text = f'筛选字段({len(selected_names)})'
        self.keyword_fields_btn.config(text=text)

    def _toggle_keyword_fields_popup(self):
        if self._search_fields_popup and self._search_fields_popup.winfo_exists():
            self._search_fields_popup.destroy()
            self._search_fields_popup = None
            return

        popup = tk.Toplevel(self.root)
        popup.title('关键词筛选字段')
        popup.transient(self.root)
        popup.resizable(False, False)
        self._search_fields_popup = popup

        btn = self.keyword_fields_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height() + 2
        popup.geometry(f'+{x}+{y}')

        frame = ttk.Frame(popup, padding=8)
        frame.grid(row=0, column=0, sticky='nsew')
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text='勾选参与关键词匹配的字段:').grid(row=0, column=0, sticky='w', pady=(0, 6))

        row = 1
        for variable in self._keyword_field_options:
            name = self._keyword_field_name_map.get(variable, variable)
            var_obj = self._search_field_vars.get(variable)
            if var_obj is None:
                continue
            cb = ttk.Checkbutton(
                frame,
                text=name,
                variable=var_obj,
                command=self._on_keyword_field_selection_change,
            )
            cb.grid(row=row, column=0, sticky='w')
            row += 1

        footer = ttk.Frame(frame)
        footer.grid(row=row, column=0, sticky='ew', pady=(8, 0))
        ttk.Button(footer, text='全选', command=self._select_all_keyword_fields).pack(side=tk.LEFT)
        ttk.Button(footer, text='默认', command=self._reset_default_keyword_fields).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text='关闭', command=self._toggle_keyword_fields_popup).pack(side=tk.RIGHT)

        popup.protocol('WM_DELETE_WINDOW', self._toggle_keyword_fields_popup)

    def _select_all_keyword_fields(self):
        all_selected = bool(self._search_field_vars) and all(var.get() for var in self._search_field_vars.values())
        target_state = not all_selected
        for var in self._search_field_vars.values():
            var.set(target_state)
        self._on_keyword_field_selection_change()

    def _reset_default_keyword_fields(self):
        for variable, var in self._search_field_vars.items():
            var.set(variable in self._keyword_default_fields)
        self._on_keyword_field_selection_change()

    def _on_keyword_field_selection_change(self):
        self._update_keyword_field_button_text()
        self._on_search_change()

    def _init_list_column_config(self):
        self._list_column_defs: Dict[str, Dict[str, Any]] = {
            'ID': {'title': '#', 'width': 56, 'anchor': 'center', 'stretch': False, 'required': True},
            'Title': {'title': 'Title', 'width': 240, 'anchor': 'w', 'stretch': True, 'required': True},
            'Status': {'title': 'State', 'width': 90, 'anchor': 'center', 'stretch': False, 'required': True},
            'Authors': {'title': 'Authors', 'width': 180, 'anchor': 'w', 'stretch': False, 'required': False},
            'Date': {'title': 'Publish Date', 'width': 110, 'anchor': 'center', 'stretch': False, 'required': False},
            'Contributor': {'title': 'Contributor', 'width': 120, 'anchor': 'w', 'stretch': False, 'required': False},
            'Conference': {'title': 'Conference', 'width': 130, 'anchor': 'w', 'stretch': False, 'required': False},
            'ReadStatus': {'title': 'Reading Status', 'width': 120, 'anchor': 'center', 'stretch': False, 'required': False},
            'Placeholder': {'title': 'Is Placeholder', 'width': 110, 'anchor': 'center', 'stretch': False, 'required': False},
        }
        self._list_optional_defaults = []
        self._list_column_vars: Dict[str, tk.BooleanVar] = {}
        for key, cfg in self._list_column_defs.items():
            is_required = bool(cfg.get('required', False))
            self._list_column_vars[key] = tk.BooleanVar(value=(is_required or key in self._list_optional_defaults))

    def _get_visible_list_columns(self) -> List[str]:
        visible: List[str] = []
        for key in self._list_column_defs:
            var_obj = self._list_column_vars.get(key)
            if var_obj is not None and bool(var_obj.get()):
                visible.append(key)
        return visible

    def _update_list_columns_button_text(self):
        if not hasattr(self, 'list_columns_btn'):
            return
        visible = self._get_visible_list_columns()
        optional_selected = [k for k in visible if not self._list_column_defs.get(k, {}).get('required')]
        self.list_columns_btn.config(text=f'列({len(optional_selected)})')

    def _toggle_list_columns_popup(self):
        if self._list_columns_popup and self._list_columns_popup.winfo_exists():
            self._list_columns_popup.destroy()
            self._list_columns_popup = None
            return

        popup = tk.Toplevel(self.root)
        popup.title('列表列配置')
        popup.transient(self.root)
        popup.resizable(False, False)
        self._list_columns_popup = popup

        btn = self.list_columns_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height() + 2
        popup.geometry(f'+{x}+{y}')

        frame = ttk.Frame(popup, padding=8)
        frame.grid(row=0, column=0, sticky='nsew')
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text='勾选列表显示字段（#、Title 必选）:').grid(row=0, column=0, sticky='w', pady=(0, 6))

        row = 1
        for key, cfg in self._list_column_defs.items():
            if cfg.get('required'):
                continue
            text = cfg.get('title', key)
            cb = ttk.Checkbutton(
                frame,
                text=text,
                variable=self._list_column_vars[key],
                command=self._on_list_column_selection_change,
            )
            cb.grid(row=row, column=0, sticky='w')
            row += 1

        footer = ttk.Frame(frame)
        footer.grid(row=row, column=0, sticky='ew', pady=(8, 0))
        ttk.Button(footer, text='默认', command=self._reset_default_list_columns).pack(side=tk.LEFT)
        ttk.Button(footer, text='关闭', command=self._toggle_list_columns_popup).pack(side=tk.RIGHT)

        popup.protocol('WM_DELETE_WINDOW', self._toggle_list_columns_popup)

    def _reset_default_list_columns(self):
        for key, cfg in self._list_column_defs.items():
            is_required = bool(cfg.get('required', False))
            self._list_column_vars[key].set(is_required or key in self._list_optional_defaults)
        self._on_list_column_selection_change()

    def _on_list_column_selection_change(self):
        self._update_list_columns_button_text()
        self._apply_paper_tree_columns()
        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())

    def _apply_paper_tree_columns(self):
        if not hasattr(self, 'paper_tree'):
            return

        visible_columns = tuple(self._get_visible_list_columns())
        self.paper_tree.configure(columns=visible_columns)

        sort_col = self._list_sort_column
        if sort_col not in visible_columns:
            self._list_sort_column = None
            self._list_sort_desc = False

        for col in visible_columns:
            cfg = self._list_column_defs.get(col, {})
            title = cfg.get('title', col)
            if col == self._list_sort_column:
                title = f"{title} {'▼' if self._list_sort_desc else '▲'}"
            self.paper_tree.heading(col, text=title, command=lambda c=col: self._on_paper_tree_heading_click(c))
            self.paper_tree.column(
                col,
                width=int(cfg.get('width', 120)),
                minwidth=40,
                anchor=cfg.get('anchor', 'w'),
                stretch=bool(cfg.get('stretch', False)),
            )

    def _on_paper_tree_heading_click(self, column: str):
        if column == self._list_sort_column:
            self._list_sort_desc = not self._list_sort_desc
        else:
            self._list_sort_column = column
            self._list_sort_desc = False

        self._apply_paper_tree_columns()
        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())

    def _get_list_column_display_value(self, paper, real_idx: int, column: str) -> str:
        if column == 'ID':
            return str(real_idx + 1)
        if column == 'Title':
            title = paper.title or ''
            return title[:150] + '...' if len(title) > 150 else title
        if column == 'Authors':
            return str(getattr(paper, 'authors', '') or '')
        if column == 'Date':
            return str(getattr(paper, 'date', '') or '')
        if column == 'Contributor':
            return str(getattr(paper, 'contributor', '') or '')
        if column == 'Conference':
            return str(getattr(paper, 'conference', '') or '')
        if column == 'ReadStatus':
            return str(getattr(paper, 'status', '') or '')
        if column == 'Placeholder':
            return 'Yes' if bool(getattr(paper, 'is_placeholder', False)) else 'No'
        return ''

    def _get_list_sort_key(self, paper, real_idx: int, column: str):
        if column == 'ID':
            return real_idx
        if column == 'Date':
            date_text = str(getattr(paper, 'date', '') or '').strip()
            parts = date_text.split('-')
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                try:
                    return int(parts[0]), int(parts[1]), int(parts[2])
                except Exception:
                    pass
            return (9999, 99, 99)
        if column == 'Placeholder':
            return int(bool(getattr(paper, 'is_placeholder', False)))
        text = self._get_list_column_display_value(paper, real_idx, column)
        return str(text or '').lower()

    def _sort_filtered_indices_for_display(self, indices: List[int]) -> List[int]:
        sort_col = self._list_sort_column
        if not sort_col:
            return list(indices)
        if sort_col not in self._get_visible_list_columns():
            return list(indices)

        sorted_indices = list(indices)
        sorted_indices.sort(
            key=lambda ridx: self._get_list_sort_key(self.logic.papers[ridx], ridx, sort_col),
            reverse=self._list_sort_desc,
        )
        return sorted_indices

    def _is_drag_reorder_allowed(self) -> bool:
        sort_col = self._list_sort_column
        # 仅在无排序或按 # 排序时允许拖拽改序
        return (not sort_col) or (sort_col == 'ID')
    
    def load_initial_data(self):
        try:
            count = self.logic.load_existing_updates()
            self._set_current_loaded_file(self.logic.current_file_path or self.logic.primary_update_file)
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

        title_label = ttk.Label(header_frame, text="🎓 Awesome 论文规范化处理提交程序", font=("Arial", 14, "bold"))
        title_label.pack(side=tk.LEFT)

        # 显示当前活跃的更新文件提示
        active_files = []
        paths = self.logic.config.settings['paths']
        for k in ['update_json', 'update_csv', 'my_update_json', 'my_update_csv']:
            p = paths.get(k)
            if p:
                active_files.append(os.path.basename(p))

        # 额外更新文件
        extra = paths.get('extra_update_files_list', [])
        active_files.extend([os.path.basename(f) for f in extra])

        files_str = ", ".join(active_files[:6])
        if len(active_files) > 6:
            files_str += "..."

        info_label = ttk.Label(header_frame, text=f"  [Active: {files_str}]", foreground="gray")
        info_label.pack(side=tk.LEFT, padx=10)

        # 管理员切换按钮
        self.admin_btn = ttk.Button(header_frame, text="🔒 管理员模式", command=self._toggle_admin_mode, width=15)
        self.admin_btn.pack(side=tk.RIGHT)

        # === 主分割窗口 ===
        self.paned_window = self._create_standard_horizontal_paned(main_frame)
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

    def _create_standard_horizontal_paned(self, parent):
        return tk.PanedWindow(
            parent,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            sashrelief=tk.RAISED,
            showhandle=False,
            opaqueresize=True,
            bd=0,
        )
    
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
        
        # 1. 阅读状态筛选
        self.status_filter_combo = ttk.Combobox(header_frame, state="readonly", width=12)
        self.status_filter_combo['values'] = ['All Status'] + self._get_status_values()
        self.status_filter_combo.set('All Status')
        self.status_filter_combo.bind("<<ComboboxSelected>>", self._on_search_change)
        self.status_filter_combo.pack(side=tk.RIGHT)

        # 2. 搜索框 (Middle Fill) - 带占位符逻辑
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(header_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

        # 3. 关键词字段筛选下拉（放在关键词搜索框左边）
        self.keyword_fields_btn = ttk.Button(
            header_frame,
            text='字段',
            width=9,
            command=self._toggle_keyword_fields_popup,
        )
        self.keyword_fields_btn.pack(side=tk.RIGHT, padx=(0, 5))

        self.list_columns_btn = ttk.Button(
            header_frame,
            text='列(0)',
            width=7,
            command=self._toggle_list_columns_popup,
        )
        self.list_columns_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # 4. 分类层级侧栏开关（位于筛选字段按钮左侧）
        self.category_sidebar_toggle_btn = ttk.Button(
            header_frame,
            text='>>',
            width=3,
            command=self._toggle_category_filter_sidebar,
        )
        self.category_sidebar_toggle_btn.pack(side=tk.RIGHT, padx=(0, 5))
        self.create_tooltip(self.category_sidebar_toggle_btn, "显示/隐藏分类层级筛选栏")

        for variable in self._keyword_field_options:
            self._search_field_vars[variable] = tk.BooleanVar(value=(variable in self._keyword_default_fields))
        self._update_keyword_field_button_text()
        self._update_list_columns_button_text()
        
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


        # --- Row 1: 列表区域（左侧可展开分类层级栏，支持拖动分隔） ---
        self.list_content_paned = self._create_standard_horizontal_paned(parent)
        self.list_content_paned.grid(row=1, column=0, sticky="nsew")

        self.category_filter_panel = ttk.Frame(self.list_content_paned)

        category_tree_frame = ttk.Frame(self.category_filter_panel)
        category_tree_frame.pack(fill=tk.BOTH, expand=True)
        category_tree_frame.columnconfigure(0, weight=1)
        category_tree_frame.rowconfigure(0, weight=1)

        self.category_filter_tree = ttk.Treeview(
            category_tree_frame,
            columns=('Count',),
            show='tree headings',
            selectmode='browse',
            height=15,
        )
        self.category_filter_tree.heading('#0', text='Category')
        self.category_filter_tree.heading('Count', text='Count')
        self.category_filter_tree.column('#0', width=220, stretch=False)
        self.category_filter_tree.column('Count', width=35, anchor='e', stretch=False)

        category_scrollbar = ttk.Scrollbar(category_tree_frame, orient=tk.VERTICAL, command=self.category_filter_tree.yview)
        self.category_filter_tree.configure(yscrollcommand=category_scrollbar.set)
        self.category_filter_tree.grid(row=0, column=0, sticky='nsew')
        category_scrollbar.grid(row=0, column=1, sticky='ns')
        self.category_filter_tree.bind('<<TreeviewSelect>>', self._on_category_filter_tree_select)
        self.category_filter_tree.bind('<Enter>', lambda e: self._bind_global_scroll(self.category_filter_tree.yview_scroll))
        self.category_filter_tree.bind('<Configure>', lambda e: self._fit_category_tree_columns())

        ttk.Button(
            self.category_filter_panel,
            text='📋 复制结构到剪贴板',
            command=self._copy_category_tree_structure_to_clipboard,
        ).pack(fill=tk.X, pady=(4, 0))

        list_frame = ttk.Frame(self.list_content_paned)
        self.paper_list_panel = list_frame
        
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.paper_tree = ttk.Treeview(list_frame, columns=(), show="headings", height=15)
        self._apply_paper_tree_columns()
        
        self.paper_tree.tag_configure('conflict', background=self.color_conflict)
        self.paper_tree.tag_configure('invalid', background=self.color_invalid)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.paper_tree.yview)
        self.paper_tree.configure(yscrollcommand=scrollbar.set)
        
        self.paper_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
    
        self.paper_tree.bind('<<TreeviewSelect>>', self.on_paper_selected)
        self.paper_tree.bind('<Enter>', lambda e: self._bind_global_scroll(self.paper_tree.yview_scroll))
        
        self.paper_tree.bind("<Button-3>", self._show_context_menu)
        self.paper_tree.bind("<Button-1>", self._on_tree_left_button)
        self.paper_tree.bind("<B1-Motion>", self._on_drag_motion)
        self.paper_tree.bind("<ButtonRelease-1>", self._on_drag_release)

        self.list_content_paned.add(self.category_filter_panel, minsize=160, stretch="never")
        self.list_content_paned.add(list_frame, minsize=220, stretch="always")
        self.list_content_paned.forget(self.category_filter_panel)

        def _set_initial_list_sash_position():
            if not self._category_sidebar_visible:
                return
            total_width = self.list_content_paned.winfo_width()
            if total_width > 1:
                self.list_content_paned.sash_place(0, int(total_width * 0.40), 0)
        self.root.after_idle(_set_initial_list_sash_position)

        self._rebuild_category_filter_tree(select_current=True)
        
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
        fill_zotero_btn.grid(row=0, column=1, sticky="ew", padx=(63, 0)) 

        self.search_hit_preview = tk.Text(
            self.form_container,
            height=3,
            wrap=tk.WORD,
            relief=tk.GROOVE,
            borderwidth=1,
            background="#FFFBE6",
        )
        self.search_hit_preview.tag_configure('SearchHitPreviewKeyword', background="#FFE58F")
        self.search_hit_preview.config(state='disabled')
        self.search_hit_preview.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.search_hit_preview.grid_remove()
        
        # --- 可滚动区域 ---
        self.form_canvas = tk.Canvas(self.form_container)
        scrollbar = ttk.Scrollbar(self.form_container, orient=tk.VERTICAL, command=self.form_canvas.yview)
        
        self.form_frame = ttk.Frame(self.form_canvas)
        self.form_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.form_canvas_window = self.form_canvas.create_window((0, 0), window=self.form_frame, anchor=tk.NW, width=800)

        self.form_canvas.bind('<Enter>', lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
        self.form_frame.bind('<Enter>', lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))

        self.form_canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        
        self.form_container.columnconfigure(0, weight=1)
        self.form_container.rowconfigure(2, weight=1)
        
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
        self.field_labels = {}
        self._field_vars = {}
        
        for tag in active_tags:
            # 逻辑：如果是系统字段且不是管理员模式，隐藏
            # 管理员模式下，显示所有字段（包括 id, conflict_marker 等）
            is_system = tag.get('system', False)
            if is_system and not self.logic.is_admin:
                continue

            variable = tag.get('variable')
            display_name = tag.get('display_name', variable)
            description = tag.get('description', '')
            if not variable:
                continue

            required = tag.get('required', False)
            field_type = tag.get('type', 'string')
            
            label_text = f"{display_name}* :" if required else f"{display_name} :"
            
            # 特殊标注系统字段
            if is_system:
                label_text = f"[SYS] {label_text}"
            
            label = ttk.Label(self.form_frame, text=label_text)
            label_sticky = tk.NW if field_type == 'text' else tk.W
            
            label.grid(row=row, column=0, sticky=label_sticky, pady=(2, 2))
            self.field_labels[variable] = label
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
                self._gui_category_max = min(cfg_max, 10) # 硬限制最大不超过10，避免界面过于复杂

                self._gui_add_category_row('')
                self.form_fields[variable] = container
                self.field_widgets[variable] = container

            # === 2. File Fields (Asset Import) ===
            elif variable == 'pipeline_image':
                self._create_pipeline_file_array_ui(row, variable)

            elif variable == 'paper_file':
                self._create_file_field_ui(row, variable)

            # === 3. Standard Enum ===
            elif field_type == 'enum':
                values = tag.get('options', [])
                # Hardcoded fallback for status if not in config
                if variable == 'status' and not values: 
                    values = self._get_status_values()
                
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
                if variable == 'conflict_marker':
                    checkbox.bind("<Button-1>", lambda e, val=var: self._on_conflict_marker_click(e, val))
                    checkbox.bind("<Key-space>", lambda e, val=var: self._on_conflict_marker_click(e, val))
                self.form_fields[variable] = var
                self.field_widgets[variable] = checkbox 
                
            # === 5. Text (Multiline) ===
            elif field_type == 'text':
                text_frame = ttk.Frame(self.form_frame)
                text_frame.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))
                
                height = 7 if variable in ['abstract', 'notes'] else 5
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
                self._field_vars[variable] = sv
                entry.bind("<KeyRelease>", lambda e, v=variable, w=entry: self._on_field_change(v, w))
                entry.bind("<FocusOut>", lambda e, v=variable, w=entry: self._on_field_change(v, w))
                
                entry.bind("<Enter>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))
                self.form_fields[variable] = entry
                self.field_widgets[variable] = entry
            
            row += 1
        
        self.form_frame.columnconfigure(1, weight=1)

    def _get_current_real_index(self) -> int:
        if self.current_paper_index < 0:
            return -1
        if self.current_paper_index >= len(self.filtered_indices):
            return -1
        return self.filtered_indices[self.current_paper_index]

    def _get_current_paper(self):
        ridx = self._get_current_real_index()
        if ridx < 0:
            return None
        if ridx >= len(self.logic.papers):
            return None
        return self.logic.papers[ridx]

    def _reset_list_after_data_change(self, keyword: Optional[str] = None, category: Optional[str] = None):
        """数据变化后统一重置选择并刷新列表/占位视图。"""
        self.current_paper_index = -1
        if keyword is None and category is None:
            self.refresh_list_view()
        else:
            self.refresh_list_view(keyword or "", category or "")
        self.show_placeholder()

    def _is_dnd_available(self) -> bool:
        if not hasattr(self.root, '_dnd_available'):
            try:
                self.root.tk.call('package', 'require', 'tkdnd')
                self.root._dnd_available = True
            except Exception:
                self.root._dnd_available = False
        return bool(getattr(self.root, '_dnd_available', False))

    def _setup_file_drop_target(
        self,
        widget,
        on_file_path,
        tooltip_ready: str,
        tooltip_fallback: str,
    ) -> bool:
        if not self._is_dnd_available():
            self.create_tooltip(widget, tooltip_fallback)
            return False

        try:
            from tkinterdnd2 import DND_FILES
        except Exception as ex:
            self.update_status(f"拖放初始化失败: {ex}")
            self.create_tooltip(widget, tooltip_fallback)
            return False

        def on_drop(event):
            files = self.root.tk.splitlist(event.data)
            if not files:
                return
            file_path = files[0].strip('{}').strip('"')
            try:
                on_file_path(file_path)
            except Exception as ex:
                messagebox.showerror("资源处理失败", str(ex))

        widget.drop_target_register(DND_FILES)
        widget.dnd_bind('<<Drop>>', on_drop)
        self.create_tooltip(widget, tooltip_ready)
        return True

    def _import_file_asset_once(self, src_path: str, asset_type: str, field_name: str) -> str:
        """导入到 assets/temp/{uid}/{asset_type} 并返回临时相对路径"""
        if not src_path:
            return ""

        # 手动输入的相对路径（项目内存在）不复制
        if not os.path.isabs(src_path):
            rel_check = os.path.join(BASE_DIR, src_path)
            if os.path.exists(rel_check):
                self._imported_files[field_name] = (src_path, src_path)
                return src_path.replace('\\', '/')

        # 绝对路径但位于项目内：改为相对路径，不复制
        if os.path.isabs(src_path):
            try:
                rel_path = os.path.relpath(src_path, BASE_DIR).replace('\\', '/')
                if not rel_path.startswith('..') and os.path.exists(src_path):
                    self._imported_files[field_name] = (src_path, rel_path)
                    return rel_path
            except ValueError:
                pass

        # 缓存命中
        cached_pair = self._imported_files.get(field_name)
        if cached_pair:
            cached_src, cached_dest = cached_pair
            if cached_src == src_path:
                return cached_dest

        paper = self._get_current_paper()
        if not paper:
            raise RuntimeError("请先选择论文")
        uid = self.logic.ensure_paper_uid(paper)

        ok, rel_path, err = self.logic.import_file_asset(src_path, asset_type, uid)
        if not ok:
            raise RuntimeError(err or "导入失败")
        self._imported_files[field_name] = (src_path, rel_path)
        return rel_path

    def _update_file_confirm_button_state(self, variable: str):
        state = self._file_field_states.get(variable, {})
        btn = state.get('confirm_btn')
        sv = state.get('var')
        if not btn or sv is None:
            return
        cur = (sv.get() or '').strip()
        last = (state.get('last_confirmed') or '').strip()
        needs_confirm = self._needs_file_confirmation(variable, cur, last)
        btn.config(state=('normal' if needs_confirm else 'disabled'))
        btn.config(style=('NeedsConfirm.TButton' if needs_confirm else 'TButton'))

    def _needs_file_confirmation(self, variable: str, cur: str, last: str) -> bool:
        if cur != last:
            return True
        if not cur:
            return False
        paper = self._get_current_paper()
        if not paper:
            return False
        try:
            paper_shadow = copy.deepcopy(paper)
            ok, normalized, _ = self.logic.confirm_file_field_for_paper(paper_shadow, variable, raw_value=cur)
            if not ok:
                return True
            return (normalized or '').strip() != cur
        except Exception:
            return True

    def _confirm_single_file_field(self, variable: str, show_popup: bool = True) -> bool:
        paper = self._get_current_paper()
        if not paper:
            return True
        state = self._file_field_states.get(variable, {})
        sv = state.get('var')
        if sv is None:
            return True

        raw_val = (sv.get() or '').strip()

        try:
            ok, normalized, err = self.logic.confirm_file_field_for_paper(paper, variable, raw_value=raw_val)
            if not ok:
                if show_popup:
                    messagebox.showerror("资源处理失败", err or "规范化失败")
                self._update_file_confirm_button_state(variable)
                return False

            normalized = normalized or ''
            sv.set(normalized)
            if variable == 'pipeline_image':
                self._pipeline_set_rows_from_value(variable, normalized)
            state['last_confirmed'] = normalized
            self._update_file_confirm_button_state(variable)
            self.logic.clear_temp_assets_for_paper(getattr(paper, 'uid', ''), variable)
            self._validate_single_field_visuals(variable, self._get_current_real_index())
            return True
        except Exception as ex:
            if show_popup:
                messagebox.showerror("资源处理失败", str(ex))
            self._update_file_confirm_button_state(variable)
            return False

    def _confirm_all_pending_file_fields_for_current_paper(self, show_popup: bool = True, block_on_error: bool = True) -> bool:
        had_error = False
        for variable in ('pipeline_image', 'paper_file'):
            state = self._file_field_states.get(variable, {})
            sv = state.get('var')
            if sv is None:
                continue
            cur = (sv.get() or '').strip()
            last = (state.get('last_confirmed') or '').strip()
            if self._needs_file_confirmation(variable, cur, last):
                if not self._confirm_single_file_field(variable, show_popup=show_popup):
                    had_error = True
                    if block_on_error:
                        return False
        return not had_error if block_on_error else True

    def _create_file_field_ui(self, row, variable):
        """Helper to create file fields with correct layout, scoping, and Drag-and-Drop"""
        frame = ttk.Frame(self.form_frame)
        frame.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))

        # 0. Confirm Button (Left)
        btn_confirm = ttk.Button(frame, text="✓", width=3, command=lambda v=variable: self._confirm_single_file_field(v, show_popup=True))
        btn_confirm.pack(side=tk.LEFT, padx=(0, 4))
        self.create_tooltip(btn_confirm, "确认该字段：校验并规范化到 assets/{uid}/；失败会中断且不修改")
        
        # 1. Entry (Left side, fill)
        entry = tk.Entry(frame)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 2. Buttons container (Right side)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.RIGHT, padx=(5, 0))
        
        sv = tk.StringVar()
        def on_file_value_change(*args):
            self._on_field_change(variable, entry)
            self._update_file_confirm_button_state(variable)
        sv.trace_add("write", on_file_value_change)
        entry.config(textvariable=sv)
        
        # 拖放功能支持 (tkinterdnd2)
        def on_drop_pdf_file(file_path: str):
            ok, err = self.logic.validate_single_asset_reference('paper_file', file_path)
            if not ok:
                messagebox.showerror("错误", err or "PDF 文件校验失败")
                return
            rel_path = self._import_file_asset_once(file_path, 'paper', variable)
            if rel_path:
                sv.set(rel_path)

        self._setup_file_drop_target(
            entry,
            on_drop_pdf_file,
            tooltip_ready="可拖放文件到此，或使用「📂」导入",
            tooltip_fallback="使用「📂 浏览」按钮选择文件",
        )

        def _import_pdf_from_text_path(path_text: str) -> bool:
            candidate = str(path_text or '').strip()
            if not candidate:
                return False
            candidate = candidate.splitlines()[0].strip() if candidate else ''
            candidate = candidate.strip('{}').strip('"').strip("'")
            if not candidate:
                return False
            ok, _ = self.logic.validate_single_asset_reference('paper_file', candidate)
            if not ok:
                return False
            try:
                rel_path = self._import_file_asset_once(candidate, 'paper', variable)
                if rel_path:
                    sv.set(rel_path)
                    return True
            except Exception as ex:
                messagebox.showerror("资源处理失败", str(ex))
            return False

        def import_clipboard_pdf(show_empty_info: bool = False) -> bool:
            try:
                from PIL import ImageGrab
                clip_obj: Any = ImageGrab.grabclipboard()
                if isinstance(clip_obj, list):
                    for item in clip_obj:
                        if _import_pdf_from_text_path(str(item)):
                            return True
                elif isinstance(clip_obj, str):
                    if _import_pdf_from_text_path(clip_obj):
                        return True
            except ImportError:
                pass
            except Exception:
                pass

            try:
                clip_text = self.root.clipboard_get()
            except Exception:
                clip_text = ''

            ok = _import_pdf_from_text_path(clip_text)
            if (not ok) and show_empty_info:
                messagebox.showinfo("Info", "剪贴板中没有可用的 PDF 文件路径")
            return ok

        def on_ctrl_v(event):
            if import_clipboard_pdf(show_empty_info=False):
                return "break"
            return None

        entry.bind("<Control-v>", on_ctrl_v)
        entry.bind("<Control-V>", on_ctrl_v)
        
        # Browse Button
        def browse_file():
            ft = [("PDF", "*.pdf")]
            path = filedialog.askopenfilename(filetypes=ft)
            if path:
                try:
                    asset_type = 'paper'
                    rel_path = self._import_file_asset_once(path, asset_type, variable)
                    if rel_path:
                        sv.set(rel_path)
                except Exception as ex:
                    messagebox.showerror("资源处理失败", str(ex))
        
        btn_browse = ttk.Button(btn_frame, text="📂", width=3, command=browse_file)
        btn_browse.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_browse, "导入文件到临时目录（覆盖当前值）")

        def paste_file():
            import_clipboard_pdf(show_empty_info=True)

        btn_paste = ttk.Button(btn_frame, text="📋", width=3, command=paste_file)
        btn_paste.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_paste, "从剪贴板导入文件（与 Ctrl+V 相同）")

        def open_file():
            path = sv.get().strip()
            if not path:
                return
            refs = [x.strip() for x in str(path).split('|') if x.strip()]
            if not refs:
                return
            self._open_file_direct(refs[0], choose_app=True)

        btn_open = ttk.Button(btn_frame, text="👁️", width=3, command=open_file)
        btn_open.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_open, "打开当前引用文件")
        
        # Reveal/Open Location (📍)
        def reveal_file():
            path = sv.get().strip()
            if not path:
                return
            refs = [x.strip() for x in str(path).split('|') if x.strip()]
            if not refs:
                return
            self._reveal_in_file_manager(refs[0], select_file=True)

        btn_reveal = ttk.Button(btn_frame, text="📍", width=3, command=reveal_file)
        btn_reveal.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_reveal, "在资源管理器中打开当前引用文件位置")

        self._file_field_states[variable] = {
            'var': sv,
            'confirm_btn': btn_confirm,
            'last_confirmed': '',
        }
        self._update_file_confirm_button_state(variable)

        self.form_fields[variable] = entry
        self.field_widgets[variable] = entry

    def _pipeline_refresh_row_buttons(self, variable: str):
        state = self._file_field_states.get(variable, {})
        rows = state.get('rows', [])
        for idx, row_data in enumerate(rows):
            btn = row_data.get('btn')
            if not btn:
                continue
            if idx == 0:
                can_add = len(rows) < self._gui_pipeline_max
                btn.config(text='+', state=('normal' if can_add else 'disabled'))
            else:
                btn.config(text='-', state='normal')

        if rows:
            first_entry = rows[0].get('entry')
            if first_entry:
                self.field_widgets[variable] = first_entry

    def _pipeline_sync_var_from_rows(self, variable: str):
        state = self._file_field_states.get(variable, {})
        sv = state.get('var')
        rows = state.get('rows', [])
        if sv is None:
            return
        values = []
        for row_data in rows:
            row_var = row_data.get('sv')
            if row_var is None:
                continue
            val = (row_var.get() or '').strip()
            if val:
                values.append(val)
        joined = '|'.join(values)
        sv.set(joined)

    def _pipeline_add_row(self, variable: str, initial_value: str = ''):
        state = self._file_field_states.get(variable, {})
        container = state.get('rows_container')
        if container is None:
            return

        row_frame = ttk.Frame(container)
        row_frame.pack(fill=tk.X, pady=1)

        btn_add_remove = ttk.Button(row_frame, text='-', width=2)
        btn_add_remove.pack(side=tk.LEFT, padx=(0, 4))

        entry = tk.Entry(row_frame)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_frame = ttk.Frame(row_frame)
        btn_frame.pack(side=tk.RIGHT, padx=(5, 0))

        row_sv = tk.StringVar(value=initial_value)
        row_data: Dict[str, Any] = {}

        def hide_preview():
            preview_frame = row_data.get('preview_frame')
            if preview_frame is not None:
                try:
                    preview_frame.destroy()
                except Exception:
                    pass
            row_data['preview_frame'] = None
            row_data['preview_visible'] = False
            btn = row_data.get('preview_btn')
            if btn is not None:
                btn.config(text='▼')

        def resolve_preview_path(raw_path: str) -> str:
            clean = (raw_path or '').strip()
            if not clean:
                return ''
            try:
                from src.core.update_file_utils import get_update_file_utils
                ufu = get_update_file_utils()
                resolved = ufu.resolve_asset_path(clean, 'pipeline_image')
                if resolved:
                    return resolved
            except Exception:
                pass
            if os.path.isabs(clean):
                return clean
            return os.path.abspath(os.path.join(BASE_DIR, clean))

        def on_row_change(*args):
            self._pipeline_sync_var_from_rows(variable)
            self._update_file_confirm_button_state(variable)
            if row_data.get('preview_visible'):
                hide_preview()

        row_sv.trace_add("write", on_row_change)
        entry.config(textvariable=row_sv)

        def on_drop_image_file(file_path: str):
            ok, err = self.logic.validate_single_asset_reference('pipeline_image', file_path)
            if not ok:
                messagebox.showerror("错误", err or "图片文件校验失败")
                return
            rel_path = self._import_file_asset_once(file_path, 'figure', variable)
            if rel_path:
                row_sv.set(rel_path)

        self._setup_file_drop_target(
            entry,
            on_drop_image_file,
            tooltip_ready="可拖放图片到此，或使用「📂」导入",
            tooltip_fallback="使用「📂 浏览」按钮选择文件",
        )

        def browse_file():
            path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp;*.svg")])
            if not path:
                return
            try:
                rel_path = self._import_file_asset_once(path, 'figure', variable)
                if rel_path:
                    row_sv.set(rel_path)
            except Exception as ex:
                messagebox.showerror("资源处理失败", str(ex))

        btn_browse = ttk.Button(btn_frame, text="📂", width=3, command=browse_file)
        btn_browse.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_browse, "导入图片到临时目录（覆盖当前行）")

        def paste_img():
            import_clipboard_image(show_empty_info=True)

        btn_paste = ttk.Button(btn_frame, text="📋", width=3, command=paste_img)
        btn_paste.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_paste, "从剪贴板导入图片（与 Ctrl+V 相同）")

        def open_file():
            path = (row_sv.get() or '').strip()
            if not path:
                return
            self._open_file_direct(path, choose_app=True)

        btn_open = ttk.Button(btn_frame, text="👁️", width=3, command=open_file)
        btn_open.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_open, "打开当前引用文件")

        def reveal_file():
            path = (row_sv.get() or '').strip()
            if not path:
                return
            self._reveal_in_file_manager(path, select_file=True)

        btn_reveal = ttk.Button(btn_frame, text="📍", width=3, command=reveal_file)
        btn_reveal.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_reveal, "在资源管理器中打开当前引用文件位置")

        def toggle_preview():
            if row_data.get('preview_visible'):
                hide_preview()
                return

            path = (row_sv.get() or '').strip()
            if not path:
                return messagebox.showinfo("提示", "当前行没有图片路径")

            abs_path = resolve_preview_path(path)
            if not abs_path or (not os.path.exists(abs_path)):
                return messagebox.showerror("错误", "图片文件不存在")

            try:
                from PIL import Image, ImageTk
            except ImportError:
                return messagebox.showerror("错误", "需要安装 Pillow 库支持图片预览: pip install Pillow")

            try:
                img = Image.open(abs_path)
                img.thumbnail((420, 240), Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
            except Exception as ex:
                return messagebox.showerror("错误", f"无法预览图片: {ex}")

            preview_frame = ttk.Frame(container)
            preview_frame.pack(fill=tk.X, padx=(22, 0), pady=(0, 4), after=row_frame)
            img_label = ttk.Label(preview_frame, image=tk_img)
            img_label.image = tk_img
            img_label.pack(anchor='w')
            img_label.bind('<Button-1>', lambda e: self._open_file_direct(path, choose_app=True))

            row_data['preview_frame'] = preview_frame
            row_data['preview_visible'] = True
            btn_preview.config(text='▲')

        btn_preview = ttk.Button(btn_frame, text="▼", width=3, command=toggle_preview)
        btn_preview.pack(side=tk.LEFT, padx=1)
        self.create_tooltip(btn_preview, "展开/收起当前图片预览")

        def import_clipboard_image(show_empty_info: bool = True) -> bool:
            try:
                from PIL import ImageGrab
                img_obj: Any = ImageGrab.grabclipboard()

                def _import_image_path(path_text: str) -> bool:
                    candidate = str(path_text or '').strip()
                    if not candidate:
                        return False
                    candidate = candidate.splitlines()[0].strip() if candidate else ''
                    candidate = candidate.strip('{}').strip('"').strip("'")
                    ok, _ = self.logic.validate_single_asset_reference('pipeline_image', candidate)
                    if not ok:
                        return False
                    try:
                        rel_path = self._import_file_asset_once(candidate, 'figure', variable)
                        if rel_path:
                            row_sv.set(rel_path)
                            return True
                    except Exception as ex:
                        messagebox.showerror("资源处理失败", str(ex))
                    return False

                if img_obj is not None and hasattr(img_obj, 'save'):
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(prefix='paste_', suffix='.png', delete=False)
                    temp_path = tmp.name
                    tmp.close()
                    try:
                        img_obj.save(temp_path)
                        rel_path = self._import_file_asset_once(temp_path, 'figure', variable)
                        if rel_path:
                            row_sv.set(rel_path)
                            return True
                        return False
                    finally:
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

                if isinstance(img_obj, list):
                    for item in img_obj:
                        if _import_image_path(str(item)):
                            return True

                if isinstance(img_obj, str):
                    if _import_image_path(img_obj):
                        return True

                try:
                    clip_text = self.root.clipboard_get()
                except Exception:
                    clip_text = ''

                if _import_image_path(clip_text):
                    return True

                if show_empty_info:
                    messagebox.showinfo("Info", "剪贴板中没有可用图片")
                return False
            except ImportError:
                messagebox.showerror("Error", "需要安装 Pillow 库支持粘贴: pip install Pillow")
                return False
            except Exception as ex:
                messagebox.showerror("Error", str(ex))
                return False

        def on_ctrl_v(event):
            if import_clipboard_image(show_empty_info=False):
                return "break"
            return None

        entry.bind("<Control-v>", on_ctrl_v)
        entry.bind("<Control-V>", on_ctrl_v)

        row_data = {
            'frame': row_frame,
            'btn': btn_add_remove,
            'entry': entry,
            'sv': row_sv,
            'preview_btn': btn_preview,
            'preview_frame': None,
            'preview_visible': False,
        }
        state.setdefault('rows', []).append(row_data)

        def on_add_or_remove():
            rows = state.get('rows', [])
            try:
                idx = rows.index(row_data)
            except ValueError:
                return
            if idx == 0:
                if len(rows) >= self._gui_pipeline_max:
                    return
                self._pipeline_add_row(variable, '')
                self._pipeline_refresh_row_buttons(variable)
                self._pipeline_sync_var_from_rows(variable)
            else:
                hide_preview()
                row_frame.destroy()
                rows.pop(idx)
                if not rows:
                    self._pipeline_add_row(variable, '')
                self._pipeline_refresh_row_buttons(variable)
                self._pipeline_sync_var_from_rows(variable)

        btn_add_remove.config(command=on_add_or_remove)
        self._pipeline_refresh_row_buttons(variable)

    def _pipeline_set_rows_from_value(self, variable: str, raw_value: str):
        state = self._file_field_states.get(variable, {})
        rows = state.get('rows', [])
        for row_data in rows:
            preview_frame = row_data.get('preview_frame')
            if preview_frame is not None:
                try:
                    preview_frame.destroy()
                except Exception:
                    pass
            frame = row_data.get('frame')
            if frame is not None:
                frame.destroy()
        state['rows'] = []

        items = [x.strip() for x in str(raw_value or '').split('|') if x.strip()]
        if len(items) > self._gui_pipeline_max:
            items = items[:self._gui_pipeline_max]

        if not items:
            self._pipeline_add_row(variable, '')
        else:
            for item in items:
                self._pipeline_add_row(variable, item)
        self._pipeline_refresh_row_buttons(variable)
        self._pipeline_sync_var_from_rows(variable)

    def _create_pipeline_file_array_ui(self, row, variable):
        frame = ttk.Frame(self.form_frame)
        frame.grid(row=row, column=1, sticky="we", pady=(2, 2), padx=(5, 0))

        btn_confirm = ttk.Button(frame, text="✓", width=3, command=lambda v=variable: self._confirm_single_file_field(v, show_popup=True))
        btn_confirm.pack(side=tk.LEFT, padx=(0, 4), anchor='n')
        self.create_tooltip(btn_confirm, "确认该字段：校验并规范化到 assets/{uid}/；失败会中断且不修改")

        rows_container = ttk.Frame(frame)
        rows_container.pack(side=tk.LEFT, fill=tk.X, expand=True)

        sv = tk.StringVar()

        def on_value_change(*args):
            self._on_field_change(variable, sv)
            self._update_file_confirm_button_state(variable)

        sv.trace_add("write", on_value_change)

        self._file_field_states[variable] = {
            'var': sv,
            'confirm_btn': btn_confirm,
            'last_confirmed': '',
            'rows_container': rows_container,
            'rows': []
        }

        self._pipeline_add_row(variable, '')
        self._update_file_confirm_button_state(variable)

        self.form_fields[variable] = frame
        self.field_widgets[variable] = frame

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
        self.create_tooltip(btn_tree, "打开分类树：可查看/复制分类树结构，也可双击分类直接填入当前字段")

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
                    except Exception as ex:
                        self.update_status(f"分类操作失败: {ex}")
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
        ttk.Button(script_frame, text="🧹 清除冗余资源", command=self.cleanup_redundant_assets, width=14).pack(side=tk.LEFT, padx=5, pady=5)

        # Group 2: File Operations (增加加载数据库)
        file_frame = ttk.LabelFrame(buttons_frame, text="File Operations")
        file_frame.grid(row=0, column=1, padx=5, sticky="ns")
        
        ttk.Button(file_frame, text="💾 加载数据库", command=self._open_database_action, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(file_frame, text="📤 保存文件", command=self.save_all_papers, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        self.save_policy_btn = ttk.Button(file_frame, text="", command=self._change_save_validation_strategy, width=18)
        self.save_policy_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self._refresh_save_policy_button_text()
        ttk.Button(file_frame, text="📂 加载文件", command=self.load_template, width=12).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(file_frame, text="📄 打开当前文件", command=self.open_current_file, width=14).pack(side=tk.LEFT, padx=5, pady=5)

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
        self._refresh_save_policy_button_text()

        if self.logic.is_admin:
            self.admin_btn.config(text="🔓 管理员: ON")
            self.root.title("Awesome 论文规范化处理提交程序 [管理员模式]")
            if hasattr(self, 'save_policy_btn') and self.save_policy_btn.winfo_manager() != 'pack':
                self.save_policy_btn.pack(side=tk.LEFT, padx=5, pady=5)
        else:
            self.admin_btn.config(text="🔒 管理员: OFF")
            self.root.title("Awesome 论文规范化处理提交程序")
            if hasattr(self, 'save_policy_btn') and self.save_policy_btn.winfo_manager() == 'pack':
                self.save_policy_btn.pack_forget()

    def _get_save_validation_strategy(self) -> str:
        strategy = str((self.settings.get('ui', {}) or {}).get('save_validation_strategy', 'strict')).strip().lower()
        if strategy not in ('strict', 'lenient'):
            strategy = 'strict'
        return strategy

    def _refresh_save_policy_button_text(self):
        if not hasattr(self, 'save_policy_btn'):
            return
        strategy = self._get_save_validation_strategy()
        self.save_policy_btn.config(text=f"🧭 保存策略: {strategy}")

    def _persist_ui_setting(self, key: str, value: str):
        cfg = configparser.ConfigParser(inline_comment_prefixes=('#', ';', '//'))
        cfg_path = os.path.join(str(self.config.config_path), 'config.ini')
        if os.path.exists(cfg_path):
            cfg.read(cfg_path, encoding='utf-8')
        if 'ui' not in cfg:
            cfg['ui'] = {}
        cfg['ui'][key] = str(value)
        with open(cfg_path, 'w', encoding='utf-8') as f:
            cfg.write(f)

        self.config.settings = self.config._load_settings()
        self.logic.settings = self.config.settings
        self.settings = self.logic.settings

    def _change_save_validation_strategy(self):
        if not self.logic.is_admin:
            messagebox.showwarning("权限", "仅管理员可修改保存策略")
            return

        cur = self._get_save_validation_strategy()
        switch_now = messagebox.askyesno(
            "保存策略",
            f"当前保存策略: {cur}\n\n"
            f"严格 (strict): 保存时任何验证失败都会阻止保存，适合正式使用以保证数据质量。\n"
            f"宽松 (lenient): 保存时验证失败仍可以保存。\n\n"
            f"是否切换到另一种策略？\n\n【是】切换\n【否】不切换"
        )
        if not switch_now:
            self.update_status(f"保存策略保持不变: {cur}")
            return

        new_strategy = 'lenient' if cur == 'strict' else 'strict'
        try:
            self._persist_ui_setting('save_validation_strategy', new_strategy)
            self._refresh_save_policy_button_text()
            self.update_status(f"保存策略已更新为: {new_strategy}")
        except Exception as ex:
            messagebox.showerror("错误", f"保存策略写入失败: {ex}")

    def _refresh_ui_fields(self):
        """完全重建表单字段 (根据管理员模式显示/隐藏字段)"""
        # 清除现有
        for widget in self.form_frame.winfo_children():
            widget.destroy()
        
        # 重建
        self.create_form_fields()
        
        # 重新加载当前论文（如果已选）
        current_paper = self._get_current_paper()
        if current_paper is not None:
            self.load_paper_to_form(current_paper)

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
        cat = self._get_category_filter_value()
        status = self._get_status_filter_value()
        self.refresh_list_view(kw, cat, status)

    def _get_paper_field_text(self, paper, variable: str) -> str:
        value = getattr(paper, variable, "")
        if value is None:
            return ""
        return str(value)

    def _filter_papers_with_match_fields(self, keyword: str = "", category: str = "", status: str = "") -> Tuple[List[int], Dict[int, set]]:
        return self.logic.filter_papers_with_match_fields(
            keyword=keyword,
            selected_category=category,
            status=status,
            search_fields=self._get_selected_keyword_fields(),
        )

    def _toggle_category_filter_sidebar(self):
        if self._category_sidebar_visible:
            try:
                self.list_content_paned.forget(self.category_filter_panel)
            finally:
                self._category_sidebar_visible = False
                self.category_sidebar_toggle_btn.config(text='>>')
            return

        total_width = self.list_content_paned.winfo_width()
        target_width = int(total_width * 0.40) if total_width > 1 else 240
        target_width = max(120, target_width)

        panes = self.list_content_paned.panes()
        if str(self.category_filter_panel) not in panes:
            self.list_content_paned.add(
                self.category_filter_panel,
                before=self.paper_list_panel,
                minsize=120,
                stretch="never",
                width=target_width,
            )
        self._category_sidebar_visible = True
        self.category_sidebar_toggle_btn.config(text='<<')
        self._rebuild_category_filter_tree(select_current=True)
        self.root.after_idle(self._fit_category_tree_columns)

        self.list_content_paned.update_idletasks()
        total_width = self.list_content_paned.winfo_width()
        if total_width > 1:
            self.list_content_paned.sash_place(0, int(total_width * 0.40), 0)

    def _fit_category_tree_columns(self):
        tree = getattr(self, 'category_filter_tree', None)
        if tree is None:
            return
        try:
            total = tree.winfo_width()
        except Exception:
            return
        if total <= 1:
            return

        count_w = 35
        name_w = max(120, total - count_w - 8)
        tree.column('#0', width=name_w, stretch=False)
        tree.column('Count', width=count_w, stretch=False)

    def _clear_category_filter(self):
        if not self._get_category_filter_value():
            return
        self._selected_category_filter = ''
        self._rebuild_category_filter_tree(select_current=True)
        self._on_search_change()

    def _on_category_filter_tree_select(self, event=None):
        if self._updating_category_filter_tree:
            return

        tree = getattr(self, 'category_filter_tree', None)
        if tree is None:
            return

        selection = tree.selection()
        if not selection:
            return

        selected_item = selection[0]
        new_filter = '' if selected_item == '__ALL__' else selected_item
        if new_filter == self._get_category_filter_value():
            return

        self._selected_category_filter = new_filter
        self._on_search_change()

    def _rebuild_category_filter_tree(self, select_current: bool = True):
        tree = getattr(self, 'category_filter_tree', None)
        if tree is None:
            return

        selected = self._get_category_filter_value()
        counts = self.logic.get_category_counts_with_descendants(self.logic.papers)
        roots, children_map, _ = self.logic.build_category_hierarchy()

        self._updating_category_filter_tree = True
        try:
            for item in tree.get_children():
                tree.delete(item)

            tree.insert('', 'end', iid='__ALL__', text='All Categories', values=(len(self.logic.papers),))

            def insert_node(parent_id, cat):
                unique_name = cat.get('unique_name', '')
                if not unique_name:
                    return
                tree.insert(
                    parent_id,
                    'end',
                    iid=unique_name,
                    text=cat.get('name', unique_name),
                    values=(counts.get(unique_name, 0),),
                    open=True,
                )
                for child in children_map.get(unique_name, []):
                    insert_node(unique_name, child)

            for root in roots:
                insert_node('', root)

            if select_current:
                target = selected if selected and tree.exists(selected) else '__ALL__'
                tree.selection_set(target)
                tree.focus(target)
                tree.see(target)
                if target == '__ALL__':
                    self._selected_category_filter = ''
        finally:
            self._updating_category_filter_tree = False

    def _apply_search_hit_highlight(self, real_idx: int):
        for label in self.field_labels.values():
            try:
                label.configure(style='TLabel')
            except Exception:
                pass

        for widget in self.form_fields.values():
            if isinstance(widget, scrolledtext.ScrolledText):
                self._clear_text_widget_search_highlight(widget)

        if real_idx < 0:
            self._update_search_hit_preview(real_idx)
            return
        if not self._get_search_keyword():
            self._update_search_hit_preview(real_idx)
            return

        matched_fields = self._search_hit_fields_by_real_idx.get(real_idx, set())
        for variable in matched_fields:
            label = self.field_labels.get(variable)
            if label is None:
                continue
            try:
                label.configure(style='SearchHit.TLabel')
            except Exception:
                pass

            widget = self.form_fields.get(variable)
            if isinstance(widget, scrolledtext.ScrolledText):
                self._highlight_keyword_in_text_widget(widget, self._get_search_keyword())

        self._update_search_hit_preview(real_idx)

    def _clear_text_widget_search_highlight(self, widget: scrolledtext.ScrolledText):
        try:
            widget.tag_remove('SearchHitTextKeyword', '1.0', tk.END)
        except Exception:
            pass

    def _highlight_keyword_in_text_widget(self, widget: scrolledtext.ScrolledText, keyword: str):
        self._clear_text_widget_search_highlight(widget)
        kw = (keyword or '').strip()
        if not kw:
            return

        widget.tag_configure('SearchHitTextKeyword', background="#FFE58F")
        start = '1.0'
        while True:
            pos = widget.search(kw, start, stopindex=tk.END, nocase=True)
            if not pos:
                break
            end_pos = f"{pos}+{len(kw)}c"
            widget.tag_add('SearchHitTextKeyword', pos, end_pos)
            start = end_pos

    def _update_search_hit_preview(self, real_idx: int):
        panel = getattr(self, 'search_hit_preview', None)
        if panel is None:
            return

        keyword = self._get_search_keyword().strip()
        matched_fields = self._search_hit_fields_by_real_idx.get(real_idx, set()) if real_idx >= 0 else set()
        if real_idx < 0 or not keyword or not matched_fields:
            panel.config(state='normal')
            panel.delete('1.0', tk.END)
            panel.config(state='disabled')
            panel.grid_remove()
            return

        paper = self.logic.papers[real_idx] if 0 <= real_idx < len(self.logic.papers) else None
        if paper is None:
            panel.config(state='normal')
            panel.delete('1.0', tk.END)
            panel.config(state='disabled')
            panel.grid_remove()
            return

        panel.config(state='normal')
        panel.delete('1.0', tk.END)

        ordered_vars = [v for v in self._keyword_field_options if v in matched_fields]
        for variable in ordered_vars:
            raw_text = self._get_paper_field_text(paper, variable).replace('\n', ' ')
            if not raw_text:
                continue

            lower_text = raw_text.lower()
            lower_kw = keyword.lower()
            hit_pos = lower_text.find(lower_kw)
            if hit_pos < 0:
                continue

            left = max(0, hit_pos - 24)
            right = min(len(raw_text), hit_pos + len(keyword) + 24)
            prefix = raw_text[left:hit_pos]
            hit = raw_text[hit_pos:hit_pos + len(keyword)]
            suffix = raw_text[hit_pos + len(keyword):right]

            display_name = self._keyword_field_name_map.get(variable, variable)
            panel.insert(tk.END, f"{display_name}: ")
            panel.insert(tk.END, "..." if left > 0 else "")
            panel.insert(tk.END, prefix)
            kw_start = panel.index(tk.INSERT)
            panel.insert(tk.END, hit)
            kw_end = panel.index(tk.INSERT)
            panel.tag_add('SearchHitPreviewKeyword', kw_start, kw_end)
            panel.insert(tk.END, suffix)
            panel.insert(tk.END, "..." if right < len(raw_text) else "")
            panel.insert(tk.END, "\n")

        content = panel.get('1.0', tk.END).strip()
        panel.config(state='disabled')
        if content:
            panel.grid()
        else:
            panel.grid_remove()

    def _resolve_tree_target_indices(self, item_id: str) -> Tuple[int, int]:
        if not item_id:
            return -1, -1

        try:
            real_index = int(item_id)
        except (TypeError, ValueError):
            self.update_status("列表选择异常：无效条目标识，已忽略")
            return -1, -1

        if real_index in self.filtered_indices:
            return self.filtered_indices.index(real_index), real_index
        self.update_status("列表选择异常：条目不在当前筛选结果中，已忽略")
        return -1, -1

    def _restore_previous_tree_selection(self, prev_display_index: int):
        self._suppress_select_event = True
        try:
            if prev_display_index is not None and 0 <= prev_display_index < len(self.filtered_indices):
                old_real = self.filtered_indices[prev_display_index]
                if self._select_tree_item_by_real_index(old_real, focus_item=True, see_item=True):
                    return

            cur_sel = self.paper_tree.selection()
            if cur_sel:
                self.paper_tree.selection_remove(*cur_sel)
        finally:
            self.paper_tree.after_idle(lambda: setattr(self, '_suppress_select_event', False))

    def _select_tree_item_by_real_index(self, real_index: int, focus_item: bool = True, see_item: bool = True) -> bool:
        item_id = str(real_index)
        if not self.paper_tree.exists(item_id):
            return False
        self.paper_tree.selection_set(item_id)
        if focus_item:
            self.paper_tree.focus(item_id)
        if see_item:
            self.paper_tree.see(item_id)
        return True

    def _select_tree_item_by_display_index(self, display_index: int, focus_item: bool = True, see_item: bool = True) -> bool:
        children = self.paper_tree.get_children()
        if display_index < 0 or display_index >= len(children):
            return False
        item_id = children[display_index]
        self.paper_tree.selection_set(item_id)
        if focus_item:
            self.paper_tree.focus(item_id)
        if see_item:
            self.paper_tree.see(item_id)
        return True

    def _confirm_before_switch_or_restore(self, prev_display_index: int, show_popup: bool = True) -> bool:
        self._confirm_all_pending_file_fields_for_current_paper(show_popup=show_popup, block_on_error=False)
        return True

    def _load_selected_paper(self, display_index: int, real_index: int) -> bool:
        if display_index < 0 or real_index < 0:
            self.update_status("加载论文失败：索引异常")
            return False
        if real_index >= len(self.logic.papers):
            self.update_status("加载论文失败：索引越界")
            return False

        self.current_paper_index = display_index
        paper = self.logic.papers[real_index]
        self.show_form()
        self.load_paper_to_form(paper)
        self._validate_all_fields_visuals(real_index)
        self.update_status(f"正在编辑: {paper.title[:30]}...")
        return True

    def _activate_paper_by_real_index(self, real_index: int) -> bool:
        if real_index not in self.filtered_indices:
            return False
        display_index = self.filtered_indices.index(real_index)
        if not self._select_tree_item_by_real_index(real_index, focus_item=True, see_item=True):
            self.update_status("激活论文失败：列表项不存在")
            return False
        return self._load_selected_paper(display_index, real_index)


    def on_paper_selected(self, event):
        if self._suppress_select_event or self._handling_paper_selection:
            return
        self._handling_paper_selection = True
        try:
            prev_display_index = self.current_paper_index
            selection = self.paper_tree.selection()
            if not selection:
                self.current_paper_index = -1
                self.show_placeholder()
                return

            target_display_index, target_real_index = self._resolve_tree_target_indices(selection[0])
            if target_display_index < 0 or target_real_index < 0:
                return

            if prev_display_index == target_display_index:
                self._load_selected_paper(target_display_index, target_real_index)
                return

            # 键盘切换时兜底：切换论文前先执行 file 字段确认逻辑
            if self._skip_next_selection_confirm:
                self._skip_next_selection_confirm = False
            else:
                if not self._confirm_before_switch_or_restore(prev_display_index, show_popup=True):
                    return

            self._load_selected_paper(target_display_index, target_real_index)
        finally:
            self._handling_paper_selection = False

    def _on_tree_left_button(self, event):
        self.drag_item = None
        self._drag_press_item = None
        self._drag_press_xy = None
        self._destroy_drag_ghost()

        if self._suppress_select_event or self._handling_paper_selection:
            return None

        clicked_item = self.paper_tree.identify_row(event.y)
        if not clicked_item:
            return None

        _, target_real_idx = self._resolve_tree_target_indices(clicked_item)
        if target_real_idx < 0:
            return None

        current_real_idx = self._get_current_real_index()

        if current_real_idx >= 0 and target_real_idx != current_real_idx:
            self._skip_next_selection_confirm = True
            if not self._confirm_before_switch_or_restore(self.current_paper_index, show_popup=True):
                return "break"

        # 仅在按下当前已选中项时进入“待拖拽”状态，移动超过阈值后才真正开始拖拽
        if current_real_idx >= 0 and target_real_idx == current_real_idx:
            self._drag_press_item = clicked_item
            self._drag_press_xy = (event.x, event.y)
        return None

    def load_paper_to_form(self, paper):
        self._disable_callbacks = True
        real_idx = self._get_current_real_index()
        
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
                    unique_names = [v.strip() for v in str(value).split('|') if v.strip()]
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

                elif variable == 'pipeline_image':
                    self._pipeline_set_rows_from_value(variable, str(value))
                
                elif isinstance(widget, ttk.Combobox): widget.set(str(value) if value else "")
                elif isinstance(widget, tk.BooleanVar): widget.set(bool(value))
                elif isinstance(widget, scrolledtext.ScrolledText):
                    widget.delete(1.0, tk.END)
                    widget.insert(1.0, str(value))
                    widget.edit_reset()
                elif isinstance(widget, tk.Entry):
                    widget.delete(0, tk.END)
                    widget.insert(0, str(value))

                if variable in ['pipeline_image', 'paper_file']:
                    state = self._file_field_states.get(variable, {})
                    state['last_confirmed'] = str(value)
                    self._update_file_confirm_button_state(variable)
                    if real_idx >= 0:
                        self._validate_single_field_visuals(variable, real_idx)
            self._apply_search_hit_highlight(real_idx)
        finally: self._disable_callbacks = False

    def _on_field_change(self, variable, widget_or_var):
        if getattr(self, '_disable_callbacks', False): return
        real_idx = self._get_current_real_index()
        if real_idx < 0:
            return

        # 获取真实论文对象
        current_paper = self.logic.papers[real_idx]
        old_value = getattr(current_paper, variable, "")
        
        new_value = ""
        if variable == 'category': pass
        elif isinstance(widget_or_var, tk.StringVar): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, tk.BooleanVar): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, tk.Variable): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, scrolledtext.ScrolledText): new_value = widget_or_var.get(1.0, tk.END).strip()
        elif isinstance(widget_or_var, ttk.Combobox): new_value = widget_or_var.get()
        elif isinstance(widget_or_var, tk.Entry): new_value = widget_or_var.get()

        if variable == 'conflict_marker':
            old_bool = bool(old_value)
            new_bool = bool(new_value)

            # 存在基论文时，禁止直接取消冲突标记，要求走“处理冲突”流程
            if old_bool and not new_bool:
                base_idx = self.logic.find_base_paper_index(real_idx)
                if base_idx != -1:
                    messagebox.showwarning(
                        "冲突处理提示",
                        "检测到该冲突条目存在基论文，不能直接取消冲突标记。\n请在左侧列表右键该条目，使用“⚔️ 处理冲突...”完成合并。"
                    )
                    return

            # 勾选冲突标记后，同步状态字段
            if new_bool and hasattr(current_paper, 'status'):
                setattr(current_paper, 'status', 'conflict')
                status_widget = self.form_fields.get('status')
                if status_widget is not None:
                    self._disable_callbacks = True
                    try:
                        if isinstance(status_widget, ttk.Combobox):
                            status_widget.set('conflict')
                        elif isinstance(status_widget, tk.Entry):
                            status_widget.delete(0, tk.END)
                            status_widget.insert(0, 'conflict')
                    finally:
                        self._disable_callbacks = False
        
        setattr(current_paper, variable, new_value)
        self._validate_single_field_visuals(variable, real_idx)

        # 任意字段变化都可能影响 Invalid/Conflict/New/OK 状态显示
        self._refresh_list_item(self.current_paper_index, current_paper)

    def _on_conflict_marker_click(self, event, bool_var):
        """在复选框切换前拦截：存在基论文时禁止直接取消冲突标记。"""
        if getattr(self, '_disable_callbacks', False):
            return None
        if self._get_current_real_index() < 0:
            return "break"

        # 当前值为 True 时，点击后将变为 False（取消勾选）
        try:
            will_uncheck = bool(bool_var.get())
        except Exception:
            will_uncheck = False

        if will_uncheck:
            real_idx = self._get_current_real_index()
            if real_idx >= 0:
                base_idx = self.logic.find_base_paper_index(real_idx)
                if base_idx != -1:
                    messagebox.showwarning(
                        "冲突处理提示",
                        "检测到该冲突条目存在基论文，不能直接取消冲突标记。\n请在左侧列表右键该条目，使用“⚔️ 处理冲突...”完成合并后自动取消。"
                    )
                    return "break"

        return None

    def _on_category_change(self, variable=None, widget_or_var=None):
        if getattr(self, '_disable_callbacks', False): return
        real_idx = self._get_current_real_index()
        if real_idx < 0:
            return
        current_paper = self.logic.papers[real_idx]
        
        unique_names = self._gui_get_category_values()
        cat_str = "|".join(unique_names)
        current_paper.category = cat_str
        
        self._validate_single_field_visuals('category', real_idx)
        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())
        if real_idx in self.filtered_indices:
            self._activate_paper_by_real_index(real_idx)
        else:
            self.current_paper_index = -1
            self.show_placeholder()

    def _get_list_status_and_tags(self, paper):
        is_valid, _, _ = paper.validate_paper_fields(self.config, True, True, no_normalize=True)
        if not is_valid:
            return "Invalid", ('invalid',)
        if paper.conflict_marker:
            return "Conflict", ('conflict',)
        if not paper.doi:
            return "New", ()
        return "OK", ()

    def _refresh_list_item(self, display_index, paper):
        """更新列表中的单项显示"""
        children = self.paper_tree.get_children()
        if display_index < len(children):
            real_idx = self.filtered_indices[display_index]
            status_str, tags = self._get_list_status_and_tags(paper)
            values = tuple(
                status_str if col == 'Status' else self._get_list_column_display_value(paper, real_idx, col)
                for col in self._get_visible_list_columns()
            )

            self.paper_tree.item(children[display_index], values=values, tags=tags)

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
            paper_idx = self._get_current_real_index()
            if paper_idx < 0:
                return
            
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

        if variable == 'pipeline_image':
            self._apply_pipeline_row_styles(is_required, is_empty)
            return
        
        try:
            if isinstance(widget, scrolledtext.ScrolledText): widget.config(background=bg_color)
            elif isinstance(widget, tk.Entry): widget.config(background=bg_color)
            elif isinstance(widget, ttk.Combobox):
                style_name = "TCombobox"
                if bg_color == self.color_invalid: style_name = "Invalid.TCombobox"
                elif bg_color == self.color_required_empty: style_name = "Required.TCombobox"
                widget.configure(style=style_name)
        except: pass

    def _apply_pipeline_row_styles(self, is_required: bool, is_empty: bool):
        state = self._file_field_states.get('pipeline_image', {})
        rows = state.get('rows', [])
        if not rows:
            return

        for idx, row_data in enumerate(rows):
            entry = row_data.get('entry')
            sv = row_data.get('sv')
            if entry is None or sv is None:
                continue

            raw_val = (sv.get() or '').strip()
            row_bg = self.color_normal

            if is_required and is_empty and idx == 0:
                row_bg = self.color_required_empty

            if raw_val:
                ok, _ = self.logic.validate_single_asset_reference('pipeline_image', raw_val)
                if not ok:
                    row_bg = self.color_invalid

            try:
                entry.config(background=row_bg)
            except Exception:
                pass

    # ================= 业务操作按钮 =================

    def add_paper(self):
        new_paper = self.logic.create_new_paper()
        selected_category = self._get_category_filter_value()
        if selected_category:
            new_paper.category = selected_category
        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())
        
        # 选中最后一个
        new_display_idx = len(self.filtered_indices) - 1
        if new_display_idx >= 0:
            self._suppress_select_event = True
            try:
                selected_ok = self._select_tree_item_by_display_index(new_display_idx, focus_item=True, see_item=True)
            finally:
                self._suppress_select_event = False

            real_idx = self.filtered_indices[new_display_idx]
            if selected_ok and self._load_selected_paper(new_display_idx, real_idx):
                self.update_status("已创建新论文")
                self.root.after(50, self._focus_first_editable_field)

    def _focus_first_editable_field(self):
        for key in ['doi', 'title', 'authors', 'abstract']:
            w = self.form_fields.get(key)
            if isinstance(w, tk.Entry):
                try:
                    w.focus_force()
                    w.icursor(tk.END)
                    return
                except Exception:
                    pass

    def delete_paper(self):
        if not self._require_selected_paper("警告", "请先选择一篇论文"):
            return
        if messagebox.askyesno("确认", "确定要删除这篇论文吗？"):
            real_idx = self._get_current_real_index()
            if real_idx < 0:
                return
            if self.logic.delete_paper(real_idx):
                self._reset_list_after_data_change(self._get_search_keyword(), self._get_category_filter_value())
                self.update_status("论文已删除")

    def clear_papers(self):
        if not self.logic.papers: return
        if messagebox.askyesno("警告", "警告！确定要清空所有论文吗？"):
            if messagebox.askyesno("警告", "二次警告！确定要清空？"):
                self.logic.clear_papers()
                self._reset_list_after_data_change()
                self.update_status("所有论文已清空")

    def save_all_papers(self) -> bool:
        if not self.logic.papers:
            messagebox.showwarning("警告", "没有论文可以保存")
            return False

        if not self._confirm_all_pending_file_fields_for_current_paper(show_popup=True):
            return False
        
        # 1. 验证
        invalid_papers = self.logic.validate_papers_for_save()
        if invalid_papers:
            msg = "以下论文未通过验证，建议修正:\n\n" + "\n".join([f"#{i} {t[:20]}..." for i, t, e in invalid_papers[:5]])
            if self._get_save_validation_strategy() == 'lenient':
                if not messagebox.askyesno("验证警告", msg + "\n\n是否仍要继续保存？"):
                    return False
            else:
                messagebox.showwarning("验证失败", msg + "\n\n当前为 strict 模式，已阻止保存。")
                return False

        # 2. 选择路径
        initial_file = os.path.basename(self.logic.current_file_path) if self.logic.current_file_path else "submit_template.json"
        target_path = filedialog.asksaveasfilename(
            title="选择保存位置", 
            defaultextension='.json', 
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
            initialfile=initial_file,
            initialdir=BASE_DIR
        )
        if not target_path:
            return False

        # 3. 判断是否为数据库
        is_db = self.logic._is_database_file(target_path)
        
        if is_db:
            if not self.logic.is_admin:
                messagebox.showerror("权限错误", "写入数据库需要管理员权限。")
                return False
            if messagebox.askyesno("警告", "正在写入核心数据库！\n\n数据库模式仅支持【全量重写】。\n这将用当前列表完全覆盖数据库内容。\n\n是否继续？"):
                self.logic.save_to_file_rewrite(target_path)
                self._set_current_loaded_file(target_path)
                messagebox.showinfo("成功", "数据库已更新")
                return True
            return False

        # 4. 普通文件：使用简单的 Yes/No/Cancel 对话框
        # Yes = 增量, No = 重写, Cancel = 取消
        choice = messagebox.askyesnocancel("选择保存模式", 
            "请选择保存模式：\n\n"
            "【是 (Yes)】：增量模式 (增量合并)\n"
            "   - 追加更新，保证原有内容不会丢失。\n"
            "   - 若遇重复项，将逐一询问覆盖或跳过。\n\n"
            "【否 (No)】：重写模式 (完全覆盖)\n"
            "   - 完全替换目标文件内容。\n"
            "   - 当前工作区将完全覆盖目标文件。")
        
        if choice is None:
            return False # Cancel

        try:
            if choice is False: # No -> Rewrite
                self.logic.save_to_file_rewrite(target_path)
                self._set_current_loaded_file(target_path)
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
                            return False
                        
                        key = p.get_key()
                        decisions[key] = 'overwrite' if res else 'skip'
                
                self.logic.save_to_file_incremental(target_path, decisions)
                self._set_current_loaded_file(target_path)
                messagebox.showinfo("成功", "增量保存完成")
            return True
                
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return False

    def submit_pr(self):
        if not messagebox.askyesno("须知", f"将自动通过 PR 提交论文...\n\n1. 创建新分支\n2. 提交更新文件和 Assets 资源\n3. 推送并创建 PR"): return
        def _has_primary_update_file() -> bool:
            p = self.logic.primary_update_file
            return bool(p and os.path.exists(p))
        
        if not _has_primary_update_file():
             if messagebox.askyesno("确认", "未检测到有效更新文件，是否先保存当前内容？"): 
                if not self.save_all_papers():
                    return
                if not _has_primary_update_file(): return # 用户取消保存
        
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

    def _confirm_replace_workspace_before_load(self) -> bool:
        """在已有工作区内容时，确认是否允许加载新文件覆盖。"""
        if not self.logic.papers:
            return True
        return bool(messagebox.askyesno("确认", "加载新文件将覆盖当前工作区。\n\n是否继续？(建议先保存)"))

    def _ensure_admin_for_db_load(self, title: str, prompt: str) -> bool:
        """确保具备数据库加载权限；若无权限则引导切换管理员模式。"""
        if self.logic.is_admin:
            return True
        if messagebox.askyesno(title, prompt):
            self._toggle_admin_mode()
        return bool(self.logic.is_admin)

    def _apply_loaded_workspace_state(self, path: str, count: int, status_text: str, show_success: bool = True):
        """统一处理加载成功后的 UI 状态刷新。"""
        self.refresh_list_view()
        self.current_paper_index = -1
        self.show_placeholder()
        self._set_current_loaded_file(path)
        self.update_status(status_text)
        if show_success:
            fname = os.path.basename(path)
            messagebox.showinfo("成功", f"已从 {fname} 加载 {count} 篇论文")

    def load_template(self):
        if not self._confirm_all_pending_file_fields_for_current_paper(show_popup=True):
            return
        if not self._confirm_replace_workspace_before_load():
            return
            
        path = filedialog.askopenfilename(title="选择文件", filetypes=[("Data", "*.json *.csv")])
        if not path: return
        
        try:
            cnt = self.logic.load_papers_from_file(path)
            self._apply_loaded_workspace_state(
                path,
                cnt,
                status_text=f"当前文件: {os.path.basename(path)}",
                show_success=True,
            )
            
        except PermissionError:
            if self._ensure_admin_for_db_load("需要管理员权限", "加载核心数据库文件需要管理员权限。\n\n是否立即切换模式？"):
                self.load_template()
        except Exception as e:
            messagebox.showerror("Error", f"加载失败: {e}")

    def _open_database_action(self):
        """打开数据库文件的快捷操作"""
        if not self._confirm_all_pending_file_fields_for_current_paper(show_popup=True):
            return
        if not self._confirm_replace_workspace_before_load():
            return
            
        if not self._ensure_admin_for_db_load("权限限制", "加载核心数据库需要管理员权限。\n是否立即切换模式？"):
            return
        
        db_path = os.path.join(BASE_DIR, self.config.settings['paths']['database'])
        try:
            cnt = self.logic.load_papers_from_file(db_path)
            self._apply_loaded_workspace_state(
                db_path,
                cnt,
                status_text=f"已加载数据库: {os.path.basename(db_path)}",
                show_success=False,
            )
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _set_current_loaded_file(self, file_path: str):
        if not hasattr(self, 'current_file_var'):
            return
        if not file_path:
            self.current_file_var.set("(未加载)")
            self._refresh_status_bar_text()
            return
        abs_path = file_path if os.path.isabs(file_path) else os.path.join(BASE_DIR, file_path)
        abs_path = os.path.abspath(abs_path)
        name = os.path.basename(abs_path)
        self.current_file_var.set(f"{name}({abs_path})")
        self._refresh_status_bar_text()

    def _get_current_loaded_file(self) -> str:
        value = self.current_file_var.get().strip() if hasattr(self, 'current_file_var') else ''
        if not value or value == '(未加载)':
            return ''
        if value.endswith(')') and '(' in value:
            left = value.rfind('(')
            candidate = value[left + 1:-1].strip()
            if candidate:
                return candidate
        return value

    def _resolve_existing_path(self, raw_path: str, empty_msg: str = "路径为空") -> Optional[str]:
        """统一路径解析与存在性检查，失败时直接弹窗并返回 None。"""
        if not raw_path:
            messagebox.showwarning("提示", empty_msg)
            return None
        abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(BASE_DIR, raw_path)
        abs_path = os.path.normpath(os.path.abspath(abs_path))
        if not os.path.exists(abs_path):
            messagebox.showerror("错误", f"文件不存在: {abs_path}")
            return None
        return abs_path

    def _open_file_direct(self, file_path: str, choose_app: bool = False):
        abs_path = self._resolve_existing_path(file_path)
        if not abs_path:
            return
        try:
            if sys.platform == 'win32':
                if os.path.isdir(abs_path):
                    os.startfile(abs_path)
                    return
                if choose_app:
                    launched = False
                    errors: List[str] = []
                    try:
                        proc = subprocess.Popen(['rundll32.exe', 'shell32.dll,OpenAs_RunDLL', abs_path])
                        time.sleep(0.35)
                        rc = proc.poll()
                        if rc is not None:
                            errors.append(f"OpenAs_RunDLL exited quickly rc={rc}")
                    except Exception as ex:
                        errors.append(f"OpenAs_RunDLL: {ex}")

                    if not launched:
                        try:
                            import ctypes
                            rc = ctypes.windll.shell32.ShellExecuteW(None, 'openas', abs_path, None, None, 1)
                            if rc <= 32:
                                errors.append(f"ShellExecute openas rc={rc}")
                            else:
                                errors.append("ShellExecute openas invoked")
                        except Exception as ex:
                            errors.append(f"ShellExecute openas: {ex}")

                    if not launched:
                        try:
                            escaped_path = abs_path.replace("'", "''")
                            result = subprocess.run(
                                [
                                    'powershell',
                                    '-NoProfile',
                                    '-Command',
                                    f"Start-Process -LiteralPath '{escaped_path}' -Verb OpenAs"
                                ],
                                check=False,
                                capture_output=True,
                                text=True,
                            )
                            if result.returncode != 0:
                                stderr_msg = (result.stderr or '').strip()
                                stdout_msg = (result.stdout or '').strip()
                                detail = stderr_msg or stdout_msg or f"returncode={result.returncode}"
                                errors.append(f"PowerShell OpenAs: {detail}")
                            else:
                                errors.append("PowerShell OpenAs invoked")
                        except Exception as ex:
                            errors.append(f"PowerShell OpenAs: {ex}")

                    try:
                        os.startfile(abs_path)
                        messagebox.showwarning("提示", "若“打开方式”未弹出，已自动改为默认程序打开。")
                        launched = True
                    except Exception as ex:
                        errors.append(f"默认程序打开失败: {ex}")

                    if not launched:
                        detail = '\n'.join(errors[-4:]) if errors else 'unknown error'
                        raise RuntimeError(f"打开方式与默认打开均失败\n{detail}")
                else:
                    os.startfile(abs_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', abs_path])
            else:
                subprocess.run(['xdg-open', abs_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开: {e}")

    def _reveal_in_file_manager(self, path: str, select_file: bool = True):
        abs_path = self._resolve_existing_path(path)
        if not abs_path:
            return
        try:
            if sys.platform == 'win32':
                if select_file and os.path.isfile(abs_path):
                    subprocess.Popen(['explorer.exe', '/select,', abs_path])
                else:
                    target_dir = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
                    os.startfile(os.path.normpath(target_dir))
            elif sys.platform == 'darwin':
                if select_file and os.path.isfile(abs_path):
                    subprocess.run(['open', '-R', abs_path])
                else:
                    target_dir = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
                    subprocess.run(['open', target_dir])
            else:
                target_dir = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
                subprocess.run(['xdg-open', target_dir])
        except Exception as e:
            messagebox.showerror("错误", f"无法定位文件: {e}")

    def open_current_file(self):
        target = self._get_current_loaded_file() or self.logic.current_file_path or self.logic.primary_update_file
        if not target:
            return messagebox.showwarning("提示", "当前没有活跃文件")
        self._open_file_direct(target)

    def cleanup_redundant_assets(self):
        if not messagebox.askyesno("确认", "将按【数据库文件】引用关系清理冗余 assets 资源，是否继续？"):
            return

        try:
            confirmed, include_update_files = self._show_cleanup_preview_dialog()
            if not confirmed:
                self.update_status("已取消清理（仅完成预览）")
                return

            if not include_update_files:
                continue_without_updates = messagebox.askyesno(
                    "二次确认",
                    "你选择了不包含更新文件。\n"
                    "这可能误删尚未更新到数据库、但仍被更新文件引用的资源。\n\n"
                    "是否仍继续？"
                )
                if not continue_without_updates:
                    self.update_status("已取消清理")
                    return

            report = self.logic.cleanup_redundant_assets(
                include_update_files=include_update_files,
                execute_delete=True
            )

            deleted_uid = report.get('deleted_uid_dirs', [])
            deleted_files = report.get('deleted_files', [])
            unref = report.get('papers_with_unreferenced_assets', [])
            missing = report.get('missing_references', [])
            invalid_suffix = report.get('invalid_suffix_references', [])
            nonstandard = report.get('nonstandard_references', [])

            lines = [
                f"对比基准: {'数据库 + 当前GUI工作区 + 更新文件' if include_update_files else '数据库 + 当前GUI工作区'}",
                f"已删除未引用 UID 文件夹: {len(deleted_uid)}",
                f"已删除未引用资源文件: {len(deleted_files)}",
                f"存在未被字段引用资源的论文UID: {len(unref)}",
                f"存在引用丢失文件的条目: {len(missing)}",
                f"存在后缀不匹配引用的条目: {len(invalid_suffix)}",
                f"存在路径非规范(非 assets/<uid>)的条目: {len(nonstandard)}",
                "",
            ]

            if unref:
                lines.append("[未被字段引用的论文资源]")
                for item in unref[:50]:
                    title = (item.get('title', '') or '')[:30]
                    lines.append(f"- {title} | uid={item.get('uid')} files={len(item.get('files', []))}")
                lines.append("")

            if missing:
                lines.append("[引用丢失资源]")
                for item in missing[:50]:
                    lines.append(f"- {item.get('title', '')[:30]} | {item.get('field')} -> {item.get('reference')}")

            if invalid_suffix:
                lines.append("\n[后缀不匹配引用]")
                for item in invalid_suffix[:50]:
                    lines.append(f"- {item.get('title', '')[:30]} | {item.get('field')} -> {item.get('reference')}")

            if nonstandard:
                lines.append("\n[路径非规范引用]")
                for item in nonstandard[:50]:
                    lines.append(f"- {item.get('title', '')[:30]} | {item.get('field')} -> {item.get('reference')}")

            _, report_status_var, report_append, _ = self._open_timestamped_output_session(
                title_base="清理完成报告",
                status_text="清理完成",
                include_header_separator=False,
            )
            report_append("\n".join(lines[:300]))
            report_status_var.set("清理完成（详见报告窗口）")
            self.update_status("冗余资源清理完成")
        except Exception as e:
            messagebox.showerror("清理失败", str(e))

    def _show_cleanup_preview_dialog(self) -> Tuple[bool, bool]:
        """清理预览弹窗（分类折叠展示，可选择是否包含更新文件）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("清理预览")
        dialog.transient(self.root)
        dialog.geometry("1180x860")
        dialog.minsize(980, 680)

        result = {'confirmed': False}
        include_var = tk.BooleanVar(value=True)
        nonempty_update_files = self.logic.get_nonempty_update_files()
        report_holder: Dict[str, Any] = {'report': {}}

        main = ttk.Frame(dialog, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        summary_var = tk.StringVar(value="正在加载预览...")
        ttk.Label(main, textvariable=summary_var, justify=tk.LEFT).pack(anchor='w', pady=(0, 8))

        opt_row = ttk.Frame(main)
        opt_row.pack(fill=tk.X, pady=(0, 8))
        include_cb = ttk.Checkbutton(
            opt_row,
            text="包含配置中的更新文件（默认包含）",
            variable=include_var,
        )
        include_cb.pack(side=tk.LEFT)

        update_hint = f"检测到有内容的更新文件: {len(nonempty_update_files)}"
        ttk.Label(opt_row, text=update_hint, foreground="gray").pack(side=tk.LEFT, padx=(12, 0))

        canvas_wrap = ttk.Frame(main)
        canvas_wrap.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(canvas_wrap)
        vbar = ttk.Scrollbar(canvas_wrap, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        content = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=content, anchor='nw')

        def _on_content_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def _on_canvas_configure(event):
            canvas.itemconfigure(win, width=event.width)

        content.bind('<Configure>', _on_content_configure)
        canvas.bind('<Configure>', _on_canvas_configure)

        def _format_issue(item: Dict[str, Any]) -> str:
            title = (item.get('title', '') or '')[:24]
            return f"{title} | {item.get('field')} -> {item.get('reference')}"

        def _render_sections(report: Dict[str, Any]):
            for child in content.winfo_children():
                child.destroy()

            would_delete_uid = report.get('would_delete_uid_dirs', [])
            would_delete_files = report.get('would_delete_files', [])
            missing_preview = report.get('missing_references', [])
            invalid_suffix_preview = report.get('invalid_suffix_references', [])
            nonstandard_preview = report.get('nonstandard_references', [])

            sections = [
                ("将删除 UID 文件夹", [str(x) for x in would_delete_uid], True),
                ("将删除资源文件", [str(x) for x in would_delete_files], True),
                ("引用丢失", [_format_issue(x) for x in missing_preview], False),
                ("后缀不匹配", [_format_issue(x) for x in invalid_suffix_preview], False),
                ("路径非规范(非 assets/<uid>)", [_format_issue(x) for x in nonstandard_preview], False),
            ]

            for sec_title, lines, default_expand in sections:
                sec_frame = ttk.Frame(content)
                sec_frame.pack(fill=tk.X, pady=(0, 6))

                state = {'expanded': default_expand}
                btn = ttk.Button(sec_frame, text="")
                btn.pack(anchor='w')

                body = ttk.Frame(sec_frame)
                body.pack(fill=tk.X, pady=(2, 0))

                max_preview = 120
                shown = lines[:max_preview]
                extra = len(lines) - len(shown)
                body_text = "\n".join([f"- {x}" for x in shown]) if shown else "(无)"
                if extra > 0:
                    body_text += f"\n... 其余 {extra} 项省略"

                if sec_title == "将删除资源文件":
                    text_height = 15
                elif sec_title in ("将删除 UID 文件夹", "路径非规范(非 assets/<uid>)"):
                    text_height = 15
                else:
                    text_height = 15

                text = tk.Text(body, height=text_height, wrap='word')
                text.insert('1.0', body_text)
                text.configure(state='disabled')
                text.pack(fill=tk.X, expand=True)

                def _toggle(_body=body, _state=state, _btn=btn, _title=sec_title, _count=len(lines)):
                    _state['expanded'] = not _state['expanded']
                    if _state['expanded']:
                        _body.pack(fill=tk.X, pady=(2, 0))
                        _btn.config(text=f"▼ {_title} ({_count})")
                    else:
                        _body.pack_forget()
                        _btn.config(text=f"▶ {_title} ({_count})")

                btn.config(command=_toggle)
                if state['expanded']:
                    btn.config(text=f"▼ {sec_title} ({len(lines)})")
                else:
                    body.pack_forget()
                    btn.config(text=f"▶ {sec_title} ({len(lines)})")

            _on_content_configure()

        def _reload_preview():
            include_updates = bool(include_var.get())
            report = self.logic.cleanup_redundant_assets(
                include_update_files=include_updates,
                execute_delete=False,
            )
            report_holder['report'] = report

            summary = (
                f"对比基准: {'数据库 + 当前GUI工作区 + 更新文件' if include_updates else '数据库 + 当前GUI工作区'}\n"
                f"将删除未引用 UID 文件夹: {len(report.get('would_delete_uid_dirs', []))} | "
                f"将删除未引用资源文件: {len(report.get('would_delete_files', []))} | "
                f"引用丢失: {len(report.get('missing_references', []))} | "
                f"后缀不匹配: {len(report.get('invalid_suffix_references', []))} | "
                f"路径非规范: {len(report.get('nonstandard_references', []))}"
            )
            summary_var.set(summary)
            _render_sections(report)

        include_cb.configure(command=_reload_preview)
        _reload_preview()

        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(10, 0))

        def _confirm():
            result['confirmed'] = True
            dialog.destroy()

        def _cancel():
            result['confirmed'] = False
            dialog.destroy()

        ttk.Button(btn_row, text="取消", command=_cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="确认执行删除", command=_confirm).pack(side=tk.RIGHT)

        dialog.protocol("WM_DELETE_WINDOW", _cancel)
        dialog.grab_set()
        dialog.focus_set()
        self.root.wait_window(dialog)
        return bool(result['confirmed']), bool(include_var.get())

    def run_update_script(self):
        if not messagebox.askyesno(
            "运行更新",
            "该按钮会执行更新流程：将更新文件合并到数据库，并尝试生成 README。\n"
            "这会修改核心数据库文件。\n\n"
            "运行后会在文本日志窗口中显示详细结果与错误信息。\n\n"
            "是否继续？"
        ):
            return

        cmd = [sys.executable, os.path.join(BASE_DIR, "src/update.py")]
        self._run_command_with_output_window(
            title_base="更新脚本输出",
            cmd=cmd,
            status_running="正在运行更新脚本...",
            status_done="更新脚本执行完成",
        )

    def run_validate_script(self):
        if not messagebox.askyesno(
            "运行验证",
            "该按钮会执行统一验证流程：检查数据库和更新文件的完整性、冲突及资源引用。\n\n"
            "运行后会在文本日志窗口中显示详细结果与错误信息。\n\n"
            "是否继续？"
        ):
            return

        cmd = [sys.executable, os.path.join(BASE_DIR, "src/validate.py")]
        self._run_command_with_output_window(
            title_base="验证脚本输出",
            cmd=cmd,
            status_running="正在运行验证脚本...",
            status_done="验证脚本执行完成",
        )

    def _open_timestamped_output_session(
        self,
        title_base: str,
        status_text: str = "",
        include_header_separator: bool = True,
    ) -> Tuple[tk.Toplevel, tk.StringVar, Any, str]:
        """统一创建带时间戳的输出窗口会话。"""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        title = f"{title_base} [{ts}]"
        log_win, status_var, append_log = self._open_text_output_window(title=title, status_text=status_text)
        append_log(f"[{ts}] {title_base}")
        if include_header_separator:
            append_log("=" * 70)
        return log_win, status_var, append_log, ts

    def _run_command_with_output_window(self, title_base: str, cmd: List[str], status_running: str, status_done: str):
        """运行命令并将输出实时显示到文本窗口"""
        log_win, status_var, append_log, _ = self._open_timestamped_output_session(
            title_base=title_base,
            status_text="启动中...",
            include_header_separator=False,
        )

        append_log(f"$ {' '.join(cmd)}")
        append_log(f"cwd: {BASE_DIR}")
        append_log("=" * 70)

        def worker():
            try:
                self.root.after(0, lambda: status_var.set(status_running))
                self.root.after(0, lambda: self.update_status(status_running))

                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONUTF8'] = '1'

                proc = subprocess.Popen(
                    cmd,
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    env=env,
                )

                if proc.stdout is not None:
                    for line in proc.stdout:
                        self.root.after(0, lambda l=line: append_log(l))

                return_code = proc.wait()
                self.root.after(0, lambda: append_log("=" * 70))
                self.root.after(0, lambda: append_log(f"进程结束，退出码: {return_code}"))
                self.root.after(0, lambda: status_var.set(f"已结束（退出码: {return_code}）"))
                self.root.after(0, lambda: self.update_status(status_done if return_code == 0 else f"{status_done}（退出码: {return_code}）"))
            except Exception as e:
                self.root.after(0, lambda: append_log(f"运行失败: {e}"))
                self.root.after(0, lambda: status_var.set("运行失败"))
                self.root.after(0, lambda: self.update_status("脚本运行失败"))

        threading.Thread(target=worker, daemon=True).start()

        try:
            log_win.lift()
            log_win.focus_force()
        except Exception:
            pass

    def _open_text_output_window(self, title: str, status_text: str = "") -> Tuple[tk.Toplevel, tk.StringVar, Any]:
        """创建统一文本输出窗口（仅展示日志，不提供清空/关闭按钮）"""
        log_win = tk.Toplevel(self.root)
        log_win.title(title)
        log_win.geometry("980x680")
        log_win.minsize(760, 480)

        main = ttk.Frame(log_win, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        status_var = tk.StringVar(value=status_text or "")
        ttk.Label(main, textvariable=status_var).pack(anchor='w', pady=(0, 8))

        text = scrolledtext.ScrolledText(main, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)
        text.configure(state='disabled')

        def append_log(line: str):
            if not (text and text.winfo_exists()):
                return
            text.configure(state='normal')
            text.insert(tk.END, line)
            if not line.endswith('\n'):
                text.insert(tk.END, '\n')
            text.see(tk.END)
            text.configure(state='disabled')

        return log_win, status_var, append_log




    def fill_from_zotero_meta(self):
        if not self._require_selected_paper("提示", "请先选择论文"):
            return
        s = self._show_zotero_input_dialog("填充表单")
        if not s: return
        new_p = self.logic.process_zotero_json(s)
        if not new_p: return messagebox.showwarning("提示", "无有效数据")

        real_idx = self._get_current_real_index()
        if real_idx < 0:
            return
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

    def _require_selected_paper(self, warning_title: Optional[str] = None, warning_message: str = "") -> bool:
        """检查是否已选择论文；可选弹出原有警告文案。"""
        if self.current_paper_index >= 0:
            return True
        if warning_title is not None:
            messagebox.showwarning(warning_title, warning_message)
        return False

    def ai_toolbox_window_impl(self):
        if not self._require_selected_paper("Warning", "请先选择一篇论文"):
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
        if not self._require_selected_paper("Warning", "请先选择一篇论文"):
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
        ridx = self._get_current_real_index()
        if ridx < 0:
            return
        paper = self.logic.papers[ridx]
        
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

    def _copy_category_tree_structure_to_clipboard(self, parent=None):
        try:
            result_text = self.logic.generate_category_tree_structure_text()
            owner = parent or self.root
            owner.clipboard_clear()
            owner.clipboard_append(result_text)
            owner.update()
            messagebox.showinfo("成功", "分类树结构已复制到剪贴板！", parent=owner)
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {str(e)}", parent=parent or self.root)

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
        
        roots, children, _ = self.logic.build_category_hierarchy()

        def insert_rec(parent_id, cat):
            node = tree.insert(parent_id, "end", text=cat['name'], values=(cat['unique_name'], cat.get('description','')))
            for child in children.get(cat['unique_name'], []):
                insert_rec(node, child)

        for root in roots:
            insert_rec("", root)

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

        # 创建按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 添加复制按钮
        copy_button = ttk.Button(button_frame, text="📋 复制结构到剪贴板", command=lambda: self._copy_category_tree_structure_to_clipboard(parent=win))
        copy_button.pack(side=tk.LEFT, padx=5)

        if target_combo:
            tree.bind("<Double-1>", on_double_click)
            hint_label = ttk.Label(button_frame, text="双击分类以填充", foreground="blue")
            hint_label.pack(side=tk.LEFT, padx=10)

    def _bind_widget_scroll_events(self, widget):
        widget.bind("<Enter>", lambda e: self._unbind_global_scroll())
        widget.bind("<Leave>", lambda e: self._bind_global_scroll(self.form_canvas.yview_scroll))

    def ai_suggest_category(self):
        self.run_ai_task(self._ai_suggest_category_task)

    def _ai_suggest_category_task(self):
        real_idx = self._get_current_real_index()
        if real_idx < 0:
            return
        paper = self.logic.papers[real_idx]
        paper_text = ""
        if paper.paper_file:
             paper_text = AIGenerator().read_paper_file(os.path.join(BASE_DIR, paper.paper_file))
        gen = AIGenerator()
        cat, reasoning = gen.generate_category(paper, paper_text)

        valid_categories = self.config.get_active_categories()
        id_set = {str(c.get('unique_name', '')).strip() for c in valid_categories if str(c.get('unique_name', '')).strip()}
        name_to_id = {
            str(c.get('name', '')).strip().lower(): str(c.get('unique_name', '')).strip()
            for c in valid_categories
            if str(c.get('name', '')).strip() and str(c.get('unique_name', '')).strip()
        }

        def normalize_suggested_category(raw_value: str) -> str:
            if not raw_value:
                return ""
            text = str(raw_value).strip()
            text = text.replace('；', ';').replace('，', ',').replace('、', ',').replace('\n', ',')
            text = text.replace('ID:', '').replace('id:', '').replace('ID', '').replace('id', '')
            for sep in [';', ',', '|']:
                text = text.replace(sep, '|')
            parts = [p.strip().strip('"\'') for p in text.split('|') if p.strip()]
            normalized = []
            for part in parts:
                if part in id_set:
                    normalized.append(part)
                    continue
                mapped = name_to_id.get(part.lower())
                if mapped:
                    normalized.append(mapped)
            # 去重并保持顺序
            return "|".join(dict.fromkeys(normalized))

        normalized_cat = normalize_suggested_category(cat)
        
        def update_ui():
            self.update_status("AI 分类建议已就绪")
            msg = f"AI Suggested: {cat}\nNormalized: {normalized_cat or '(未匹配到有效分类)'}\n\nReasoning:\n{reasoning}"
            if messagebox.askyesno("AI Category", msg + "\n\nAccept suggestion?"):
                if normalized_cat:
                    target_paper = self.logic.papers[real_idx]
                    target_paper.category = normalized_cat
                    if self._get_current_real_index() == real_idx:
                        self.load_paper_to_form(target_paper)
                        self._refresh_list_item(self.current_paper_index, target_paper)
                    else:
                        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())
                else:
                    messagebox.showwarning("AI Category", "AI 建议未匹配到有效分类ID，未应用。")
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
            ttk.Label(tip, text=text, background="#ffffe0", relief="solid", borderwidth=1, padding=5).pack()
            self._place_tooltip_within_root(tip, x, y)
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

    def _place_tooltip_within_root(self, tip_window, preferred_x: int, preferred_y: int, margin: int = 8):
        try:
            self.root.update_idletasks()
            tip_window.update_idletasks()

            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_w = self.root.winfo_width()
            root_h = self.root.winfo_height()

            if root_w <= 1 or root_h <= 1:
                tip_window.wm_geometry(f"+{preferred_x}+{preferred_y}")
                return

            tip_w = tip_window.winfo_reqwidth()
            tip_h = tip_window.winfo_reqheight()

            min_x = root_x + margin
            min_y = root_y + margin
            max_x = root_x + root_w - tip_w - margin
            max_y = root_y + root_h - tip_h - margin

            if max_x < min_x:
                max_x = min_x
            if max_y < min_y:
                max_y = min_y

            x = max(min_x, min(preferred_x, max_x))
            y = max(min_y, min(preferred_y, max_y))
            tip_window.wm_geometry(f"+{x}+{y}")
        except Exception:
            try:
                tip_window.wm_geometry(f"+{preferred_x}+{preferred_y}")
            except Exception:
                pass

    def create_tooltip(self, widget, text):
        def enter(event):
            try:
                if getattr(self, 'tooltip', None):
                    self.tooltip.destroy()
                    self.tooltip = None
            except Exception:
                self.tooltip = None

            x, y = widget.winfo_rootx() + 20, widget.winfo_rooty() + 20
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            ttk.Label(self.tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1, padding=5).pack()
            self._place_tooltip_within_root(self.tooltip, x, y)
        def leave(event):
            if getattr(self, 'tooltip', None):
                self.tooltip.destroy()
                self.tooltip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def setup_status_bar(self, parent):
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        self.current_file_var = tk.StringVar()
        self.current_file_var.set("(未加载)")
        self.status_bar_var = tk.StringVar()

        status_label = tk.Label(
            parent,
            textvariable=self.status_bar_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padx=6,
        )
        status_label.grid(row=4, column=0, columnspan=2, sticky="we", pady=(5, 0))
        self._refresh_status_bar_text()

    def _refresh_status_bar_text(self):
        if not hasattr(self, 'status_bar_var'):
            return
        status_msg = (self.status_var.get() or '').strip() if hasattr(self, 'status_var') else ''
        current_file = (self.current_file_var.get() or '').strip() if hasattr(self, 'current_file_var') else ''
        if not status_msg:
            status_msg = "就绪"
        if not current_file:
            current_file = "(未加载)"
        self.status_bar_var.set(f"{status_msg}  |  当前加载文件: {current_file}")

    def update_status(self, message):
        self.status_var.set(message)
        self._refresh_status_bar_text()
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
        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())

    def refresh_list_view(self, keyword="", category="", status=""):
        """根据搜索条件刷新列表 (修复列数据对应)"""
        if category == "":
            category = self._get_category_filter_value()
        if status == "":
            status = self._get_status_filter_value()

        # 1. 获取筛选后的索引
        filtered_indices, self._search_hit_fields_by_real_idx = self._filter_papers_with_match_fields(keyword, category, status)
        self.filtered_indices = self._sort_filtered_indices_for_display(filtered_indices)
        
        # 2. 清空列表
        for item in self.paper_tree.get_children():
            self.paper_tree.delete(item)
            
        # 3. 填充列表
        visible_columns = self._get_visible_list_columns()
        for real_idx in self.filtered_indices:
            paper = self.logic.papers[real_idx]
            status_str, tags = self._get_list_status_and_tags(paper)

            values = tuple(
                status_str if col == 'Status' else self._get_list_column_display_value(paper, real_idx, col)
                for col in visible_columns
            )
            self.paper_tree.insert("", "end", iid=str(real_idx), values=values, tags=tags)

        self._rebuild_category_filter_tree(select_current=True)
        
        # 恢复选中状态
        if self.current_paper_index >= 0 and self.current_paper_index < len(self.filtered_indices):
            real_idx = self.filtered_indices[self.current_paper_index]
            if not self._select_tree_item_by_real_index(real_idx, focus_item=False, see_item=False):
                self.current_paper_index = -1
                self.show_placeholder()
            else:
                self._apply_search_hit_highlight(real_idx)
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
        self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())
        self._highlight_paper(new_idx)
        self.update_status("条目已拷贝")

    def _highlight_paper(self, real_idx):
        """在列表中高亮显示指定真实索引的论文"""
        # 检查该 real_idx 是否在当前筛选视图中
        if not self._activate_paper_by_real_index(real_idx):
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
        ttk.Label(header_frame, text="基论文", foreground="blue", font=h_font).grid(row=0, column=2, sticky="w")
        ttk.Label(header_frame, text="", width=2).grid(row=0, column=3) 
        ttk.Label(header_frame, text="  ", width=4).grid(row=0, column=4) # Checkbox Col
        ttk.Label(header_frame, text="冲突/新论文", foreground="red", font=h_font).grid(row=0, column=5, sticky="w")

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
                wb = scrolledtext.ScrolledText(scroll_frame, height=4, width=30, font=("Arial", 9), background=bg_color)
                wb.insert(1.0, str(val_base))
            else:
                wb = tk.Entry(scroll_frame, font=("Arial", 9), relief="flat", bg=bg_color)
                wb.insert(0, str(val_base))
            wb.grid(row=row, column=2, sticky="nsew", pady=1, padx=2)
            self.conflict_ui_data[field]['w_base'] = wb
            
            # Separator
            line = tk.Frame(scroll_frame, width=2, bg=bg_color)
            line.grid(row=row, column=3, sticky="ns", pady=1)
            
            # Conflict Side (复选框在前)
            rb2 = tk.Radiobutton(scroll_frame, variable=choice_var, value=1, bg=bg_color)
            rb2.grid(row=row, column=4, sticky="nsew", pady=1)
            
            if ftype == 'text':
                wc = scrolledtext.ScrolledText(scroll_frame, height=4, width=30, font=("Arial", 9), background=bg_color)
                wc.insert(1.0, str(val_conflict))
            else:
                wc = tk.Entry(scroll_frame, font=("Arial", 9), relief="flat", bg=bg_color)
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
                self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())
                
                new_base_idx = base_idx if base_idx < conflict_idx else base_idx - 1
                self._highlight_paper(new_base_idx)
                self.update_status("冲突处理完成")

        ttk.Button(btm_frame, text="✅ 确认合并", command=on_confirm, width=20).pack(side=tk.RIGHT)


    # ================= 拖拽排序功能 (修改：增加跟随窗口) =================

    def _on_drag_start(self, event):
        if self._is_any_filter_active():
            return
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
        if self._drag_press_item and not self.drag_item and self._drag_press_xy:
            dx = abs(event.x - self._drag_press_xy[0])
            dy = abs(event.y - self._drag_press_xy[1])
            if max(dx, dy) >= self._drag_min_distance:
                self.drag_item = self._drag_press_item
                try:
                    item_text = self.paper_tree.item(self.drag_item, "values")[1]
                except Exception:
                    item_text = ""
                self._create_drag_ghost(item_text)

        if not self.drag_item:
            return

        self._update_drag_ghost(event)
        
        # 可选：绘制一条插入线 (TreeView 比较难实现插入线，这里保持简单，不乱动 Selection)
        # 移除原有的 selection_set 代码，避免鼠标划过时疯狂切换选中项

    def _handle_category_drop_for_dragged_paper(self) -> bool:
        """若当前拖拽释放在分类树节点上，则为论文追加分类并返回 True。"""
        if not self.drag_item:
            return False

        tree = getattr(self, 'category_filter_tree', None)
        if tree is None:
            return False

        if not bool(getattr(self, '_category_sidebar_visible', False)):
            return False

        try:
            pointer_x = self.root.winfo_pointerx()
            pointer_y = self.root.winfo_pointery()
        except Exception:
            return False

        tree_left = tree.winfo_rootx()
        tree_top = tree.winfo_rooty()
        tree_right = tree_left + tree.winfo_width()
        tree_bottom = tree_top + tree.winfo_height()
        if not (tree_left <= pointer_x <= tree_right and tree_top <= pointer_y <= tree_bottom):
            return False

        local_y = pointer_y - tree_top
        target_item = tree.identify_row(local_y)
        if not target_item or target_item == '__ALL__':
            return False

        try:
            real_index = int(self.drag_item)
        except Exception:
            return False

        changed, reason, count = self.logic.add_category_to_paper(real_index, target_item)

        if reason == 'limit':
            max_count = self.logic.get_max_categories_per_paper()
            messagebox.showwarning('限制', f'该论文分类数已达上限（{max_count}），无法继续添加。')
            return True

        if reason in ('invalid-index', 'invalid-category'):
            return True

        if changed:
            category_meta = self.logic.config.get_category_by_unique_name(target_item) or {}
            category_name = category_meta.get('name', target_item)
            self.refresh_list_view(self._get_search_keyword(), self._get_category_filter_value(), self._get_status_filter_value())
            self._activate_paper_by_real_index(real_index)
            self.update_status(f"已添加分类：{category_name}（当前 {count} 个）")
        else:
            category_meta = self.logic.config.get_category_by_unique_name(target_item) or {}
            category_name = category_meta.get('name', target_item)
            if reason == 'exists':
                self.update_status(f"该论文已包含分类：{category_name}")

        return True

    def _on_drag_release(self, event):
        self._destroy_drag_ghost()
        if not self.drag_item:
            self._drag_press_item = None
            self._drag_press_xy = None
            return

        # 优先处理“拖到 hierarchy 分类树节点上”这一操作
        if self._handle_category_drop_for_dragged_paper():
            self.drag_item = None
            self._drag_press_item = None
            self._drag_press_xy = None
            return

        # 检测释放位置是否在 Treeview 内
        tv_width = self.paper_tree.winfo_width()
        tv_height = self.paper_tree.winfo_height()
        
        if event.x < 0 or event.x > tv_width or event.y < 0 or event.y > tv_height:
            # 在框外释放，取消移动
            self.drag_item = None
            self._drag_press_item = None
            self._drag_press_xy = None
            return

        target_item = self.paper_tree.identify_row(event.y)

        target_mode = 'row'
        if not target_item:
            children = self.paper_tree.get_children()
            if children:
                last_item = children[-1]
                last_bbox = self.paper_tree.bbox(last_item)
                if last_bbox and event.y > (last_bbox[1] + last_bbox[3]):
                    target_mode = 'append-end'

        can_reorder = self._is_drag_reorder_allowed()

        if can_reorder and ((target_item and target_item != self.drag_item) or target_mode == 'append-end'):
            try:
                real_from = int(self.drag_item)
                if target_mode == 'append-end':
                    real_to_target = len(self.logic.papers) - 1
                else:
                    real_to_target = int(target_item)

                from_index = real_from
                to_index = real_to_target

                self.logic.move_paper(from_index, to_index)
                self.refresh_list_view()
                self._highlight_paper(to_index)
                
            except ValueError:
                pass 
            
        self.drag_item = None
        self._drag_press_item = None
        self._drag_press_xy = None


    def _on_text_undo(self, event):
        try: event.widget.edit_undo(); return "break"
        except: return "break"
    def _on_text_redo(self, event):
        try: event.widget.edit_redo(); return "break"
        except: return "break"


    def on_closing(self):
        self._confirm_all_pending_file_fields_for_current_paper(show_popup=True, block_on_error=False)
        if self.logic.papers:
            choice = messagebox.askyesnocancel("确认", "注意！是否保存当前所有论文？如果否，当前所有内容会丢失")
            if choice is None: return
            if choice and (not self.save_all_papers()):
                return
        self.logic.clear_all_temp_assets()
        self.root.destroy()

    def add_from_zotero_meta(self):
        s = self._show_zotero_input_dialog("从Zotero Meta新建论文")
        if not s: return
        new_p = self.logic.process_zotero_json(s)
        if not new_p: return messagebox.showwarning("提示", "未解析到有效的Zotero数据")
        self.logic.add_zotero_papers(new_p)
        self.update_paper_list()
        idx = len(self.logic.papers) - 1
        if idx in self.filtered_indices:
            self._suppress_select_event = True
            try:
                self._activate_paper_by_real_index(idx)
            finally:
                self._suppress_select_event = False
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