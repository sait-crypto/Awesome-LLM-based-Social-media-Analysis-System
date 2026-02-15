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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity
from src.core.update_file_utils import get_update_file_utils
from src.process_zotero_meta import ZoteroProcessor
from src.utils import clean_doi, ensure_directory

# 锚定根目录
BASE_DIR = str(get_config_instance().project_root)

class SubmitLogic:
    """提交系统的业务逻辑控制器"""

    def __init__(self):
        # 加载配置
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.update_utils = get_update_file_utils()
        self.zotero_processor = ZoteroProcessor()
        
        # 论文数据列表
        self.papers: List[Paper] = []
        
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

    def load_existing_updates(self) -> int:
        """加载默认更新文件中的论文"""
        count = 0
        if self.primary_update_file and os.path.exists(self.primary_update_file):
            try:
                # 使用通用的 read_data 接口
                self.papers = self.update_utils.read_data(self.primary_update_file)
                count = len(self.papers)
            except Exception as e:
                raise Exception(f"加载更新文件失败: {e}")
        return count

    def create_new_paper(self) -> Paper:
        """创建一个新的占位符论文并添加到列表"""
        # 创建时就分配一个临时 UID，方便关联资源
        new_uid = str(uuid.uuid4())[:8]
        placeholder_data = {
            'uid': new_uid,
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
            placeholder = Paper(title=self.PLACEHOLDER, uid=new_uid)
            
        self.papers.append(placeholder)
        return placeholder

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
            existing_papers = self.update_utils.read_data(target_path)
        
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
                paper.uid = str(uuid.uuid4())[:8]

            key = paper.get_key()
            if key in existing_map:
                has_conflict = True
            else:
                pass 
                
        return merged_papers, has_conflict

    def perform_save(self, target_path: str, conflict_mode: str = 'overwrite_duplicates') -> List[Paper]:
        """执行保存操作 (包含 Assets 规范化)"""
        existing_papers = []
        if os.path.exists(target_path):
            existing_papers = self.update_utils.read_data(target_path)
        
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
        new_papers = self.update_utils.read_data(filepath)
        self.papers = new_papers
        return len(self.papers)

    # ================= Zotero 逻辑 =================

    def process_zotero_json(self, json_str: str) -> List[Paper]:
        """处理Zotero JSON字符串"""
        return self.zotero_processor.process_meta_data(json_str)

    def add_zotero_papers(self, papers: List[Paper]) -> int:
        """批量添加Zotero论文"""
        # 为新论文分配 UID
        for p in papers:
            if not p.uid:
                p.uid = str(uuid.uuid4())[:8]
        self.papers.extend(papers)
        return len(papers)

    def get_zotero_fill_updates(self, source_paper: Paper, target_index: int) -> Tuple[List[str], List[Tuple[str, Any]]]:
        """计算Zotero填充的更新内容"""
        if not (0 <= target_index < len(self.papers)):
            return [], []
            
        target_paper = self.papers[target_index]
        conflicts = []
        fields_to_update = []
        
        system_fields = [t["id"] for t in self.config.get_system_tags()] # 使用 ID 匹配
        
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
    
    def import_file_asset(self, src_path: str, asset_type: str) -> str:
        """
        GUI 临时导入文件资源：
        1. 将文件复制到 assets/temp/ 目录 (防止源文件被移动/删除)
        2. 返回 assets/temp/filename 相对路径供 GUI 显示
        3. 保存时 (perform_save -> normalize_assets) 会将其移动到 assets/{uid}/
        """
        if not src_path or not os.path.exists(src_path):
            return ""
        
        # 临时目录 assets/temp/
        temp_dir = os.path.join(BASE_DIR, self.assets_dir, 'temp')
        ensure_directory(temp_dir)
        
        filename = os.path.basename(src_path)
        # 防止重名：加时间戳
        name, ext = os.path.splitext(filename)
        timestamp = int(time.time())
        # 简单检查是否存在，存在则加后缀
        if os.path.exists(os.path.join(temp_dir, filename)):
            filename = f"{name}_{timestamp}{ext}"
            
        dest_path = os.path.join(temp_dir, filename)
        
        try:
            shutil.copy2(src_path, dest_path)
            # 返回相对路径 (正斜杠)
            rel_path = f"{self.assets_dir}temp/{filename}".replace('\\', '/')
            return rel_path
        except Exception as e:
            print(f"Import file failed: {e}")
            return ""

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