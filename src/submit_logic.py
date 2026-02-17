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
from typing import Dict, List, Any, Optional, Tuple
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
    # ================= 文件加载与管理 =================

    def load_papers_from_file(self, filepath: str) -> int:
        """加载指定文件"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        
        # 权限检查：如果是数据库文件且未登录
        if self._is_database_file(filepath) and not self.is_admin:
            raise PermissionError("需要管理员权限才能打开数据库文件")

        success,self.papers = self.update_utils.read_data(filepath)
        if not success:
            print(f"加载文件失败: {filepath}")
        self.current_file_path = filepath
        return len(self.papers)


    def load_existing_updates(self) -> int:
        """加载默认更新文件中的论文"""
        count = 0
        if self.primary_update_file and os.path.exists(self.primary_update_file):
            try:
                # 使用通用的 read_data 接口
                success,self.papers = self.update_utils.read_data(self.primary_update_file)
                if not success:                    
                    print(f"加载更新文件失败: {self.primary_update_file}")
                count = len(self.papers)
            except Exception as e:
                raise Exception(f"加载更新文件失败: {e}")
        return count

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

    # ================= 筛选与搜索 =================

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
            self.db_manager.save_database(self.papers)
        else:
            # 普通文件，先处理 Assets 归档
            for p in self.papers:
                self.update_utils.normalize_assets(p)
            self.update_utils.write_data(target_path, self.papers)

    def save_to_file_incremental(self, target_path: str, conflict_decisions: Dict[str, str]):
        """
        增量模式：读取目标文件，根据 decisions 决定如何合并当前的新增项
        conflict_decisions: { paper_key: 'overwrite' | 'skip' }
        """
        success, existing_papers = self.update_utils.read_data(target_path)
        if not success: existing_papers = []
        
        existing_map = {p.get_key(): i for i, p in enumerate(existing_papers)}
        
        # 待追加的论文
        papers_to_append = []
        
        for p in self.papers:
            # 规范化
            self.update_utils.normalize_assets(p)
            p.doi = clean_doi(p.doi, self.conflict_marker)
            
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
        self.update_utils.write_data(target_path, final_list)
        return final_list

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
        existing_papers = []
        if os.path.exists(target_path):
            success,existing_papers = self.update_utils.read_data(target_path)
            if not success:
                print(f"加载文件失败: {target_path}")
        
        merged_papers = list(existing_papers)
        existing_map = {}
        for p in existing_papers:
            key = p.get_key()
            existing_map[key] = p

        has_conflict = False
        
        for paper in self.papers:
            # 预处理
            paper.doi = clean_doi(paper.doi, self.conflict_marker) if paper.doi else ""
            paper.category = self.update_utils.normalize_category_value(paper.category, self.config)
            
            # 确保 UID (如果不保存只是检查，可以先不生成，但为了统一逻辑，这里确保一下)
            if not paper.uid:
                paper.uid = generate_paper_uid(getattr(paper, 'title', ''), getattr(paper, 'doi', ''))

            key = paper.get_key()
            if key in existing_map:
                has_conflict = True
            else:
                pass 
                
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


        existing_papers = []
        if os.path.exists(target_path):
            success,existing_papers = self.update_utils.read_data(target_path)
            if not success:
                print(f"加载文件失败: {target_path}")
        
        merged_papers = list(existing_papers)
        # 建立映射: Key -> List index
        existing_map = {}
        for idx, p in enumerate(existing_papers):
            key = p.get_key()
            existing_map[key] = idx

        for paper in self.papers:
            # 1. 规范化 Assets (移动文件到 assets/{uid})
            # 这是一个副作用操作，会将 temp 文件归档
            paper = self.update_utils.normalize_assets(paper)

            # 2. 规范化其他字段
            paper.doi = clean_doi(paper.doi, self.conflict_marker) if paper.doi else ""
            paper.category = self.update_utils.normalize_category_value(paper.category, self.config)
            
            key = paper.get_key()
            
            if key in existing_map:
                if conflict_mode == 'overwrite_duplicates' or conflict_mode == 'overwrite_all':
                    idx = existing_map[key]
                    merged_papers[idx] = paper
                elif conflict_mode == 'skip_duplicates' or conflict_mode == 'skip_all':
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
        success, new_papers = self.update_utils.read_data(filepath)
        if not success:
            print(f"加载文件失败: {filepath}")
            return 0
        self.papers = new_papers
        return len(self.papers)
    
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
            if not p.uid:
                p.uid = generate_paper_uid(getattr(p, 'title', ''), getattr(p, 'doi', ''))
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

        # 预检查：字段中的每个路径都必须可解析并存在
        items = [x.strip() for x in str(raw_val).split('|') if x.strip()]
        for item in items:
            resolved = self.update_utils.resolve_asset_path(item, field_name)
            if not resolved or not os.path.exists(resolved):
                return False, "", f"文件不存在或无法解析: {item}"

        try:
            setattr(paper, field_name, str(raw_val).strip())
            self.update_utils.normalize_asset_fields(paper, [field_name], strict=True)
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
        for k in ['update_json', 'update_csv', 'my_update_json', 'my_update_csv']:
            p = paths.get(k)
            if p and os.path.exists(p):
                out.append(p)
        for p in paths.get('extra_update_files_list', []):
            if p and os.path.exists(p):
                out.append(p)
        return list(dict.fromkeys(out))

    def _collect_asset_reference_papers(self) -> List[Paper]:
        collected: List[Paper] = []

        db_path = self.settings['paths'].get('database')
        if db_path and os.path.exists(db_path):
            success, papers = self.update_utils.read_data(db_path)
            if success:
                collected.extend(papers)

        for fpath in self._iter_existing_update_files():
            success, papers = self.update_utils.read_data(fpath)
            if success:
                collected.extend(papers)

        if self.papers:
            collected.extend(self.papers)

        return collected

    def cleanup_redundant_assets(self) -> Dict[str, Any]:
        """
        清除冗余资源并返回审计报告：
        - 未被任何论文条目引用的 uid 文件夹
        - 已存在 uid 文件夹中未被字段引用的文件
        - 论文字段引用缺失的文件
        """
        assets_root = os.path.join(BASE_DIR, self.assets_dir)
        report: Dict[str, Any] = {
            'deleted_uid_dirs': [],
            'deleted_files': [],
            'papers_with_unreferenced_assets': [],
            'missing_references': [],
        }
        if not os.path.isdir(assets_root):
            return report

        papers = self._collect_asset_reference_papers()

        uid_to_refs: Dict[str, set] = {}
        uid_to_title: Dict[str, str] = {}
        for p in papers:
            uid = (getattr(p, 'uid', '') or '').strip()
            if not uid:
                continue
            if uid not in uid_to_title:
                uid_to_title[uid] = getattr(p, 'title', '') or ''
            ref_set = uid_to_refs.setdefault(uid, set())
            for field_name in ('pipeline_image', 'paper_file'):
                raw_val = getattr(p, field_name, '') or ''
                if not raw_val:
                    continue
                parts = [x.strip() for x in str(raw_val).split('|') if x.strip()]
                for item in parts:
                    ref_set.add(item.replace('\\', '/'))
                    resolved = self.update_utils.resolve_asset_path(item, field_name)
                    if not resolved or not os.path.exists(resolved):
                        report['missing_references'].append({
                            'uid': uid,
                            'title': getattr(p, 'title', ''),
                            'field': field_name,
                            'reference': item,
                        })

        for entry in os.listdir(assets_root):
            if entry == 'temp':
                continue
            uid_dir = os.path.join(assets_root, entry)
            if not os.path.isdir(uid_dir):
                continue
            uid = entry
            ref_set = uid_to_refs.get(uid, set())
            if not ref_set:
                shutil.rmtree(uid_dir, ignore_errors=True)
                report['deleted_uid_dirs'].append(uid)
                continue

            referenced_files_abs = set()
            for rel_ref in ref_set:
                ref_abs = os.path.join(BASE_DIR, rel_ref)
                if os.path.exists(ref_abs):
                    referenced_files_abs.add(os.path.normpath(ref_abs))

            unreferenced_here = []
            for root, _, files in os.walk(uid_dir):
                for fn in files:
                    abs_file = os.path.normpath(os.path.join(root, fn))
                    if abs_file not in referenced_files_abs:
                        rel_file = os.path.relpath(abs_file, BASE_DIR).replace('\\', '/')
                        unreferenced_here.append(rel_file)
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

        return report



    # ================= PR 提交逻辑 =================

    def has_update_files(self) -> bool:
        """检查是否存在更新文件"""
        # 只要主更新文件存在即可
        return self.primary_update_file and os.path.exists(self.primary_update_file)

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