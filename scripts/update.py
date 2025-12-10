"""
项目入口2：将更新文件（excel和json）的内容更新到核心excel
"""
import os
import sys
from pathlib import Path
from typing import Dict, List
from dataclasses import asdict

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from scripts.core.config_loader import config_loader
from scripts.core.database_manager import DatabaseManager
from scripts.core.database_model import Paper
from scripts.ai_generator import AIGenerator
from scripts.utils import read_json_file, read_excel_file, get_current_timestamp, write_json_file
import pandas as pd


class UpdateProcessor:
    """更新处理器"""
    
    def __init__(self):
        self.config = config_loader
        self.settings = config_loader.settings
        self.db_manager = DatabaseManager()
        self.ai_generator = AIGenerator()
        
        self.update_excel_path = self.settings['paths']['update_excel']
        self.update_json_path = self.settings['paths']['update_json']
        self.default_contributor = self.settings['database']['default_contributor']
    
    def process_updates(self, conflict_resolution: str = 'mark') -> Dict:
        """
        处理更新文件
        
        参数:
            conflict_resolution: 冲突解决策略 ('mark', 'skip', 'replace')
        
        返回:
            处理结果字典
        """
        result = {
            'success': False,
            'new_papers': 0,
            'updated_papers': 0,
            'conflicts': [],
            'errors': [],
            'ai_generated': 0
        }
        
        # 检查更新文件是否存在
        excel_exists = os.path.exists(self.update_excel_path)
        json_exists = os.path.exists(self.update_json_path)
        
        if not excel_exists and not json_exists:
            result['errors'].append("没有找到更新文件")
            return result
        
        # 从两个文件加载更新
        new_papers = []
        
        if excel_exists:
            excel_papers = self._load_papers_from_excel()
            new_papers.extend(excel_papers)
            print(f"从Excel文件加载了 {len(excel_papers)} 篇论文")
        
        if json_exists:
            json_papers = self._load_papers_from_json()
            new_papers.extend(json_papers)
            print(f"从JSON文件加载了 {len(json_papers)} 篇论文")
        
        if not new_papers:
            result['errors'].append("更新文件中没有有效的论文数据")
            return result
        
        # 去重（基于DOI和标题）
        unique_papers = self._deduplicate_papers(new_papers)
        print(f"去重后剩余 {len(unique_papers)} 篇论文")
        
        # 添加提交时间
        for paper in unique_papers:
            if not paper.submission_time:
                paper.submission_time = get_current_timestamp()
            
            # 设置默认贡献者
            if not paper.contributor:
                paper.contributor = self.default_contributor
        
        # 使用AI生成缺失内容
        if self.ai_generator.is_available():
            print("使用AI生成缺失内容...")
            unique_papers = self.ai_generator.batch_enhance_papers(unique_papers)
            result['ai_generated'] = len([p for p in unique_papers if any(
                getattr(p, field, "").startswith("[AI generated]") 
                for field in ['title_translation', 'analogy_summary', 
                            'summary_motivation', 'summary_innovation',
                            'summary_method', 'summary_conclusion', 
                            'summary_limitation']
            )])
            print(f"AI生成了 {result['ai_generated']} 篇论文的内容")
        
        # 验证论文数据
        valid_papers = []
        for paper in unique_papers:
            errors = paper.is_valid(self.config)
            if errors:
                error_msg = f"论文验证失败: {paper.title[:50]}... - {', '.join(errors[:3])}"
                result['errors'].append(error_msg)
                print(f"错误: {error_msg}")
            else:
                valid_papers.append(paper)
        
        if not valid_papers:
            result['errors'].append("没有有效的论文数据可以更新")
            return result
        
        print(f"准备更新 {len(valid_papers)} 篇有效论文到数据库")
        
        # 添加到数据库
        added_papers, conflict_papers = self.db_manager.add_papers(
            valid_papers, 
            conflict_resolution
        )
        
        # 更新结果
        result['success'] = True
        result['new_papers'] = len(added_papers)
        # Normalize conflicts into a list of dicts; db_manager may return either
        # a list of (new_paper, existing_paper) tuples or a list of Paper objects.
        conflicts_list = []
        for item in conflict_papers:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                new_paper, existing_paper = item
            else:
                new_paper = item
                existing_paper = None
            conflicts_list.append({
                'new': asdict(new_paper) if new_paper else None,
                'existing': asdict(existing_paper) if existing_paper else None
            })
        result['conflicts'] = conflicts_list
        
        # 清空更新文件（如果更新成功）
        if added_papers and not conflict_papers:
            self._clear_update_files()
            print("更新文件已清空")
        
        return result
    
    def _load_papers_from_excel(self) -> List[Paper]:
        """从Excel文件加载论文"""
        df = read_excel_file(self.update_excel_path)
        if df is None or df.empty:
            return []
        
        papers = []
        
        for _, row in df.iterrows():
            paper_data = {}
            
            # 将Excel行转换为Paper对象
            for tag in self.config.get_active_tags():
                column_name = tag['table_name']
                if column_name in row:
                    value = row[column_name]
                    
                    # 处理NaN值
                    if pd.isna(value):
                        value = ""
                    
                    paper_data[tag['variable']] = str(value).strip()
            
            # 创建Paper对象
            paper = Paper.from_dict(paper_data)
            papers.append(paper)
        
        return papers
    
    def _load_papers_from_json(self) -> List[Paper]:
        """从JSON文件加载论文"""
        data = read_json_file(self.update_json_path)
        if not data:
            return []
        
        papers = []
        
        # JSON格式可能是一个论文列表
        if isinstance(data, list):
            for paper_data in data:
                paper = Paper.from_dict(paper_data)
                papers.append(paper)
        elif isinstance(data, dict):
            # 或者是一个包含论文列表的对象
            if 'papers' in data and isinstance(data['papers'], list):
                for paper_data in data['papers']:
                    paper = Paper.from_dict(paper_data)
                    papers.append(paper)
            else:
                # 或者直接是一个论文对象
                paper = Paper.from_dict(data)
                papers.append(paper)
        
        return papers
    
    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """去重论文列表（基于DOI和标题）"""
        unique_papers = []
        seen_keys = set()
        
        for paper in papers:
            key = paper.get_key()
            if key and key not in seen_keys:
                seen_keys.add(key)
                unique_papers.append(paper)
        
        return unique_papers
    
    def _clear_update_files(self):
        """清空更新文件"""
        # 清空JSON文件
        if os.path.exists(self.update_json_path):
            write_json_file(self.update_json_path, {})
        
        # 清空Excel文件（创建空的DataFrame）
        if os.path.exists(self.update_excel_path):
            active_tags = self.config.get_active_tags()
            active_tags.sort(key=lambda x: x['order'])
            columns = [tag['table_name'] for tag in active_tags]
            
            df = pd.DataFrame(columns=columns)
            df.to_excel(self.update_excel_path, index=False)
    
    def send_notification_email(self, result: Dict):
        """发送通知邮件（模拟）"""
        # 在实际部署中，这里会发送邮件
        # 现在只打印通知信息
        
        print("\n" + "="*50)
        print("更新处理完成")
        print("="*50)
        
        if result['success']:
            print(f"✓ 成功添加 {result['new_papers']} 篇新论文")
            
            if result['ai_generated'] > 0:
                print(f"✓ AI生成了 {result['ai_generated']} 篇论文的内容")
            
            if result['conflicts']:
                print(f"⚠ 发现 {len(result['conflicts'])} 处冲突需要手动处理")
                for i, conflict in enumerate(result['conflicts'], 1):
                    new_title = conflict['new'].get('title', '未知标题')[:50]
                    print(f"  {i}. 冲突论文: {new_title}...")
            
            if result['errors']:
                print(f"⚠ 处理过程中出现 {len(result['errors'])} 个错误")
                for error in result['errors'][:3]:  # 只显示前3个错误
                    print(f"  - {error}")
        else:
            print("✗ 更新失败")
            for error in result['errors']:
                print(f"  - {error}")


def main():
    """主函数"""
    print("开始处理更新文件...")
    
    processor = UpdateProcessor()
    
    # 检查是否有更新
    excel_exists = os.path.exists(processor.update_excel_path)
    json_exists = os.path.exists(processor.update_json_path)
    
    if not excel_exists and not json_exists:
        print("没有找到更新文件")
        return
    
    # 处理更新
    result = processor.process_updates(conflict_resolution='mark')
    
    # 发送通知
    processor.send_notification_email(result)
    
    # 如果更新成功，重新生成README
    if result['success'] and result['new_papers'] > 0:
        print("\n重新生成README...")
        try:
            from convert import ReadmeGenerator
            generator = ReadmeGenerator()
            success = generator.update_readme_file()
            
            if success:
                print("✓ README更新成功")
            else:
                print("✗ README更新失败")
        except Exception as e:
            print(f"重新生成README时出错: {e}")


if __name__ == "__main__":
    main()