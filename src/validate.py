"""
统一验证接口
用于验证数据库文件和各更新文件的完整性、冲突及资源引用
"""
import os
import sys
from typing import List, Dict

# 添加项目根目录
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config_loader import get_config_instance
from src.core.database_manager import DatabaseManager
from src.core.update_file_utils import get_update_file_utils
from src.core.database_model import Paper, is_same_identity

class Validator:
    def __init__(self):
        self.config = get_config_instance()
        self.settings = self.config.settings
        self.db_manager = DatabaseManager()
        self.update_utils = get_update_file_utils()
        
        self.db_path = self.settings['paths']['database']
        self.update_files = []
        
        # 收集所有更新文件
        paths = self.settings['paths']
        for key in ['update_csv', 'update_json', 'my_update_csv', 'my_update_json']:
            p = paths.get(key)
            if p and os.path.exists(p): self.update_files.append(p)
        
        for p in paths.get('extra_update_files_list', []):
            if p and os.path.exists(p): self.update_files.append(p)

    def run(self):
        print("="*50)
        print("开始全量验证...")
        print("="*50)
        
        # 1. 验证数据库
        print(f"\n[Database] 检查: {self.db_path}")
        db_papers = self.db_manager.load_database()
        self._check_papers(db_papers, "Database")
        
        # 2. 验证更新文件
        all_papers = list(db_papers)
        
        for fpath in self.update_files:
            print(f"\n[Update File] 检查: {os.path.basename(fpath)}")
            papers = self.update_utils.read_data(fpath)
            self._check_papers(papers, os.path.basename(fpath))
            
            # 3. 检查与数据库的重复 (Cross-Check)
            print(f"  > 正在检查与数据库的重复项...")
            dups = 0
            for p in papers:
                for db_p in db_papers:
                    if is_same_identity(p, db_p):
                        # 如果是显式标记的冲突，则不算"意外重复"
                        if not p.conflict_marker and not db_p.conflict_marker:
                            print(f"    ! 发现重复: {p.title[:40]}... (与数据库中条目一致)")
                            dups += 1
                        break
            if dups == 0:
                print("    ✓ 无未标记重复项")
            
            all_papers.extend(papers)

        print("\n" + "="*50)
        print("验证结束")
        print("="*50)

    def _check_papers(self, papers: List[Paper], source_name: str):
        if not papers:
            print("  (空文件)")
            return

        issues = 0
        assets_issues = 0
        
        for i, p in enumerate(papers):
            # 基础字段验证
            valid, errors, _ = p.validate_paper_fields(
                self.config, check_required=True, check_non_empty=True, no_normalize=True
            )
            
            if not valid:
                print(f"  #{i+1} [Field Error] {p.title[:30]}...")
                for e in errors:
                    print(f"     - {e}")
                issues += 1
            
            # 资源引用验证 (双重检查 assets 实际存在性)
            # validate_paper_fields 已经包含路径检查，这里做更直观的输出
            if p.uid:
                asset_dir = os.path.join(self.config.project_root, 'assets', p.uid)
                if not os.path.exists(asset_dir) and (p.pipeline_image or p.paper_file):
                    print(f"  #{i+1} [Asset Error] UID文件夹缺失: assets/{p.uid}")
                    assets_issues += 1
            elif p.pipeline_image or p.paper_file:
                print(f"  #{i+1} [Asset Error] 有资源引用但缺失UID (需运行更新以自动修复)")
                assets_issues += 1

        if issues == 0 and assets_issues == 0:
            print(f"  ✓ {len(papers)} 篇论文格式验证通过")
        else:
            print(f"  Found {issues} field issues, {assets_issues} asset issues.")

if __name__ == "__main__":
    Validator().run()