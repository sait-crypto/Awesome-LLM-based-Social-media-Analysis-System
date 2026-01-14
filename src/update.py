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
        
        # 标准更新文件路径
        self.update_excel_path = self.settings['paths']['update_excel']
        self.update_json_path = self.settings['paths']['update_json']
        self.my_update_excel_path = self.settings['paths']['my_update_excel']
        self.my_update_json_path = self.settings['paths']['my_update_json']
        
        # 额外更新文件列表 (ConfigLoader 已经解析为绝对路径列表)
        self.extra_update_files = self.settings['paths'].get('extra_update_files_list', [])

        #其他配置
        self.default_contributor = self.settings['database']['default_contributor']
        self.ai_generate_mark=self.settings['ai']['ai_generate_mark']

        # 兼容配置项为 bool 或 str 的情况；确保得到布尔值
        remove_val = self.settings['database'].get('remove_added_paper_in_template','false')
        try:
            self.is_remove_added_paper=str(remove_val).lower()=='true'
        except Exception:
            self.is_remove_added_paper=bool(remove_val)
    
    def process_updates(self, conflict_resolution: str = 'mark') -> Dict:
        """
        处理更新文件 (循环处理所有配置的更新源文件)
        
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
        
        # 构建待处理的文件列表 (顺序: 标准 -> My -> Extra)
        files_to_process = []
        
        # 1. 标准更新文件
        files_to_process.append(self.update_excel_path)
        files_to_process.append(self.update_json_path)
        
        # 2. My 更新文件
        files_to_process.append(self.my_update_excel_path)
        files_to_process.append(self.my_update_json_path)
        
        # 3. 额外更新文件
        if self.extra_update_files:
            files_to_process.extend(self.extra_update_files)

        # 过滤不存在的文件
        valid_files = [f for f in files_to_process if f and os.path.exists(f)]
        
        if not valid_files:
            result['errors'].append("没有找到任何有效的更新文件")
            return result

        print(f"检测到 {len(valid_files)} 个更新文件，开始逐一处理...")

        # 循环处理每个文件
        total_added_papers = []
        total_conflict_papers = []

        for file_path in valid_files:
            print(f"\n📝--- 处理文件: {file_path} ---")
            
            # 1. 加载论文
            current_papers = []
            try:
                if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                    current_papers = self.update_utils.load_papers_from_excel(file_path)
                elif file_path.endswith('.json'):
                    current_papers = self.update_utils.load_papers_from_json(file_path)
                else:
                    print(f"警告: 跳过不支持的文件类型: {file_path}")
                    continue
            except Exception as e:
                err = f"加载文件 {file_path} 失败: {e}"
                result['errors'].append(err)
                print(err)
                continue

            if not current_papers:
                print(f"❕文件中没有论文数据")
                continue

            print(f"读取到 {len(current_papers)} 篇论文")

            # 2. 本地去重 (针对当前文件内的重复)
            unique_papers = self._deduplicate_papers(current_papers)
            if len(unique_papers) < len(current_papers):
                print(f"去重后剩余 {len(unique_papers)} 篇论文")

            # 3. 数据预处理 (时间戳、贡献者、验证)
            valid_papers = []
            for paper in unique_papers:
                # 添加提交时间
                if not paper.submission_time:
                    paper.submission_time = get_current_timestamp()
                
                # 设置默认贡献者
                if not paper.contributor:
                    paper.contributor = self.default_contributor
                
                # 验证
                errors = paper.is_valid()
                if errors:
                    error_msg = f"[{os.path.basename(file_path)}] 论文验证失败: {paper.title[:30]}... - {', '.join(errors[:2])}"
                    result['errors'].append(error_msg)
                    print(f"警告: {error_msg}")
                else:
                    valid_papers.append(paper)
            
            if not valid_papers:
                continue

            # 4. AI 生成缺失内容并回写到 *当前文件*
            if self.ai_generator.is_available():
                print("使用AI生成缺失内容...")
                try:
                    valid_papers = self.ai_generator.batch_enhance_papers(valid_papers)
                    
                    # 回写到当前文件
                    try:
                        self.update_utils.persist_ai_generated_to_update_files(valid_papers, file_path)
                    except Exception as e:
                        err = f"回写AI内容到 {file_path} 失败: {e}"
                        print(err)
                        result['errors'].append(err)
                    
                    # 统计
                    ai_count = 0
                    for p in valid_papers:
                        if any(
                            getattr(p, field, "").startswith(self.ai_generate_mark) 
                            for field in ['title_translation', 'analogy_summary', 
                                        'summary_motivation', 'summary_innovation',
                                        'summary_method', 'summary_conclusion', 
                                        'summary_limitation']
                        ):
                            ai_count += 1
                    result['ai_generated'] += ai_count
                except Exception as e:
                    err = f"AI生成内容失败 ({file_path}): {e}"
                    result['errors'].append(err)
                    print(f"错误: {err}")

            # 5. 添加到数据库
            print(f"正在更新 {len(valid_papers)} 篇论文到数据库...")
            try:
                added, conflicts = self.db_manager.add_papers(
                    valid_papers, 
                    conflict_resolution_strategy
                )
                total_added_papers.extend(added)
                total_conflict_papers.extend(conflicts)
                result['new_papers'] += len(added)
            except Exception as e:
                error_msg = f"数据库操作失败 ({file_path}): {e}"
                result['errors'].append(error_msg)
                print(f"错误: {error_msg}")
                continue # 如果数据库写入失败，不进行后续的清理操作

            # 6. 从 *当前文件* 移除已处理的论文
            if self.is_remove_added_paper==True:
                try:
                    self._remove_processed_papers(added, file_path)
                    print(f"🗑️ 已从 {os.path.basename(file_path)} 移除 {len(added)} 篇已处理论文")
                    
                    # 如果是Excel，确保格式规范化 (修复表头样式)
                    if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                        try:
                            self.update_utils.ensure_update_file_format(file_path)
                        except Exception as e:
                            print(f"警告: 规范化Excel格式失败: {e}")
                            
                except Exception as e:
                    err = f"清理更新文件 {file_path} 失败: {e}"
                    result['errors'].append(err)
                    print(f"警告: {err}")

        # 循环结束，整理最终结果
        if result['new_papers'] > 0 or result['updated_papers'] > 0 or result['ai_generated'] > 0:
            result['success'] = True
        elif not result['errors']:
             # 没有错误，但也没添加任何东西 (可能是文件为空)
             pass
        
        # 整理冲突信息
        conflicts_list = []
        for item in total_conflict_papers:
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

        return result
    
    
    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """去重论文列表（基于所有非系统字段）"""
        unique_papers = []
        
        for paper in papers:
            if is_duplicate_paper(unique_papers, paper,complete_compare=False):
                continue
            unique_papers.append(paper)

        return unique_papers
    
    def _remove_processed_papers(self, processed_papers: List[Paper], file_path: str):
        """从指定的更新文件中移除已处理的论文"""
        if not os.path.exists(file_path):
            return

        # 根据文件类型调用相应方法
        if file_path.endswith('.json'):
            try:
                self.update_utils.remove_papers_from_json(processed_papers, file_path)
            except Exception as e:
                raise Exception(f"从JSON文件移除论文失败: {e}")
        
        elif file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            try:
                self.update_utils.remove_papers_from_excel(processed_papers, file_path)
            except Exception as e:
                raise Exception(f"从Excel文件移除论文失败: {e}")
    
    
    def print_result(self, result: Dict):
        """打印更新结果"""
        
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
            print("✗ 更新操作未产生变更或失败")
            for error in result['errors']:
                print(f"  - {error}")
    
def main():
    """主函数"""
    print("===！！！！注意：运行该脚本前请关闭核心excel文件，以免无法写入！！！！===\n！！！他只会默默处理完并尝试写入！！！\n！！！如若未关闭，请终止进程！！！")
    print("开始处理更新文件...")
    
    processor = UpdateProcessor()
    
    # 处理更新
    result = processor.process_updates(conflict_resolution='mark')
    
    # 发送通知
    processor.print_result(result)
    
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