"""
提交系统的业务逻辑层
处理数据管理、文件读写、Git操作和Zotero集成
适配 CSV/JSON 和 Assets 架构
"""
import os
import sys
import threading
import subprocess
import time
import shutil
import uuid
import configparser
import json
from typing import Dict, List, Any, Optional, Tuple, Set
import re
import copy # 新增

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity
from src.core.database_manager import DatabaseManager
from src.core.update_file_utils import get_update_file_utils
from src.process_zotero_meta import ZoteroProcessor
from src.utils import clean_doi, ensure_directory, generate_paper_uid

# 锚定根目录
BASE_DIR = str(get_config_instance().project_root)

class SubmitLogic:
    """提交系统的业务逻辑控制器"""

    VALID_SAVE_VALIDATION_STRATEGIES = {'strict', 'lenient'}
    VALID_SAVE_MODES = {'incremental', 'rewrite'}
    DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME = 'default'
    DEFAULT_WORKSPACE_LAYOUT = {
        'main_pane_ratio': 0.47,
        'category_sidebar_visible': False,
        'category_sidebar_ratio': 0.40,
        'optional_columns': [],
        'column_widths': {},
        'category_tree_count_width': 35,
    }

    def __init__(self):
        # 加载配置
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.update_utils = get_update_file_utils()
        self.db_manager = DatabaseManager()
        self.zotero_processor = ZoteroProcessor()
        
        # 论文数据列表
        self.papers: List[Paper] = []
        self.current_file_path: Optional[str] = None # 当前编辑的文件路径
        
        # 默认使用 JSON 作为主要更新文件，如果未配置则使用 CSV
        self.primary_update_file = self.settings['paths'].get('update_json', 'submit_template.json')
        if not self.primary_update_file:
             self.primary_update_file = self.settings['paths'].get('update_csv', 'submit_template.csv')
        
        # 绝对路径
        if self.primary_update_file and not os.path.isabs(self.primary_update_file):
            self.primary_update_file = os.path.join(BASE_DIR, self.primary_update_file)

        self.conflict_marker = self.settings['database']['conflict_marker']
        self.PLACEHOLDER = "to be filled in"
        
        # 资源目录配置
        self.assets_dir = self.settings['paths'].get('assets_dir', 'assets/')

        # PR配置
        try:
            ui_cfg = self.settings.get('ui', {}) or {}
            enable_pr_val = ui_cfg.get('enable_pr', 'true')
            self.pr_enabled = str(enable_pr_val).strip().lower() in ('1', 'true', 'yes', 'on')
        except Exception:
            self.pr_enabled = True

        if '--no-pr' in sys.argv or os.environ.get('NO_PR', '').lower() in ('1', 'true'):
            self.pr_enabled = False

        # 管理员相关（当前没有实现自选位置吗）
        self.is_admin = False
        self.admin_password_path = self.settings['database'].get('administer_password_path', '')
        if not self.admin_password_path:
             # 默认位置
             self.admin_password_path = os.path.join(BASE_DIR, 'admin_key.txt')

        self.update_json_path = self.settings['paths'].get('update_json', 'submit_template.json')

    # ================= UI 配置逻辑 =================

    def _normalize_save_validation_strategy(self, strategy: Any) -> str:
        value = str(strategy or '').strip().lower()
        if value not in self.VALID_SAVE_VALIDATION_STRATEGIES:
            return 'strict'
        return value

    def _normalize_save_mode(self, mode: Any) -> str:
        value = str(mode or '').strip().lower()
        if value not in self.VALID_SAVE_MODES:
            return 'incremental'
        return value

    def get_save_validation_strategy(self) -> str:
        ui_cfg = self.settings.get('ui', {}) or {}
        return self._normalize_save_validation_strategy(ui_cfg.get('save_validation_strategy', 'strict'))

    def get_save_mode(self) -> str:
        ui_cfg = self.settings.get('ui', {}) or {}
        return self._normalize_save_mode(ui_cfg.get('save_mode', 'incremental'))

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

        # 刷新配置快照，确保后续读取立即生效
        self.config.settings = self.config._load_settings()
        self.settings = self.config.settings

    def set_save_validation_strategy(self, strategy: str, require_admin: bool = True) -> str:
        if require_admin and not self.is_admin:
            raise PermissionError("仅管理员可修改保存策略")
        normalized = self._normalize_save_validation_strategy(strategy)
        self._persist_ui_setting('save_validation_strategy', normalized)
        return normalized

    def set_save_mode(self, mode: str, require_admin: bool = False) -> str:
        if require_admin and not self.is_admin:
            raise PermissionError("仅管理员可修改保存模式")
        normalized = self._normalize_save_mode(mode)
        self._persist_ui_setting('save_mode', normalized)
        return normalized

    def _build_default_workspace_layout_profile(self) -> Dict[str, Any]:
        return {
            'name': self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME,
            'display_name': '默认配置',
            'locked': True,
            'layout': copy.deepcopy(self.DEFAULT_WORKSPACE_LAYOUT)
        }

    def get_default_workspace_layout_payload(self) -> Dict[str, Any]:
        return copy.deepcopy(self.DEFAULT_WORKSPACE_LAYOUT)

    def _normalize_workspace_ratio(self, value: Any, default: float, minimum: float = 0.10, maximum: float = 0.90) -> float:
        try:
            ratio = float(value)
        except Exception:
            ratio = float(default)
        return max(minimum, min(maximum, ratio))

    def _normalize_workspace_layout_payload(self, payload: Any) -> Dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        defaults = self.DEFAULT_WORKSPACE_LAYOUT

        optional_columns: List[str] = []
        raw_optional = data.get('optional_columns', [])
        if isinstance(raw_optional, list):
            for item in raw_optional:
                text = str(item or '').strip()
                if text and text not in optional_columns:
                    optional_columns.append(text)

        column_widths: Dict[str, int] = {}
        raw_widths = data.get('column_widths', {})
        if isinstance(raw_widths, dict):
            for key, val in raw_widths.items():
                column = str(key or '').strip()
                if not column:
                    continue
                try:
                    width = int(val)
                except Exception:
                    continue
                column_widths[column] = max(30, min(1000, width))

        try:
            category_tree_count_width = int(data.get('category_tree_count_width', defaults.get('category_tree_count_width', 35)))
        except Exception:
            category_tree_count_width = int(defaults.get('category_tree_count_width', 35))
        category_tree_count_width = max(24, min(240, category_tree_count_width))

        return {
            'main_pane_ratio': self._normalize_workspace_ratio(
                data.get('main_pane_ratio', defaults.get('main_pane_ratio', 0.40)),
                float(defaults.get('main_pane_ratio', 0.40)),
            ),
            'category_sidebar_visible': bool(data.get('category_sidebar_visible', defaults.get('category_sidebar_visible', False))),
            'category_sidebar_ratio': self._normalize_workspace_ratio(
                data.get('category_sidebar_ratio', defaults.get('category_sidebar_ratio', 0.40)),
                float(defaults.get('category_sidebar_ratio', 0.40)),
            ),
            'optional_columns': optional_columns,
            'column_widths': column_widths,
            'category_tree_count_width': category_tree_count_width,
        }

    def _normalize_workspace_layout_profile(self, profile: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(profile, dict):
            return None

        name = str(profile.get('name', '')).strip()
        if not name:
            return None

        display_name = str(profile.get('display_name', name)).strip() or name
        locked = bool(profile.get('locked', False))
        layout_payload = self._normalize_workspace_layout_payload(profile.get('layout', {}))

        return {
            'name': name,
            'display_name': display_name,
            'locked': locked,
            'layout': layout_payload,
        }

    def _load_workspace_layout_profiles_state(self) -> Tuple[List[Dict[str, Any]], str]:
        ui_cfg = self.settings.get('ui', {}) or {}
        raw_profiles = ui_cfg.get('workspace_layout_profiles_json', '[]')

        parsed_profiles: List[Dict[str, Any]] = []
        try:
            profile_items = json.loads(raw_profiles) if raw_profiles else []
        except Exception:
            profile_items = []

        if isinstance(profile_items, list):
            for item in profile_items:
                normalized = self._normalize_workspace_layout_profile(item)
                if normalized is None:
                    continue
                if normalized.get('name') == self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME:
                    continue
                parsed_profiles.append(normalized)

        profiles = [self._build_default_workspace_layout_profile()] + parsed_profiles

        active_name = str(ui_cfg.get('active_workspace_layout_profile', self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME)).strip()
        available_names = {p.get('name', '') for p in profiles}
        if active_name not in available_names:
            active_name = self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME

        return profiles, active_name

    def _persist_workspace_layout_profiles_state(self, profiles: List[Dict[str, Any]], active_name: str):
        serializable_profiles: List[Dict[str, Any]] = []
        for profile in profiles:
            if profile.get('name') == self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME:
                continue
            serializable_profiles.append({
                'name': profile.get('name', ''),
                'display_name': profile.get('display_name', profile.get('name', '')),
                'locked': bool(profile.get('locked', False)),
                'layout': self._normalize_workspace_layout_payload(profile.get('layout', {})),
            })

        self._persist_ui_setting('workspace_layout_profiles_json', json.dumps(serializable_profiles, ensure_ascii=False))
        self._persist_ui_setting('active_workspace_layout_profile', str(active_name or self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME))

    def get_workspace_layout_profiles(self) -> Tuple[List[Dict[str, Any]], str]:
        profiles, active_name = self._load_workspace_layout_profiles_state()
        return copy.deepcopy(profiles), active_name

    def get_active_workspace_layout_profile(self) -> Dict[str, Any]:
        profiles, active_name = self._load_workspace_layout_profiles_state()
        for profile in profiles:
            if profile.get('name') == active_name:
                return copy.deepcopy(profile)
        return copy.deepcopy(self._build_default_workspace_layout_profile())

    def set_active_workspace_layout_profile(self, profile_name: str) -> Dict[str, Any]:
        target_name = str(profile_name or '').strip()
        profiles, _ = self._load_workspace_layout_profiles_state()

        target_profile: Optional[Dict[str, Any]] = None
        for profile in profiles:
            if profile.get('name') == target_name:
                target_profile = profile
                break

        if target_profile is None:
            raise ValueError(f"布局配置不存在: {target_name}")

        self._persist_workspace_layout_profiles_state(profiles, target_name)
        return copy.deepcopy(target_profile)

    def save_workspace_layout_profile(self, profile_name: str, layout_payload: Dict[str, Any], overwrite: bool = False) -> Dict[str, Any]:
        name = str(profile_name or '').strip()
        if not name:
            raise ValueError('配置名不能为空')
        if name == self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME:
            raise PermissionError('默认配置不可修改')

        normalized_payload = self._normalize_workspace_layout_payload(layout_payload)
        profiles, _ = self._load_workspace_layout_profiles_state()

        existing_idx = -1
        for idx, profile in enumerate(profiles):
            if profile.get('name') == name:
                existing_idx = idx
                break

        if existing_idx >= 0:
            if not overwrite:
                raise ValueError(f"配置已存在: {name}")
            if profiles[existing_idx].get('locked', False):
                raise PermissionError('该配置不可修改')
            profiles[existing_idx]['display_name'] = name
            profiles[existing_idx]['layout'] = normalized_payload
            saved_profile = profiles[existing_idx]
        else:
            saved_profile = {
                'name': name,
                'display_name': name,
                'locked': False,
                'layout': normalized_payload,
            }
            profiles.append(saved_profile)

        self._persist_workspace_layout_profiles_state(profiles, name)
        return copy.deepcopy(saved_profile)

    def delete_workspace_layout_profile(self, profile_name: str):
        name = str(profile_name or '').strip()
        if not name:
            raise ValueError('配置名不能为空')
        if name == self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME:
            raise PermissionError('默认配置不可删除')

        profiles, active_name = self._load_workspace_layout_profiles_state()
        kept_profiles = [p for p in profiles if p.get('name') != name]
        if len(kept_profiles) == len(profiles):
            raise ValueError(f"配置不存在: {name}")

        next_active = active_name
        if active_name == name:
            next_active = self.DEFAULT_WORKSPACE_LAYOUT_PROFILE_NAME

        self._persist_workspace_layout_profiles_state(kept_profiles, next_active)
    # ================= 文件加载与管理 =================

    def load_papers_from_file(self, filepath: str) -> int:
        """加载指定文件"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        
        # 权限检查：如果是数据库文件且未登录
        if self._is_database_file(filepath) and not self.is_admin:
            raise PermissionError("需要管理员权限才能打开数据库文件")

        return self._load_papers_into_workspace(filepath, set_current_file=True)


    def load_existing_updates(self) -> int:
        """加载默认更新文件中的论文"""
        if self.primary_update_file and os.path.exists(self.primary_update_file):
            try:
                return self._load_papers_into_workspace(self.primary_update_file, set_current_file=False)
            except Exception as e:
                raise Exception(f"加载更新文件失败: {e}")
        return 0

    def _is_database_file(self, filepath: str) -> bool:
        """检查路径是否为核心数据库"""
        db_path = self.settings['paths']['database']
        if not os.path.isabs(db_path):
            db_path = os.path.join(BASE_DIR, db_path)
        
        # 简单路径比对
        try:
            return os.path.samefile(filepath, db_path)
        except:
            return os.path.abspath(filepath) == os.path.abspath(db_path)

    def _read_existing_papers(self, filepath: str) -> List[Paper]:
        """读取已有文件中的论文；失败时返回空列表并输出日志。"""
        if not filepath or not os.path.exists(filepath):
            return []
        success, papers = self.update_utils.read_data(filepath)
        if not success:
            print(f"加载文件失败: {filepath}")
            return []
        return papers

    def _load_papers_into_workspace(self, filepath: str, set_current_file: bool = True) -> int:
        """统一加载逻辑：读取文件并写入当前工作集。"""
        self.papers = self._read_existing_papers(filepath)
        try:
            self.update_utils.repair_related_paper_references(self.papers)
        except Exception as ex:
            print(f"相关论文引用修正失败（工作区）: {ex}")
        if set_current_file:
            self.current_file_path = filepath
        return len(self.papers)

    def _prepare_paper_for_save(
        self,
        paper: Paper,
        *,
        normalize_assets: bool = False,
        ensure_uid: bool = False,
    ) -> Paper:
        """统一保存前预处理：资源规范化、关键字段清洗、UID 补全。"""
        if normalize_assets:
            paper = self.update_utils.normalize_assets(paper)

        paper.doi = clean_doi(paper.doi, self.conflict_marker) if paper.doi else ""
        paper.category = self.update_utils.normalize_category_value(paper.category, self.config)

        if ensure_uid:
            self.ensure_paper_uid(paper)

        return paper

    # ================= 筛选与搜索 =================

    def _paper_category_set(self, paper: Paper) -> Set[str]:
        raw_cat = getattr(paper, 'category', '') or ''
        return {c.strip() for c in str(raw_cat).split('|') if c.strip()}

    def _paper_category_list(self, paper: Paper) -> List[str]:
        """返回保持原有顺序且去重后的分类列表。"""
        raw_cat = getattr(paper, 'category', '') or ''
        result: List[str] = []
        seen: Set[str] = set()
        for item in str(raw_cat).split('|'):
            category = item.strip()
            if not category or category in seen:
                continue
            seen.add(category)
            result.append(category)
        return result

    def get_max_categories_per_paper(self) -> int:
        """获取单篇论文允许的最大分类数。"""
        try:
            cfg_max = int((self.settings.get('database', {}) or {}).get('max_categories_per_paper', 4))
        except Exception:
            cfg_max = 4
        return max(1, min(cfg_max, 10))

    def add_category_to_paper(
        self,
        paper_index: int,
        category_unique_name: str,
        max_categories: Optional[int] = None,
    ) -> Tuple[bool, str, int]:
        """
        给论文追加分类（若不存在）。

        返回: (changed, reason, current_count)
        reason: added | exists | limit | invalid-index | invalid-category
        """
        if not (0 <= paper_index < len(self.papers)):
            return False, 'invalid-index', 0

        target_category = (category_unique_name or '').strip()
        if not target_category:
            return False, 'invalid-category', 0

        _, _, by_unique = self.build_category_hierarchy()
        if target_category not in by_unique:
            return False, 'invalid-category', 0

        paper = self.papers[paper_index]
        categories = self._paper_category_list(paper)

        if target_category in categories:
            return False, 'exists', len(categories)

        category_limit = self.get_max_categories_per_paper() if max_categories is None else max(1, int(max_categories))
        if len(categories) >= category_limit:
            return False, 'limit', len(categories)

        categories.append(target_category)
        paper.category = '|'.join(categories)
        paper.category = self.update_utils.normalize_category_value(paper.category, self.config)
        return True, 'added', len(categories)

    def build_category_hierarchy(self) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]:
        """构建分类树结构并返回 (roots, children_map, by_unique_name)。"""
        categories = self.config.get_active_categories() or []
        by_unique: Dict[str, Dict[str, Any]] = {}
        children_map: Dict[str, List[Dict[str, Any]]] = {}
        roots: List[Dict[str, Any]] = []

        for cat in categories:
            unique_name = str(cat.get('unique_name', '')).strip()
            if not unique_name:
                continue
            by_unique[unique_name] = cat

        for cat in by_unique.values():
            parent = str(cat.get('predecessor_category', '') or '').strip()
            if parent and parent in by_unique:
                children_map.setdefault(parent, []).append(cat)
            else:
                roots.append(cat)

        roots.sort(key=lambda x: x.get('order', 0))
        for key in children_map:
            children_map[key].sort(key=lambda x: x.get('order', 0))

        return roots, children_map, by_unique

    def get_category_scope_with_descendants(self, selected_category: str) -> Set[str]:
        """返回选中分类及其所有子孙分类的 unique_name 集合。"""
        selected = (selected_category or '').strip()
        if not selected:
            return set()

        _, children_map, by_unique = self.build_category_hierarchy()
        if selected not in by_unique:
            return set()

        scope: Set[str] = set()
        stack = [selected]
        while stack:
            current = stack.pop()
            if current in scope:
                continue
            scope.add(current)
            for child in children_map.get(current, []):
                child_unique = str(child.get('unique_name', '')).strip()
                if child_unique:
                    stack.append(child_unique)
        return scope

    def get_category_counts_with_descendants(self, papers: Optional[List[Paper]] = None) -> Dict[str, int]:
        """统计每个分类（含其所有子孙分类）的论文数量。"""
        _, _, by_unique = self.build_category_hierarchy()
        if not by_unique:
            return {}

        source_papers = papers if papers is not None else self.papers
        counts: Dict[str, int] = {k: 0 for k in by_unique.keys()}
        scope_cache: Dict[str, Set[str]] = {}

        for unique_name in by_unique.keys():
            scope_cache[unique_name] = self.get_category_scope_with_descendants(unique_name)

        for paper in source_papers:
            p_cats = self._paper_category_set(paper)
            if not p_cats:
                continue
            for unique_name, scope in scope_cache.items():
                if not p_cats.isdisjoint(scope):
                    counts[unique_name] += 1

        return counts

    def generate_category_tree_structure_text(self) -> str:
        """生成分类树结构文本（用于复制到剪贴板）。"""
        roots, children_map, _ = self.build_category_hierarchy()
        lines: List[str] = []

        def dump_node(cat: Dict[str, Any], prefix: str = ''):
            name = cat.get('name', '')
            unique_name = cat.get('unique_name', '')
            desc = cat.get('description', '')

            lines.append(f"{prefix}{name}")
            lines.append(f"{prefix}Unique Name: {unique_name}")
            if desc:
                lines.append(f"{prefix}Description: {desc}")
            lines.append('')

            for child in children_map.get(unique_name, []):
                dump_node(child, prefix + '    ')

        for root in roots:
            dump_node(root)

        return '\n'.join(lines).rstrip()

    def filter_papers_with_match_fields(
        self,
        keyword: str = '',
        selected_category: str = '',
        status: str = '',
        search_fields: Optional[List[str]] = None,
    ) -> Tuple[List[int], Dict[int, Set[str]]]:
        """关键词 + 分类(含子类) + 阅读状态联合筛选，并返回命中字段。"""
        kw = (keyword or '').lower().strip()
        status_filter = (status or '').strip()
        fields = list(search_fields or ['title', 'authors', 'doi', 'notes'])

        category_scope = self.get_category_scope_with_descendants(selected_category)

        indices: List[int] = []
        hit_fields: Dict[int, Set[str]] = {}

        for i, paper in enumerate(self.papers):
            if category_scope:
                p_cats = self._paper_category_set(paper)
                if p_cats.isdisjoint(category_scope):
                    continue

            if status_filter and status_filter != 'All Status':
                paper_status = (getattr(paper, 'status', '') or '').strip()
                if paper_status != status_filter:
                    continue

            matched: Set[str] = set()
            if kw:
                for variable in fields:
                    value = getattr(paper, variable, '')
                    text = '' if value is None else str(value)
                    if text and kw in text.lower():
                        matched.add(variable)
                if not matched:
                    continue

            indices.append(i)
            hit_fields[i] = matched

        return indices, hit_fields

    def filter_papers(self, keyword: str = "", category: str = "") -> List[int]:
        """
        根据条件筛选论文
        返回符合条件的论文在 self.papers 中的索引列表
        """
        indices = []
        kw = keyword.lower().strip()
        cat = category.strip()
        
        for i, p in enumerate(self.papers):
            # Category 过滤 (修复空值报错)
            if cat and cat != "All Categories":
                raw_cat = p.category if p.category else ""
                # 支持多分类匹配
                p_cats = [c.strip() for c in str(raw_cat).split('|') if c.strip()]
                if cat not in p_cats:
                    continue
            
            # Keyword 过滤
            if kw:
                # 搜索范围: title, authors, doi, notes
                # 修复 None 导致的报错
                title = p.title if p.title else ""
                authors = p.authors if p.authors else ""
                doi = p.doi if p.doi else ""
                notes = p.notes if p.notes else ""
                
                content = f"{title} {authors} {doi} {notes}".lower()
                if kw not in content:
                    continue
            
            indices.append(i)
        return indices
    
    # ================= 列表操作 (新增功能) =================

    def move_paper(self, from_index: int, to_index: int):
        """移动论文位置"""
        if from_index == to_index: return
        if not (0 <= from_index < len(self.papers) and 0 <= to_index < len(self.papers)): return
        
        item = self.papers.pop(from_index)
        self.papers.insert(to_index, item)

    def duplicate_paper(self, index: int) -> int:
        """拷贝论文，返回新索引"""
        if 0 <= index < len(self.papers):
            new_paper = copy.deepcopy(self.papers[index])
            # # 重置系统字段
            # new_paper.uid = "" 
            # new_paper.conflict_marker = False
            # new_paper.title = f"{new_paper.title} (Copy)"
            self.papers.insert(index + 1, new_paper)
            return index + 1
        return -1

    def find_base_paper_index(self, conflict_index: int) -> int:
        """查找冲突论文对应的基论文索引"""
        if not (0 <= conflict_index < len(self.papers)): return -1
        
        conflict_paper = self.papers[conflict_index]
        # 简单逻辑：向前查找同一个Identity且非冲突的论文
        # 或者遍历所有论文查找
        for i, p in enumerate(self.papers):
            if i == conflict_index: continue
            if is_same_identity(p, conflict_paper) and not p.conflict_marker:
                return i
        return -1

    def merge_papers_custom(self, base_index: int, conflict_index: int, final_data: Dict[str, Any]):
        """
        合并冲突：使用前端传入的具体数据(final_data)更新基论文，并删除冲突论文
        """
        base = self.papers[base_index]
        
        for field, value in final_data.items():
            if hasattr(base, field):
                setattr(base, field, value)
        
        # 标记处理完毕（防止逻辑混乱，其实可以直接删除）
        base.conflict_marker = False
        
        # 删除冲突论文
        self.delete_paper(conflict_index)

    # ================= 保存逻辑 (新) =================

    def save_to_file_rewrite(self, target_path: str):
        """重写模式：完全用当前列表覆盖目标文件"""
        # 如果是数据库，走数据库专用逻辑
        if self._is_database_file(target_path):
            if not self.is_admin: raise PermissionError("无权限写入数据库")
            success = self.db_manager.save_database(self.papers)
            if not success:
                raise IOError(self.update_utils.last_error or f"写入数据库失败: {target_path}")
        else:
            # 普通文件，先处理 Assets 归档
            for p in self.papers:
                self.update_utils.normalize_assets(p)
            success = self.update_utils.write_data(target_path, self.papers)
            if not success:
                raise IOError(self.update_utils.last_error or f"写入失败: {target_path}")

    def save_to_file_incremental(self, target_path: str, conflict_decisions: Dict[Tuple[str, str], str]):
        """
        增量模式：读取目标文件，根据 decisions 决定如何合并当前的新增项
        conflict_decisions: { (doi, title): 'overwrite' | 'skip' }
        """
        success, existing_papers = self.update_utils.read_data(target_path)
        if not success: existing_papers = []
        
        existing_map = {p.get_key(): i for i, p in enumerate(existing_papers)}
        
        # 待追加的论文
        papers_to_append = []
        
        for p in self.papers:
            p = self._prepare_paper_for_save(
                p,
                normalize_assets=True,
                ensure_uid=False,
            )
            
            key = p.get_key()
            
            if key in existing_map:
                decision = conflict_decisions.get(key, 'skip') # 默认跳过
                if decision == 'overwrite':
                    idx = existing_map[key]
                    existing_papers[idx] = p # 替换
            else:
                papers_to_append.append(p)
        
        # 合并
        final_list = existing_papers + papers_to_append
        success = self.update_utils.write_data(target_path, final_list)
        if not success:
            raise IOError(self.update_utils.last_error or f"写入失败: {target_path}")
        return final_list

    def save_to_file_by_mode(
        self,
        target_path: str,
        save_mode: Optional[str] = None,
        conflict_decisions: Optional[Dict[Tuple[str, str], str]] = None,
    ) -> List[Paper]:
        """按保存模式执行保存：数据库文件强制 rewrite，其余按配置/参数选择。"""
        if self._is_database_file(target_path):
            self.save_to_file_rewrite(target_path)
            return self.papers

        mode = self._normalize_save_mode(save_mode if save_mode is not None else self.get_save_mode())
        if mode == 'rewrite':
            self.save_to_file_rewrite(target_path)
            return self.papers

        return self.save_to_file_incremental(target_path, conflict_decisions or {})

    def get_conflicts_for_save(self, target_path: str) -> List[Paper]:
        """预检查：返回当前列表中与目标文件冲突的论文"""
        if not os.path.exists(target_path): return []
        
        success, existing = self.update_utils.read_data(target_path)
        if not success: return []
        
        existing_keys = {p.get_key() for p in existing}
        conflicts = []
        
        for p in self.papers:
            if p.get_key() in existing_keys:
                conflicts.append(p)
        return conflicts

    def create_new_paper(self) -> Paper:
        """创建一个新的占位符论文并添加到列表"""
        # 创建时就分配一个临时 UID，方便关联资源
        # 占位符不使用基于 title/doi 的稳定 uid，保持随机短 UUID
        new_uid = str(uuid.uuid4())[:8]
        placeholder = Paper(title=self.PLACEHOLDER, uid=new_uid)
        self.papers.append(placeholder)
        return placeholder

    def ensure_paper_uid(self, paper: Paper) -> str:
        """确保论文存在 uid，供资源暂存与规范化流程复用"""
        if not getattr(paper, 'uid', ''):
            paper.uid = generate_paper_uid(getattr(paper, 'title', ''), getattr(paper, 'doi', ''))
            if not paper.uid:
                paper.uid = str(uuid.uuid4())[:8]
        return paper.uid

    def delete_paper(self, index: int) -> bool:
        """删除指定索引的论文"""
        if 0 <= index < len(self.papers):
            del self.papers[index]
            return True
        return False

    def clear_papers(self):
        """清空所有论文"""
        self.papers = []

    def validate_papers_for_save(self) -> List[Tuple[int, str, List[str]]]:
        """验证所有论文，返回无效论文列表 (index, title, errors)"""
        invalid_papers = []
        for i, paper in enumerate(self.papers):
             valid, errors, _ = paper.validate_paper_fields(
                self.config,
                check_required=True,
                check_non_empty=True,
                no_normalize=False
            )
             if not valid:
                 invalid_papers.append((i+1, paper.title[:30], errors[:2]))
        return invalid_papers

    def check_save_conflicts(self, target_path: str) -> Tuple[List[Paper], bool]:
        """检查保存时的冲突，返回(合并后的列表, 是否有冲突)"""
        existing_papers = self._read_existing_papers(target_path)
        
        merged_papers = list(existing_papers)
        existing_keys = {p.get_key() for p in existing_papers}

        has_conflict = False
        
        for paper in self.papers:
            self._prepare_paper_for_save(paper, normalize_assets=False, ensure_uid=True)
            if paper.get_key() in existing_keys:
                has_conflict = True
                
        return merged_papers, has_conflict

    def perform_save(self, target_path: str, conflict_mode: str = 'overwrite_duplicates') -> List[Paper]:
        """
        执行保存操作 (包含 Assets 规范化)
        数据库操作使用覆盖模式
        """

        # 如果目标是数据库文件，需要使用 db_manager.save_database
        if self._is_database_file(target_path):
            if not self.is_admin: raise PermissionError("无权限写入数据库")
            # 数据库保存直接覆盖 (Full Save)
            self.db_manager.save_database(self.papers)
            return self.papers


        existing_papers = self._read_existing_papers(target_path)
        
        merged_papers = list(existing_papers)
        # 建立映射: Key -> List index
        existing_map = {}
        for idx, p in enumerate(existing_papers):
            key = p.get_key()
            existing_map[key] = idx

        overwrite_modes = {'overwrite_duplicates', 'overwrite_all'}
        skip_modes = {'skip_duplicates', 'skip_all'}

        for paper in self.papers:
            paper = self._prepare_paper_for_save(
                paper,
                normalize_assets=True,
                ensure_uid=False,
            )
            
            key = paper.get_key()
            
            if key in existing_map:
                if conflict_mode in overwrite_modes:
                    idx = existing_map[key]
                    merged_papers[idx] = paper
                elif conflict_mode in skip_modes:
                    continue
                # 如果是逐个询问模式，上层逻辑应该已经处理好了 papers 列表的去留，
                # 这里默认按照 overwrite 处理剩余的
            else:
                merged_papers.append(paper)
                # 更新 map 以防止 self.papers 内部也有重复
                existing_map[key] = len(merged_papers) - 1

        # 写入文件
        self.update_utils.write_data(target_path, merged_papers)
        return merged_papers

    def load_from_template(self, filepath: str) -> int:
        """从文件加载论文"""
        return self._load_papers_into_workspace(filepath, set_current_file=False)
    
    # ================= 管理员权限 =================

    def check_admin_password_configured(self) -> bool:
        return os.path.exists(self.admin_password_path)

    def verify_admin_password(self, password: str) -> bool:
        if not self.check_admin_password_configured(): return False
        try:
            with open(self.admin_password_path, 'r', encoding='utf-8') as f:
                stored = f.read().strip()
            return stored == password
        except: return False

    def set_admin_password(self, password: str):
        ensure_directory(os.path.dirname(self.admin_password_path))
        with open(self.admin_password_path, 'w', encoding='utf-8') as f:
            f.write(password)

    def set_admin_mode(self, enabled: bool):
        self.is_admin = enabled

    # ================= Zotero 逻辑 =================

    def process_zotero_json(self, json_str: str) -> List[Paper]:
        """处理Zotero JSON字符串"""
        return self.zotero_processor.process_meta_data(json_str)

    def add_zotero_papers(self, papers: List[Paper]) -> int:
        """批量添加Zotero论文"""
        # 为新论文分配 UID
        for p in papers:
            self.ensure_paper_uid(p)
        self.papers.extend(papers)
        return len(papers)

    def get_zotero_fill_updates(self, source_paper: Paper, target_index: int) -> Tuple[List[str], List[Tuple[str, Any]]]:
        """计算Zotero填充的更新内容"""
        if not (0 <= target_index < len(self.papers)):
            return [], []
            
        target_paper = self.papers[target_index]
        conflicts = []
        fields_to_update = []
        
        system_fields = [
            t.get("variable")
            for t in self.config.get_system_tags()
            if t.get("variable")
        ]
        
        for field in source_paper.__dataclass_fields__:
            if field in ['invalid_fields', 'is_placeholder', 'uid'] or field in system_fields:
                continue
            
            val = getattr(source_paper, field)
            if val:
                target_val = getattr(target_paper, field)
                fields_to_update.append((field, val))
                # 冲突检测
                if target_val and str(target_val).strip() and str(target_val).strip() != self.PLACEHOLDER:
                    conflicts.append(field)
                    
        return conflicts, fields_to_update

    def apply_paper_updates(self, index: int, updates: List[Tuple[str, Any]], overwrite: bool):
        """应用更新到指定论文"""
        if not (0 <= index < len(self.papers)):
            return 0
            
        target_paper = self.papers[index]
        updated_count = 0
        
        for field, val in updates:
            target_val = getattr(target_paper, field)
            if overwrite or (not target_val or not str(target_val).strip()):
                setattr(target_paper, field, val)
                updated_count += 1
        return updated_count

    # ================= Assets Import (New) =================
    
    def import_file_asset(self, src_path: str, asset_type: str, paper_uid: str = "") -> Tuple[bool, str, str]:
        """
        GUI 临时导入文件资源：
        1. 将文件复制到 assets/temp/{uid}/
        2. 返回临时相对路径供 GUI 显示
        3. 真正规范化在“确认(✓)”或保存时执行
        """
        if not src_path or not os.path.exists(src_path):
            return False, "", "源文件不存在"

        uid = (paper_uid or "").strip() or "unknown"
        temp_dir = os.path.join(BASE_DIR, self.assets_dir, 'temp', uid)
        ensure_directory(temp_dir)

        filename = os.path.basename(src_path)
        name, ext = os.path.splitext(filename)
        timestamp = int(time.time())
        if os.path.exists(os.path.join(temp_dir, filename)):
            filename = f"{name}_{timestamp}{ext}"

        dest_path = os.path.join(temp_dir, filename)
        try:
            shutil.copy2(src_path, dest_path)
            rel_path = os.path.relpath(dest_path, BASE_DIR).replace('\\', '/')
            return True, rel_path, ""
        except Exception as e:
            return False, "", f"复制失败: {e}"

    def validate_single_asset_reference(self, field_name: str, raw_path: str) -> Tuple[bool, str]:
        """使用统一验证函数校验单个引用路径（存在性 + 后缀）"""
        if field_name not in ('pipeline_image', 'paper_file'):
            return False, f"不支持的字段: {field_name}"
        paper = Paper()
        setattr(paper, field_name, (raw_path or '').strip())
        valid, errors = self.update_utils.validate_and_normalize_asset_fields(
            paper,
            [field_name],
            normalize=False,
            strict=True,
        )
        if valid:
            return True, ""
        return False, (errors[0] if errors else "资源验证失败")

    def confirm_file_field_for_paper(self, paper: Paper, field_name: str, raw_value: Optional[str] = None) -> Tuple[bool, str, str]:
        """对单个 file 字段执行规范化（复制到 assets/{uid}/ 并回填标准相对路径）"""
        if field_name not in ('pipeline_image', 'paper_file'):
            return False, "", f"不支持的字段: {field_name}"

        old_uid = getattr(paper, 'uid', '')
        old_pipeline = getattr(paper, 'pipeline_image', '')
        old_paper_file = getattr(paper, 'paper_file', '')

        raw_val = getattr(paper, field_name, "") if raw_value is None else raw_value
        if not raw_val:
            return True, "", ""

        try:
            setattr(paper, field_name, str(raw_val).strip())
            valid, errors = self.update_utils.validate_and_normalize_asset_fields(
                paper,
                [field_name],
                normalize=True,
                strict=True,
            )
            if not valid:
                return False, "", (errors[0] if errors else "资源验证失败")
            return True, getattr(paper, field_name, "") or "", ""
        except Exception as e:
            # 事务性回滚，保证失败时无修改
            paper.uid = old_uid
            paper.pipeline_image = old_pipeline
            paper.paper_file = old_paper_file
            return False, "", str(e)

    def clear_temp_assets_for_paper(self, paper_uid: str, field_name: Optional[str] = None):
        """清理 assets/temp/{uid} 下的临时资源（可按字段）"""
        if not paper_uid:
            return
        uid_dir = os.path.join(BASE_DIR, self.assets_dir, 'temp', paper_uid)
        if os.path.isdir(uid_dir):
            shutil.rmtree(uid_dir, ignore_errors=True)

    def clear_all_temp_assets(self):
        temp_root = os.path.join(BASE_DIR, self.assets_dir, 'temp')
        if os.path.isdir(temp_root):
            shutil.rmtree(temp_root, ignore_errors=True)

    def _iter_existing_update_files(self) -> List[str]:
        paths = self.settings['paths']
        out: List[str] = []

        def _resolve_abs(path_val: Optional[str]) -> Optional[str]:
            if not path_val:
                return None
            p = path_val if os.path.isabs(path_val) else os.path.join(BASE_DIR, path_val)
            return os.path.normpath(os.path.abspath(p))

        for k in ['update_json', 'update_csv', 'my_update_json', 'my_update_csv']:
            p = paths.get(k)
            p_abs = _resolve_abs(p)
            if p_abs and os.path.exists(p_abs):
                out.append(p_abs)
        for p in paths.get('extra_update_files_list', []):
            p_abs = _resolve_abs(p)
            if p_abs and os.path.exists(p_abs):
                out.append(p_abs)
        return list(dict.fromkeys(out))

    def get_nonempty_update_files(self) -> List[Dict[str, Any]]:
        """返回配置中存在且有内容的更新文件清单"""
        files: List[Dict[str, Any]] = []
        for fpath in self._iter_existing_update_files():
            success, papers = self.update_utils.read_data(fpath)
            if success and papers:
                files.append({'path': fpath, 'count': len(papers)})
        return files

    def _collect_asset_reference_papers(self, include_update_files: bool = False) -> List[Paper]:
        collected: List[Paper] = []

        db_path = self.settings['paths'].get('database')
        if db_path:
            db_abs = db_path if os.path.isabs(db_path) else os.path.join(BASE_DIR, db_path)
            db_abs = os.path.normpath(os.path.abspath(db_abs))
        else:
            db_abs = ""

        if db_abs and os.path.exists(db_abs):
            success, papers = self.update_utils.read_data(db_abs)
            if success:
                collected.extend(papers)

        if include_update_files:
            for fpath in self._iter_existing_update_files():
                success, papers = self.update_utils.read_data(fpath)
                if success:
                    collected.extend(papers)

        # 当前 GUI 工作区中正在编辑的论文也视作有效引用来源
        if self.papers:
            collected.extend(self.papers)

        return collected

    def cleanup_redundant_assets(self, include_update_files: bool = False, execute_delete: bool = False) -> Dict[str, Any]:
        """
        清除冗余资源并返回审计报告：
        - 未被任何论文条目引用的 uid 文件夹
        - 已存在 uid 文件夹中未被字段引用的文件
        - 论文字段引用缺失的文件
        """
        assets_root = os.path.join(BASE_DIR, self.assets_dir)
        assets_root_norm = os.path.normpath(os.path.abspath(assets_root))

        def _is_within_assets(path_val: str) -> bool:
            try:
                common = os.path.commonpath([assets_root_norm, os.path.normpath(os.path.abspath(path_val))])
                return common == assets_root_norm
            except Exception:
                return False

        report: Dict[str, Any] = {
            'mode': 'execute' if execute_delete else 'preview',
            'deleted_uid_dirs': [],
            'deleted_files': [],
            'would_delete_uid_dirs': [],
            'would_delete_files': [],
            'papers_with_unreferenced_assets': [],
            'missing_references': [],
            'invalid_suffix_references': [],
            'nonstandard_references': [],
        }
        if not os.path.isdir(assets_root):
            return report

        papers = self._collect_asset_reference_papers(include_update_files=include_update_files)

        uid_to_refs: Dict[str, set] = {}
        uid_to_referenced_assets_abs: Dict[str, set] = {}
        uid_to_title: Dict[str, str] = {}

        def _append_issue_entries(uid: str, title: str, analyses: List[Dict[str, Any]]):
            for item in analyses:
                issue_entry_base = {
                    'uid': uid,
                    'title': title,
                    'field': item.get('field', ''),
                    'reference': item.get('reference', ''),
                    'resolved': item.get('resolved'),
                }
                for issue in item.get('issues', []):
                    kind = issue.get('kind')
                    if kind == 'missing':
                        report['missing_references'].append(dict(issue_entry_base))
                    elif kind == 'invalid_suffix':
                        report['invalid_suffix_references'].append(dict(issue_entry_base))
                    elif kind == 'nonstandard_path':
                        report['nonstandard_references'].append(dict(issue_entry_base))

        for p in papers:
            uid = (getattr(p, 'uid', '') or '').strip()
            if not uid:
                continue
            title = getattr(p, 'title', '') or ''
            if uid not in uid_to_title:
                uid_to_title[uid] = title

            ref_set = uid_to_refs.setdefault(uid, set())
            resolved_assets = uid_to_referenced_assets_abs.setdefault(uid, set())

            analyses = self.update_utils.analyze_asset_fields(p, ['pipeline_image', 'paper_file'])
            for item in analyses:
                ref = str(item.get('reference') or '').replace('\\', '/')
                if ref:
                    ref_set.add(ref)

                resolved = item.get('resolved')
                if resolved and item.get('exists'):
                    resolved_norm = os.path.normpath(resolved)
                    if _is_within_assets(resolved_norm):
                        resolved_assets.add(resolved_norm)

            _append_issue_entries(uid, title, analyses)

        for entry in os.listdir(assets_root):
            if entry == 'temp':
                continue
            uid_dir = os.path.join(assets_root, entry)
            if not os.path.isdir(uid_dir):
                continue
            uid = entry
            ref_set = uid_to_refs.get(uid, set())
            if not ref_set:
                report['would_delete_uid_dirs'].append(uid)
                if execute_delete and _is_within_assets(uid_dir):
                    shutil.rmtree(uid_dir, ignore_errors=True)
                    report['deleted_uid_dirs'].append(uid)
                continue

            referenced_files_abs = uid_to_referenced_assets_abs.get(uid, set())

            unreferenced_here = []
            for root, _, files in os.walk(uid_dir):
                for fn in files:
                    abs_file = os.path.normpath(os.path.join(root, fn))
                    if abs_file not in referenced_files_abs:
                        rel_file = os.path.relpath(abs_file, BASE_DIR).replace('\\', '/')
                        unreferenced_here.append(rel_file)
                        report['would_delete_files'].append(rel_file)
                        if execute_delete and _is_within_assets(abs_file):
                            try:
                                os.remove(abs_file)
                                report['deleted_files'].append(rel_file)
                            except Exception:
                                pass

            if unreferenced_here:
                report['papers_with_unreferenced_assets'].append({
                    'uid': uid,
                    'title': uid_to_title.get(uid, ''),
                    'files': unreferenced_here,
                })

        # 去重，避免重复报告
        def _dedup_dict_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            seen = set()
            out = []
            for item in items:
                key = (
                    item.get('uid'), item.get('field'),
                    item.get('reference'), item.get('resolved')
                )
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
            return out

        report['missing_references'] = _dedup_dict_list(report['missing_references'])
        report['invalid_suffix_references'] = _dedup_dict_list(report['invalid_suffix_references'])
        report['nonstandard_references'] = _dedup_dict_list(report['nonstandard_references'])
        report['would_delete_uid_dirs'] = list(dict.fromkeys(report['would_delete_uid_dirs']))
        report['would_delete_files'] = list(dict.fromkeys(report['would_delete_files']))
        report['deleted_uid_dirs'] = list(dict.fromkeys(report['deleted_uid_dirs']))
        report['deleted_files'] = list(dict.fromkeys(report['deleted_files']))

        return report



    # ================= PR 提交逻辑 =================

    def execute_pr_submission(self, status_callback, result_callback, error_callback):
        """执行PR提交的线程函数"""
        def run():
            try:
                # 检查 Git
                try:
                    subprocess.run(["git", "--version"], check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    raise Exception("Git未安装！")
                
                # 获取待提交文件列表
                files_to_commit = []
                paths = self.settings['paths']
                # 收集配置中所有有效的更新文件
                check_keys = ['update_csv', 'update_json', 'my_update_csv', 'my_update_json']
                for k in check_keys:
                    p = paths.get(k)
                    if p and os.path.exists(os.path.join(BASE_DIR, p) if not os.path.isabs(p) else p):
                         files_to_commit.append(p)
                
                if not files_to_commit:
                    raise Exception("没有找到可提交的更新文件！")

                # 获取当前分支
                result = subprocess.run(["git", "branch", "--show-current"], 
                                       capture_output=True, text=True, cwd=BASE_DIR)
                current_branch = result.stdout.strip()
                original_branch = current_branch
                created_new_branch = False
                
                # 分支处理
                if current_branch == "main":
                    branch_name = f"paper-submission-{int(time.time())}"
                    try:
                        subprocess.run(["git", "checkout", "-b", branch_name], 
                                      check=True, capture_output=True, text=True, cwd=BASE_DIR)
                        created_new_branch = True
                        status_callback(f"已创建并切换到新分支: {branch_name}")
                    except subprocess.CalledProcessError as e:
                        raise Exception(f"创建分支失败: {e.stderr}")
                else:
                    branch_name = current_branch
                
                # 添加更新文件
                for f in files_to_commit:
                    subprocess.run(["git", "add", f], check=True, capture_output=True, cwd=BASE_DIR)
                
                # 重要：添加 assets 目录 (包含新添加的资源)
                # 使用 assets/ 递归添加
                if os.path.exists(os.path.join(BASE_DIR, self.assets_dir)):
                     subprocess.run(["git", "add", self.assets_dir], check=True, capture_output=True, cwd=BASE_DIR)

                # 提交
                subprocess.run(["git", "commit", "-m", f"Add {len(self.papers)} papers via GUI"], 
                               check=True, capture_output=True, cwd=BASE_DIR)
                status_callback("已提交更改到本地仓库")
                
                # 推送
                try:
                    subprocess.run(["git", "push", "origin", branch_name], 
                                 check=True, capture_output=True, text=True, cwd=BASE_DIR)
                    status_callback(f"已推送到远程分支: {branch_name}")
                except subprocess.CalledProcessError as e:
                    raise Exception(f"推送失败: {e.stderr}")
                
                # 创建 PR (尝试使用 gh cli)
                pr_url = None
                try:
                    pr_title = f"论文提交: {len(self.papers)} 篇新论文"
                    pr_body = f"通过GUI提交了 {len(self.papers)} 篇论文。"
                    
                    try:
                        subprocess.run(["gh", "--version"], check=True, capture_output=True)
                        use_gh = True
                    except: use_gh = False

                    if use_gh:
                        res = subprocess.run(
                            ["gh", "pr", "create", "--base", "main", "--head", branch_name,
                             "--title", pr_title, "--body", pr_body],
                            capture_output=True, text=True, cwd=BASE_DIR
                        )
                        if res.returncode == 0:
                            pr_url = res.stdout.strip()
                        else:
                            raise Exception(f"GitHub CLI创建PR失败: {res.stderr}")
                    else:
                        raise Exception("GitHub CLI not installed")

                except Exception as e:
                    # 推送成功但PR创建失败，引导手动创建
                    if "GitHub CLI" in str(e):
                        result_callback(None, branch_name, manual_guide=True)
                    else:
                        result_callback(None, branch_name, manual_guide=False)
                else:
                    result_callback(pr_url, branch_name, manual_guide=False)

                # 切回原分支
                if created_new_branch:
                    subprocess.run(["git", "checkout", original_branch], check=True, capture_output=True, text=True, cwd=BASE_DIR)

            except Exception as e:
                error_callback(str(e))
                
        threading.Thread(target=run, daemon=True).start()

    def save_ai_config(self, profiles: List[Dict], active_profile: str, enable_ai: bool):
        """保存AI配置 (代理到ConfigLoader)"""
        self.config.save_ai_settings(enable_ai, active_profile, profiles)