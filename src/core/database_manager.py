"""
数据库管理器 (Refactored for CSV/JSON)
处理核心数据库的读写、冲突检测与合并
完全移除 Pandas/OpenPyXL 依赖
"""
import os
import sys
import shutil
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity
from src.core.update_file_utils import get_update_file_utils
from src.utils import backup_file

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        
        # 数据库路径 (CSV 或 JSON)
        self.database_path = self.settings['paths']['database']
        self.backup_dir = self.settings['paths']['backup_dir']
        self.conflict_marker = self.settings['database']['conflict_marker']
        
        self.update_utils = get_update_file_utils()

        # 确保目录存在
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def load_database(self) -> List[Paper]:
        """加载数据库"""
        if not os.path.exists(self.database_path):
            return []
        return self.update_utils.read_data(self.database_path)

    def save_database(self, papers: List[Paper]) -> bool:
        """保存数据库 (带备份)"""
        try:
            # 1. 备份
            if os.path.exists(self.database_path):
                backup_file(self.database_path, self.backup_dir)
            
            # 2. 规范化 Assets (确保所有资源的 UID 对应且文件在 assets/{uid} 下)
            # 这一步会移动文件，副作用
            normalized_papers = []
            for p in papers:
                p = self.update_utils.normalize_assets(p)
                normalized_papers.append(p)

            # 3. 写入
            return self.update_utils.write_data(self.database_path, normalized_papers)
            
        except Exception as e:
            print(f"保存数据库失败: {e}")
            return False

    def add_papers(self, new_papers: List[Paper], conflict_resolution: str = 'mark') -> Tuple[List[Paper], List[Paper], List[str]]:
        """
        添加新论文到数据库
        返回: (Added, Conflicts, InvalidMessages)
        """
        # 1. 加载现有数据
        current_papers = self.load_database()
        
        # 验证现有数据的完整性 (仅记录日志，不阻断)
        invalid_msg = []
        for p in current_papers:
            # 简单验证，不normalize
            valid, errors, _ = p.validate_paper_fields(self.config, check_required=True, no_normalize=True)
            if not valid:
                invalid_msg.append(f"DB Existing: {p.title[:30]} - {errors[0]}")

        # 2. 分离冲突与非冲突 (处理逻辑保持原有思路：Group by identity)
        # 结构: { key: [MainPaper, Conflict1, Conflict2...] }
        # key 是 (doi, title) tuple
        paper_groups: Dict[Tuple[str, str], List[Paper]] = {}
        
        # 辅助：展平现有列表到 groups
        for p in current_papers:
            key = p.get_key()
            if key not in paper_groups:
                paper_groups[key] = []
            paper_groups[key].append(p)

        added_papers = []
        conflict_papers = []

        # 3. 处理新论文
        for new_p in new_papers:
            key = new_p.get_key()
            
            # 如果是全新的
            if key not in paper_groups:
                paper_groups[key] = [new_p]
                added_papers.append(new_p)
                continue
            
            # 如果已存在 (冲突处理)
            existing_group = paper_groups[key]
            
            # 检查完全重复 (Strict Compare)
            is_dup = False
            for ex in existing_group:
                if self._is_strictly_equal(ex, new_p):
                    is_dup = True
                    break
            
            if is_dup:
                print(f"跳过完全重复论文: {new_p.title[:30]}")
                continue

            # 处理冲突
            if conflict_resolution == 'skip':
                print(f"跳过冲突论文: {new_p.title[:30]}")
                continue
            elif conflict_resolution == 'replace':
                # 替换：保留新论文，丢弃旧组
                paper_groups[key] = [new_p]
                added_papers.append(new_p)
                print(f"替换冲突论文: {new_p.title[:30]}")
            else: # mark (默认)
                new_p.conflict_marker = True
                existing_group.append(new_p) # 添加到组尾
                conflict_papers.append(new_p)
                print(f"标记冲突论文: {new_p.title[:30]}")

        # 4. 重新构建列表并排序
        # 排序规则: Category (Order) -> Submission Time (Desc)
        
        final_list = []
        
        # 辅助：获取分类的 Order
        cat_order_map = {c['unique_name']: (c.get('order', 999), i) 
                        for i, c in enumerate(self.config.get_active_categories())}
        
        def get_sort_key(p: Paper):
            # 主分类（第一个）
            first_cat = p.category.split(';')[0].strip() if p.category else ""
            order_info = cat_order_map.get(first_cat, (9999, 9999))
            
            # 时间解析
            try:
                ts = datetime.strptime(p.submission_time, "%Y-%m-%d %H:%M:%S")
                ts_val = ts.timestamp()
            except Exception:
                # 在 Windows 上 datetime.min.timestamp() 可能抛出 OSError
                ts_val = 0.0

            # 返回: (CategoryOrder, OriginalIndex, -Timestamp)
            return (order_info[0], order_info[1], -1 * ts_val)

        # 将每个 group 内部先按时间倒序排好，确保主论文（无冲突标记或最新的）在第一个
        # 这里策略：如果有 conflict_marker=False 的，优先放在前面作为 Main
        # 如果都有，选最新的作为 Main
        
        all_groups = list(paper_groups.values())
        
        # 展平前先处理每个组的内部顺序
        # 逻辑：非冲突且最新的 -> 冲突且最新的
        for group in all_groups:
            group.sort(key=lambda x: (not x.conflict_marker, x.submission_time), reverse=True)
        
        # 此时 group[0] 是这一组的代表，用于通过 Category 排序
        # 对 all_groups 进行排序
        all_groups.sort(key=lambda g: get_sort_key(g[0]))
        
        # 展平
        for group in all_groups:
            final_list.extend(group)

        # 5. 保存
        if self.save_database(final_list):
            return added_papers, conflict_papers, invalid_msg
        else:
            return [], new_papers, invalid_msg

    def _is_strictly_equal(self, p1: Paper, p2: Paper) -> bool:
        """比较非系统字段是否完全一致"""
        d1 = p1.to_dict()
        d2 = p2.to_dict()
        
        ignore_fields = {t['id'] for t in self.config.get_system_tags()}
        # 还要忽略 uid ? 如果 uid 不同但内容相同，视作内容重复
        ignore_fields.add('uid')
        
        keys = set(d1.keys()) | set(d2.keys())
        for k in keys:
            if k in ignore_fields: continue
            v1 = str(d1.get(k, "")).strip()
            v2 = str(d2.get(k, "")).strip()
            if v1 != v2: return False
        return True

    def update_paper(self, target_paper: Paper, updates: Dict[str, Any]) -> bool:
        """更新单篇论文"""
        papers = self.load_database()
        updated = False
        
        for i, p in enumerate(papers):
            if is_same_identity(p, target_paper):
                # 如果是冲突组，需要确保只更新特定的那一个（比较对象引用或内容）
                # 这里简单处理：如果 target_paper 传的是对象引用最好
                # 或者比较所有字段
                # 简化逻辑：更新第一个匹配 identity 的（通常 UI 只会让用户操作主条目）
                # 为了支持冲突处理，可能需要更精确的匹配（如比较 uid 或 raw index）
                # 假设 UI 传递的是完整的原始对象进行定位：
                
                # 尝试通过 UID 匹配 (最准)
                if p.uid and target_paper.uid and p.uid == target_paper.uid:
                    self._apply_updates(papers[i], updates)
                    updated = True
                    break
                
                # 否则 Fallback 到 Identity 且内容高度相似
                if not updated: 
                    self._apply_updates(papers[i], updates)
                    updated = True
                    break
        
        if updated:
            return self.save_database(papers)
        return False

    def _apply_updates(self, paper: Paper, updates: Dict):
        for k, v in updates.items():
            if hasattr(paper, k):
                setattr(paper, k, v)

    def delete_paper(self, target_paper: Paper) -> bool:
        """删除论文"""
        papers = self.load_database()
        original_len = len(papers)
        
        # 优先 UID
        if target_paper.uid:
            papers = [p for p in papers if p.uid != target_paper.uid]
        else:
            # Fallback identity
            papers = [p for p in papers if not is_same_identity(p, target_paper)]
            
        if len(papers) < original_len:
            return self.save_database(papers)
        return False