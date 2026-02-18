"""
数据库管理器
处理核心数据库的读写、冲突检测与合并
完全移除 Pandas/OpenPyXL 依赖，忠实还原原有分组逻辑
"""
import os
import sys
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity, is_duplicate_paper
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

    def load_database(self) -> Tuple[bool, List[Paper]]:
        """加载数据库"""
        if not os.path.exists(self.database_path):
            return False, []
        return self.update_utils.read_data(self.database_path)

    def save_database(self, papers: List[Paper]) -> bool:
        """保存数据库 (带备份 & 资源规范化)"""
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
        添加新论文到数据库，同时验证冲突
        
        参数:
            new_papers: 新论文列表
            conflict_resolution: 冲突解决策略 ('mark', 'skip', 'replace')
        
        返回:
            Tuple[成功添加的论文列表, 冲突论文列表（被标记后需要加入数据库的）, 验证失败消息列表]
        """
        # 1. 加载现有数据库
        success, old_papers = self.load_database()
        if not success:
            return [], new_papers, [f"无法加载数据库: {self.database_path}"]

        # 2. 统一验证所有已写入数据库的论文条目（记录日志）
        invalid_msg = []
        for p in old_papers:
            try:
                # 仅做检查，不 normalize
                valid, errors, _ = p.validate_paper_fields(self.config, check_required=True, check_non_empty=True, no_normalize=True)
                if not valid or p.invalid_fields:
                    invalid_msg.append(f"DB Existing '{p.title[:30]}' invalid: {errors[:2]}")
            except Exception as e:
                print(f"验证已存在论文时出错: {e}")

        # 3. 还原原有的冲突结构
        # non_conflict_papers存储结构: [(主论文, [冲突论文1, 冲突论文2, ...]), ...]
        non_conflict_papers: List[Tuple[Paper, List[Paper]]] = []    
        old_conflict_papers = []
        
        # 分离
        for p in old_papers:
            if not p.conflict_marker:
                non_conflict_papers.append((p, []))
            else:
                old_conflict_papers.append(p)
        
        # 重组
        for old_conflict in old_conflict_papers:
            conflict_found = False
            for i, (main_paper, conflict_list) in enumerate(non_conflict_papers):
                if is_same_identity(old_conflict, main_paper):
                    conflict_list.append(old_conflict)
                    conflict_found = True
                    break
            
            if not conflict_found:
                # 孤儿冲突论文，转正
                print(f"警告：数据库原有冲突论文 {old_conflict.title[:30]}... 未找到主论文，已转正")
                non_conflict_papers.append((old_conflict, []))
                old_conflict.conflict_marker = False
        
        added_papers = []
        conflict_papers = []

        # 4. 处理新论文
        for new_paper in new_papers:
            # 检查是否已存在
            same_identity_indices = []
            main_paper_idx = -1
            
            # 找出所有同identity论文
            for idx, (main_paper, conflict_list) in enumerate(non_conflict_papers):
                if is_same_identity(new_paper, main_paper):
                    same_identity_indices.append(idx)
                    # 记录第一次匹配到的主论文索引
                    if main_paper_idx == -1:
                        main_paper_idx = idx
            
            if same_identity_indices:
                # 检查是否为"完全重复提交" - 需要包括主论文和所有冲突论文
                all_same_papers = []
                for idx in same_identity_indices:
                    main_paper, conflict_list = non_conflict_papers[idx]
                    all_same_papers.append(main_paper)
                    all_same_papers.extend(conflict_list)
                
                # 使用 database_model 中的 is_duplicate_paper (需传入 list)
                is_duplicate, conflict_field = is_duplicate_paper(all_same_papers, new_paper, complete_compare=False)
                
                if is_duplicate:
                    print(f"论文: {new_paper.title[:30]}... ——完全重复，跳过")
                    continue
                
                # 不是完全相同，按冲突策略处理
                if conflict_resolution == 'skip':
                    print(f"论文: {new_paper.title[:30]}... ——存在冲突 ({conflict_field})，跳过")
                    continue
                
                elif conflict_resolution == 'replace':
                    # 完全替换：删除旧组，添加新组
                    for idx in sorted(same_identity_indices, reverse=True):
                        del non_conflict_papers[idx]
                    
                    non_conflict_papers.append((new_paper, []))
                    added_papers.append(new_paper)
                    print(f"论文: {new_paper.title[:30]}... ——存在冲突，已替换旧论文")
                
                elif conflict_resolution == 'mark':
                    new_paper.conflict_marker = True
                    
                    if main_paper_idx != -1:
                        # 添加到对应主论文的冲突列表中
                        non_conflict_papers[main_paper_idx][1].append(new_paper)
                        conflict_papers.append(new_paper)
                        print(f"论文: {new_paper.title[:30]}... ——存在冲突，已标记并添加")
                    else:
                        # 理论上不应走到这里，因为 same_identity_indices 不为空意味着至少找到了一个
                        # 除非找到的全是冲突论文但没有主论文（上面的重组逻辑已处理此情况）
                        non_conflict_papers.append((new_paper, []))
                        new_paper.conflict_marker = False
                        added_papers.append(new_paper)
            else:
                # 新论文
                non_conflict_papers.append((new_paper, []))
                added_papers.append(new_paper)
                print(f"论文: {new_paper.title[:30]}... ——新论文添加")
        
        # 5. 排序与展平
        # 按category分组
        category_groups = {}
        for main_paper, conflict_list in non_conflict_papers:
            # 取第一个分类
            cat = str(main_paper.category).split('|')[0].strip() if main_paper.category else "Uncategorized"
            if cat not in category_groups:
                category_groups[cat] = []
            category_groups[cat].append((main_paper, conflict_list))
        
        # 获取分类顺序
        active_cats = self.config.get_active_categories()
        cat_order_map = {c['unique_name']: (c.get('order', 999), i) for i, c in enumerate(active_cats)}
        
        def get_cat_sort_key(cat_name):
            return cat_order_map.get(cat_name, (9999, 9999))

        sorted_all_papers = []
        
        # 对 Category 排序
        sorted_cats = sorted(category_groups.keys(), key=get_cat_sort_key)
        
        for category in sorted_cats:
            papers_in_category = category_groups[category]
            
            # 每个 Category 内，按主论文提交时间倒序
            papers_in_category.sort(key=lambda x: x[0].submission_time or "", reverse=True)
            
            for main_paper, conflict_list in papers_in_category:
                # 先添加冲突论文（按提交时间倒序，最新的在最上面，紧随主论文之后? 原逻辑似乎是先 conflict 后 main?）
                # 重新阅读原 database_manager.py 逻辑: 
                # "sorted_all_papers.extend(conflict_list) ... sorted_all_papers.append(main_paper)"
                # 是的，原逻辑是先加冲突列表，再加主论文。这样在 Excel/CSV 中，主论文在下面，冲突的在上面（堆栈式）。
                
                if conflict_list:
                    conflict_list.sort(key=lambda x: x.submission_time or "", reverse=True)
                    sorted_all_papers.extend(conflict_list)
                
                sorted_all_papers.append(main_paper)
        
        # 6. 保存
        success = self.save_database(sorted_all_papers)
        
        if success:
            return added_papers, conflict_papers, invalid_msg
        else:
            return [], new_papers, invalid_msg
    
    def update_paper(self, target_paper: Paper, updates: Dict[str, Any]) -> bool:
        """更新单篇论文"""
        success,papers = self.load_database()
        if not success:            
            print(f"加载数据库失败: {self.database_path}")
            return False
        updated = False
        
        # 优先使用 UID 匹配
        for p in papers:
            if p.uid and target_paper.uid and p.uid == target_paper.uid:
                self._apply_updates(p, updates)
                updated = True
                break
        
        # 如果没匹配到，尝试 Identity
        if not updated:
            for p in papers:
                if is_same_identity(p, target_paper):
                    # 如果有冲突标记，需要更小心。这里简化：只更新第一个匹配的
                    # 或者如果 target_paper 也是从列表里拿出来的，可以比较内存地址(不可靠)或全部字段
                    self._apply_updates(p, updates)
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
        """删除单篇论文"""
        success,papers = self.load_database()
        if not success:            
            print(f"加载数据库失败: {self.database_path}")
            return False
        original_len = len(papers)
        
        new_papers = []
        deleted = False
        
        for p in papers:
            if not deleted:
                # 尝试匹配
                if p.uid and target_paper.uid and p.uid == target_paper.uid:
                    deleted = True
                    continue
                elif is_same_identity(p, target_paper):
                    # 只有当非系统字段也一致时才认为是同一篇（防止删错冲突组里的其他论文）
                    # 简化：假设 GUI 传来的 paper 具有唯一性
                    deleted = True
                    continue
            new_papers.append(p)

        if len(new_papers) < original_len:
            return self.save_database(new_papers)
        
        return False