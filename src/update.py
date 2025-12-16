"""
项目入口2：将更新文件（excel和json）的内容更新到核心excel
!!!!!注意：运行该脚本前请关闭核心excel文件，以免写入冲突，它会默默处理完并尝试写入!!!!!
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import asdict

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from src.convert import ReadmeGenerator
from src.core.config_loader import get_config_instance
from src.core.database_manager import DatabaseManager
from src.core.database_model import Paper, is_duplicate_paper
from src.ai_generator import AIGenerator
from src.utils import  get_current_timestamp
from src.core.update_file_utils import get_update_file_utils
import pandas as pd


class UpdateProcessor:
    """更新处理器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.db_manager = DatabaseManager()
        self.ai_generator = AIGenerator()
        self.update_utils = get_update_file_utils()
        
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
        conflict_resolution_strategy = self.settings['database'].get('conflict_resolution', conflict_resolution)
        
        # 检查更新文件是否存在
        excel_exists = os.path.exists(self.update_excel_path)
        json_exists = os.path.exists(self.update_json_path)
        
        if not excel_exists and not json_exists:
            result['errors'].append("没有找到更新文件")
            return result
        
        # 从两个文件加载更新
        new_papers = []
        
        if excel_exists:
            try:
                excel_papers = self.update_utils.load_papers_from_excel()
                new_papers.extend(excel_papers)
                print(f"Excel文件中有 {len(excel_papers)} 个论文条目")
            except Exception as e:
                error_msg = f"加载Excel文件失败: {e}"
                result['errors'].append(error_msg)
                print(f"错误: {error_msg}")
        
        if json_exists:
            try:
                json_papers = self.update_utils.load_papers_from_json()
                new_papers.extend(json_papers)
                print(f"JSON文件中有 {len(json_papers)} 个论文条目")
            except Exception as e:
                error_msg = f"加载JSON文件失败: {e}"
                result['errors'].append(error_msg)
                print(f"错误: {error_msg}")
        
        if not new_papers:
            if not result['errors']:  # 如果没有错误但也没有论文
                result['errors'].append("更新文件中没有有效的论文数据")
            return result
        
        # 去重
        unique_papers = self._deduplicate_papers(new_papers)
        print(f"去重后剩余 {len(unique_papers)} 篇论文")
        
        # 添加提交时间
        for paper in unique_papers:
            if not paper.submission_time:
                paper.submission_time = get_current_timestamp()
            
            # 设置默认贡献者
            if not paper.contributor:
                paper.contributor = self.default_contributor
        
        # 验证论文数据
        valid_papers = []
        for paper in unique_papers:
            errors = paper.is_valid()
            if errors:
                error_msg = f"论文验证失败: {paper.title[:50]}... - {', '.join(errors[:3])}"
                result['errors'].append(error_msg)
                print(f"警告: {error_msg}")
            else:
                valid_papers.append(paper)
        
        if not valid_papers:
            result['errors'].append("没有有效的论文数据可以更新")
            return result
        
        # 使用AI生成缺失内容
        if self.ai_generator.is_available():
            print("使用AI生成缺失内容...")
            try:
                valid_papers = self.ai_generator.batch_enhance_papers(valid_papers)
                
                # 将AI生成的内容回写到更新文件（JSON & Excel）
                try:
                    self.update_utils.persist_ai_generated_to_update_files(valid_papers)
                    print("已将AI生成内容回写到更新文件")
                except Exception as e:
                    err = f"回写AI生成内容到更新文件失败: {e}"
                    print(err)
                    result['errors'].append(err)
                
                # 统计AI生成的数量
                ai_count = 0
                for p in valid_papers:
                    if any(
                        getattr(p, field, "").startswith("[AI generated]") 
                        for field in ['title_translation', 'analogy_summary', 
                                    'summary_motivation', 'summary_innovation',
                                    'summary_method', 'summary_conclusion', 
                                    'summary_limitation']
                    ):
                        ai_count += 1
                result['ai_generated'] = ai_count
                print(f"AI生成了 {result['ai_generated']} 篇论文的内容")
            except Exception as e:
                err = f"AI生成内容失败: {e}"
                result['errors'].append(err)
                print(f"错误: {err}")

        print(f"准备更新 {len(valid_papers)} 篇有效论文到数据库")
        
        # 添加到数据库
        try:
            added_papers, conflict_papers = self.db_manager.add_papers(
                valid_papers, 
                conflict_resolution_strategy
            )
        except Exception as e:
            error_msg = f"数据库操作失败: {e}"
            result['errors'].append(error_msg)
            print(f"错误: {error_msg}")
            return result
        
        # 更新结果
        result['success'] = True
        result['new_papers'] = len(added_papers)
        
        # Normalize conflicts into a list of dicts
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
        
        # 如果配置中开启相关变量，从更新文件中移除已成功处理的论文
        try:
            self._remove_processed_papers(added_papers)
            print(f"已从更新文件中移除 {len(added_papers)} 篇已处理论文")
        except Exception as e:
            err = f"清理更新文件失败: {e}"
            result['errors'].append(err)
            print(f"警告: {err}")
        
        return result
    
    
    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """去重论文列表（基于所有非系统字段）"""
        unique_papers = []
        
        for paper in papers:
            if is_duplicate_paper(unique_papers, paper,complete_compare=False):
                continue
            unique_papers.append(paper)

        return unique_papers
    
    def _remove_processed_papers(self, processed_papers: List[Paper]):
        """从更新文件中移除已处理的论文"""
        # 1. 处理JSON文件
        if os.path.exists(self.update_json_path):
            try:
                self.update_utils.remove_papers_from_json(processed_papers)
            except Exception as e:
                raise Exception(f"从JSON文件移除论文失败: {e}")
        
        # 2. 处理Excel文件
        if os.path.exists(self.update_excel_path):
            try:
                self.update_utils.remove_papers_from_excel(processed_papers)
            except Exception as e:
                raise Exception(f"从Excel文件移除论文失败: {e}")
    
    
    def send_notification_email(self, result: Dict):
        """发送通知邮件（模拟）"""
        # 在实际部署中，这里会发送邮件，请完善该部分代码
        # 现在只打印通知信息
        
        print("\n" + "="*50)
        print("更新处理完成")
        print("="*50)
        
        if result['success']:
            print(f"✓ 成功添加 {result['new_papers']} 篇新论文")
            
            if result['ai_generated'] > 0:
                print(f"✓ AI生成了 {result['ai_generated']} 篇论文的内容")
            
            if result['conflicts']:
                print(f"⚠ 发现 {len(result['conflicts'])} 处冲突需要手动处理，已添加到数据库，请尽快处理并运行convert.py更新到readme")
                for i, conflict in enumerate(result['conflicts'], 1):
                    new_title = conflict['new'].get('title', '未知标题')[:50] if conflict['new'] else '未知标题'
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
    print("===！！！！注意：运行该脚本前请关闭核心excel文件，以免写入冲突它不会提醒的！！！！===\n！！！只会默默处理完并尝试写入！！！\n！！！如若未关闭，请终止进程！！！")
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
    if result['success']:  #and result['new_papers'] > 0
        print("\n重新生成README...")
        try:
            from src.convert import ReadmeGenerator
            generator = ReadmeGenerator()
            success = generator.update_readme_file()
            
            if success:
                print("✓ README更新成功")
            else:
                print("✗ README更新失败")
        except ImportError as e:
            print(f"⚠ 无法导入ReadmeGenerator模块: {e}")
            print("  请确保convert.py文件存在且ReadmeGenerator类定义正确")
        except Exception as e:
            print(f"⚠ 重新生成README时出错: {e}")


if __name__ == "__main__":
    main()