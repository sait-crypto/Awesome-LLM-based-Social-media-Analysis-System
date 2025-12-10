"""
数据库管理器
处理Excel数据库的读写操作
"""
import os
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter
from typing import Dict, List, Optional, Any, Tuple
import shutil
from datetime import datetime
import warnings

# 导入配置和模型
from .config_loader import config_loader
from .database_model import Paper


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.config = config_loader
        self.settings = config_loader.settings
        self.core_excel_path = self.settings['paths']['core_excel']
        self.backup_dir = self.settings['paths']['backup_dir']
        self.conflict_marker = self.settings['database']['conflict_marker']
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.core_excel_path), exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def backup_database(self) -> str:
        """备份数据库，返回备份文件路径"""
        if not os.path.exists(self.core_excel_path):
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"paper_database_backup_{timestamp}.xlsx"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        shutil.copy2(self.core_excel_path, backup_path)
        print(f"数据库已备份到: {backup_path}")
        return backup_path
    
    def load_database(self) -> pd.DataFrame:
        """加载数据库到DataFrame"""
        if not os.path.exists(self.core_excel_path):
            # 创建新的数据库文件
            return self._create_new_database()
        
        try:
            # 尝试读取Excel文件
            df = pd.read_excel(self.core_excel_path, engine='openpyxl')
            
            # 确保所有必需的列都存在
            return self._ensure_columns_exist(df)
        except Exception as e:
            print(f"加载数据库失败: {e}")
            # 创建新的数据库文件
            return self._create_new_database()
    
    def _create_new_database(self) -> pd.DataFrame:
        """创建新的数据库DataFrame"""
        # 获取所有激活的标签
        active_tags = self.config.get_active_tags()
        
        # 创建空的DataFrame，按照order排序
        active_tags.sort(key=lambda x: x['order'])
        columns = [tag['table_name'] for tag in active_tags]
        
        df = pd.DataFrame(columns=columns)
        print(f"创建新的数据库文件: {self.core_excel_path}")
        return df
    
    def _ensure_columns_exist(self, df: pd.DataFrame) -> pd.DataFrame:
        """确保DataFrame包含所有必需的列"""
        active_tags = self.config.get_active_tags()
        active_tags.sort(key=lambda x: x['order'])
        required_columns = [tag['table_name'] for tag in active_tags]
        
        # 添加缺失的列
        for column in required_columns:
            if column not in df.columns:
                df[column] = None
        
        # 移除多余的列（不在激活标签中的列）
        columns_to_keep = [col for col in df.columns if col in required_columns]
        
        # 重新排序列
        df = df[required_columns]
        
        return df
    
    def save_database(self, df: pd.DataFrame, password: str = "") -> bool:
        """保存DataFrame到Excel文件"""
        try:
            # 备份原文件
            self.backup_database()
            
            # 保存到Excel
            with pd.ExcelWriter(
                self.core_excel_path,
                engine='openpyxl'
            ) as writer:
                df.to_excel(writer, index=False, sheet_name='Papers')
                
                # 获取工作簿和工作表
                workbook = writer.book
                worksheet = writer.sheets['Papers']
                
                # 应用格式
                self._apply_excel_formatting(workbook, worksheet, df)
                
                # 如果有密码，尝试设置保护（但openpyxl的写保护有限）
                if password:
                    try:
                        worksheet.protection.set_password(password)
                        worksheet.protection.sheet = True
                    except:
                        print("注意：无法设置Excel保护，文件将以未加密形式保存")
            
            print(f"数据库已保存到: {self.core_excel_path}")
            return True
        except Exception as e:
            print(f"保存数据库失败: {e}")
            return False
    
    def _apply_excel_formatting(self, workbook, worksheet, df):
        """应用Excel格式"""
        # 设置列宽
        for column in df.columns:
            column_letter = get_column_letter(df.columns.get_loc(column) + 1)
            max_length = max(
                df[column].astype(str).map(len).max(),
                len(str(column))
            )
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # 设置标题行样式
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
        
        # 标记冲突行
        if 'conflict_marker' in df.columns:
            conflict_fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
            
            for idx, row in df.iterrows():
                if row.get('conflict_marker'):
                    for cell in worksheet[idx + 2]:  # +2因为标题行是1，索引从0开始
                        cell.fill = conflict_fill
    
    def get_password(self) -> str:
        """获取Excel密码"""
        # 首先尝试从环境变量获取
        password = os.environ.get('EXCEL_KEY', '')
        if password:
            return password
        
        # 尝试从本地文件获取
        password_path = self.settings['excel'].get('password_path', '')
        if password_path and os.path.exists(password_path):
            try:
                with open(password_path, 'r', encoding='utf-8') as f:
                    password = f.read().strip()
                    return password
            except:
                pass
        
        return ""  # 返回空字符串表示不加密
    
    def get_papers_from_dataframe(self, df: pd.DataFrame) -> List[Paper]:
        """从DataFrame提取Paper对象列表"""
        papers = []
        
        for _, row in df.iterrows():
            paper_data = {}
            
            # 将DataFrame行转换为字典
            for tag in self.config.get_active_tags():
                column_name = tag['table_name']
                if column_name in row:
                    value = row[column_name]
                    
                    # 处理NaN值
                    if pd.isna(value):
                        value = ""
                    
                    # 根据类型转换
                    if tag['type'] == 'bool':
                        value = bool(value) if not pd.isna(value) else False
                    elif tag['type'] == 'int':
                        value = int(value) if not pd.isna(value) else 0
                    
                    paper_data[tag['variable']] = value
            
            # 创建Paper对象
            paper = Paper.from_dict(paper_data)
            papers.append(paper)
        
        return papers
    
    def get_dataframe_from_papers(self, papers: List[Paper]) -> pd.DataFrame:
        """从Paper对象列表创建DataFrame"""
        # 获取激活的标签
        active_tags = self.config.get_active_tags()
        active_tags.sort(key=lambda x: x['order'])
        
        # 准备数据
        data = []
        for paper in papers:
            row = {}
            for tag in active_tags:
                column_name = tag['table_name']
                value = getattr(paper, tag['variable'], "")
                row[column_name] = value
            data.append(row)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 确保列顺序正确
        column_order = [tag['table_name'] for tag in active_tags]
        df = df[column_order]
        
        return df
    
    def add_papers(self, new_papers: List[Paper], conflict_resolution: str = 'mark') -> Tuple[List[Paper], List[Paper]]:
        """
        添加新论文到数据库
        
        参数:
            new_papers: 新论文列表
            conflict_resolution: 冲突解决策略 ('mark', 'skip', 'replace')
        
        返回:
            Tuple[成功添加的论文列表, 冲突论文列表]
        """
        # 加载现有数据库
        df = self.load_database()
        existing_papers = self.get_papers_from_dataframe(df)
        
        added_papers = []
        conflict_papers = []
        
        for new_paper in new_papers:
            # 检查是否已存在
            is_duplicate = False
            conflict_with = None
            
            for existing_paper in existing_papers:
                if new_paper.is_similar_to(existing_paper):
                    is_duplicate = True
                    conflict_with = existing_paper
                    break
            
            if is_duplicate:
                if conflict_resolution == 'skip':
                    # 跳过重复论文
                    continue
                elif conflict_resolution == 'replace':
                    # 替换现有论文
                    existing_papers = [p for p in existing_papers if not p.is_similar_to(new_paper)]
                    existing_papers.append(new_paper)
                    added_papers.append(new_paper)
                elif conflict_resolution == 'mark':
                    # 标记冲突
                    new_paper.conflict_marker = self.conflict_marker
                    conflict_papers.append((new_paper, conflict_with))
                    existing_papers.append(new_paper)
                    added_papers.append(new_paper)
            else:
                # 新论文，直接添加
                existing_papers.append(new_paper)
                added_papers.append(new_paper)
        
        # 排序：先按分类，再按提交时间（假设提交时间在submission_time字段）
        existing_papers.sort(key=lambda x: (
            x.category,
            x.submission_time if hasattr(x, 'submission_time') and x.submission_time else ""
        ), reverse=True)  # 越晚提交越靠前
        
        # 保存更新后的数据库
        df = self.get_dataframe_from_papers(existing_papers)
        password = self.get_password()
        success = self.save_database(df, password)
        
        if success:
            return added_papers, conflict_papers
        else:
            return [], new_papers  # 如果保存失败，返回空列表和所有新论文作为冲突
    
    def update_paper(self, paper_id: str, updates: Dict[str, Any]) -> bool:
        """更新单篇论文"""
        df = self.load_database()
        papers = self.get_papers_from_dataframe(df)
        
        # 查找论文
        for paper in papers:
            if paper.paper_id == paper_id:
                # 应用更新
                for key, value in updates.items():
                    if hasattr(paper, key):
                        setattr(paper, key, value)
                
                # 保存更新
                df = self.get_dataframe_from_papers(papers)
                password = self.get_password()
                return self.save_database(df, password)
        
        return False
    
    def delete_paper(self, paper_id: str) -> bool:
        """删除单篇论文"""
        df = self.load_database()
        papers = self.get_papers_from_dataframe(df)
        
        # 过滤掉要删除的论文
        filtered_papers = [p for p in papers if p.paper_id != paper_id]
        
        if len(filtered_papers) < len(papers):
            # 有论文被删除
            df = self.get_dataframe_from_papers(filtered_papers)
            password = self.get_password()
            return self.save_database(df, password)
        
        return False