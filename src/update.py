"""
项目入口2：将更新文件（CSV/JSON）的内容更新到核心数据库（CSV）
"""
import os
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config_loader import get_config_instance
from src.core.database_manager import DatabaseManager
from src.core.database_model import Paper, is_same_identity
from src.ai_generator import AIGenerator
from src.utils import get_current_timestamp, backup_file
from src.core.update_file_utils import get_update_file_utils

class UpdateProcessor:
    """更新处理器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.db_manager = DatabaseManager()
        self.ai_generator = AIGenerator()
        self.update_utils = get_update_file_utils()
        
        # 获取所有可能的更新文件路径
        self.update_files = []
        paths = self.settings['paths']
        
        # 标准更新文件
        for k in ['update_csv', 'update_json', 'my_update_csv', 'my_update_json']:
            if paths.get(k):
                self.update_files.append(paths[k])
                
        # 额外更新文件
        extra = paths.get('extra_update_files_list', [])
        self.update_files.extend(extra)

        # 其他配置
        self.default_contributor = self.settings['database']['default_contributor']
        self.ai_generate_mark = self.settings['ai'].get('ai_generate_mark', '[AI generated]')
        
        # 兼容配置项为 bool 或 str
        remove_val = self.settings['database'].get('remove_added_paper_in_template', 'false')
        self.is_remove_added_paper = str(remove_val).lower() == 'true'

        # 这里的 enable_ai_generation 控制自动流程
        self.enable_ai = str(self.settings['ai'].get('enable_ai_generation', 'true')).lower() == 'true'
    
    def process_updates(self, conflict_resolution: str = 'mark') -> Dict:
        """
        处理更新文件
        conflict_resolution: 'mark', 'skip', 'replace'
        """
        result = {
            'success': False,
            'new_papers': 0,
            'updated_papers': 0,
            'conflicts': [],
            'errors': [],
            'ai_generated': 0,
            'invalid_msg': []
        }
        
        # 过滤有效文件
        valid_files = [f for f in self.update_files if f and os.path.exists(f)]
        
        if not valid_files:
            result['errors'].append("没有找到任何有效的更新文件")
            return result

        print(f"检测到 {len(valid_files)} 个更新文件，开始逐一处理...")

        total_added_papers = []
        total_conflict_papers = []
        
        for file_path in valid_files:
            print(f"\n📝--- 处理文件: {os.path.basename(file_path)} ---")
            
            # 1. 加载论文
            try:
                current_papers = self.update_utils.read_data(file_path)
            except Exception as e:
                err = f"加载文件 {file_path} 失败: {e}"
                result['errors'].append(err)
                print(err)
                continue

            if not current_papers:
                print(f"⚠ 文件中没有论文数据")
                continue

            print(f"读取到 {len(current_papers)} 篇论文")

            # 2. 本地去重 (文件内去重)
            unique_papers = self._deduplicate_papers(current_papers)
            if len(unique_papers) < len(current_papers):
                print(f"去重后剩余 {len(unique_papers)} 篇论文")

            # 3. 数据预处理
            valid_papers = []
            for paper in unique_papers:


                # 时间戳
                if not paper.submission_time:
                    paper.submission_time = get_current_timestamp()
                
                # 贡献者
                if not paper.contributor:
                    paper.contributor = self.default_contributor
                
                # 验证
                valid, errors, _ = paper.validate_paper_fields(
                    self.config, check_required=True, check_non_empty=True, no_normalize=False
                )
                
                if not valid:
                    error_msg = f"[{os.path.basename(file_path)}] 验证失败: {paper.title[:30]}... - {', '.join(errors[:2])}"
                    result['errors'].append(error_msg)
                    # 即使验证失败，如果是配置为不跳过，或者为了保留数据，这里我们先不添加
                    # 策略：只有验证通过的才自动入库
                    print(f"警告: {error_msg} (已跳过入库)")
                else:
                    valid_papers.append(paper)
            
            if not valid_papers:
                continue

            # 4. AI 生成 (如果启用)
            if self.enable_ai and self.ai_generator.is_available():
                print("使用AI生成缺失内容...")
                try:
                    enhanced_papers, is_enhanced = self.ai_generator.batch_enhance_papers(valid_papers)
                    valid_papers = enhanced_papers # 更新引用
                    
                    if is_enhanced:
                        # 回写到当前更新文件
                        try:
                            self.update_utils.persist_ai_generated_to_update_files(valid_papers, file_path)
                            print(f"AI内容已回写至 {os.path.basename(file_path)}")
                        except Exception as e:
                            result['errors'].append(f"回写AI内容失败: {e}")
                        
                        # 统计
                        ai_count = 0
                        for p in valid_papers:
                            # 简单检查是否有 AI 标记
                            if self.ai_generate_mark in str(p.to_dict()): 
                                ai_count += 1
                        result['ai_generated'] += ai_count
                except Exception as e:
                    result['errors'].append(f"AI生成失败: {e}")

            # 5. 添加到数据库
            print(f"正在更新 {len(valid_papers)} 篇论文到数据库...")
            try:
                added, conflicts, inv_msgs = self.db_manager.add_papers(
                    valid_papers, 
                    conflict_resolution
                )
                total_added_papers.extend(added)
                total_conflict_papers.extend(conflicts)
                result['invalid_msg'].extend(inv_msgs)
                result['new_papers'] += len(added)
            except Exception as e:
                err = f"数据库操作失败 ({file_path}): {e}"
                result['errors'].append(err)
                print(f"错误: {err}")
                continue

            # 6. 从更新文件移除已处理论文
            if self.is_remove_added_paper:
                try:
                    # 从 valid_papers 中找出那些已经成功 add 或 标记为 conflict 的
                    processed = added + conflicts
                    if processed:
                        # 重新读取当前文件（防止覆盖期间的变动），过滤掉 processed
                        current_file_papers = self.update_utils.read_data(file_path)
                        remaining = []
                        
                        processed_keys = {p.get_key() for p in processed}
                        
                        for p in current_file_papers:
                            if p.get_key() not in processed_keys:
                                remaining.append(p)
                        
                        if len(remaining) < len(current_file_papers):
                            # 备份
                            backup_file(file_path, self.settings['paths']['backup_dir'])
                            # 写入
                            self.update_utils.write_data(file_path, remaining)
                            print(f"🗑️ 已从 {os.path.basename(file_path)} 移除 {len(current_file_papers)-len(remaining)} 篇已处理论文")
                            
                except Exception as e:
                    result['errors'].append(f"清理文件 {file_path} 失败: {e}")

        # 整理冲突信息
        conflicts_list = []
        # 注意: add_papers 返回的 conflicts 已经是 Paper 对象列表（已标记）
        # 这里为了 result 显示，我们需要构造一下 info
        for p in total_conflict_papers:
            conflicts_list.append({
                'new': p.to_dict(),
                'existing': None # 简化，不再查找旧对象，因为 new_p 已经 merge 进去了
            })
        result['conflicts'] = conflicts_list
        result['invalid_msg'] = list(set(result['invalid_msg']))

        if result['new_papers'] > 0 or result['conflicts'] or result['ai_generated'] > 0:
            result['success'] = True

        return result
    
    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """去重论文列表"""
        unique = []
        seen_keys = set()
        for p in papers:
            k = p.get_key()
            # 如果 DOI 和 Title 都为空，跳过
            if not k[0] and not k[1]:
                continue
            if k in seen_keys:
                continue
            seen_keys.add(k)
            unique.append(p)
        return unique
    
    def print_result(self, result: Dict):
        """打印结果"""
        print("\n" + "="*50)
        print("更新处理完成")
        print("="*50)
        
        if result['success']:
            print(f"✓ 成功添加 {result['new_papers']} 篇新论文")
            if result['ai_generated'] > 0:
                print(f"✓ AI生成了 {result['ai_generated']} 处内容")
            if result['conflicts']:
                print(f"⚠ 发现 {len(result['conflicts'])} 处冲突，已标记并添加，请在 GUI 中搜索 '{self.settings['database']['conflict_marker']}' 处理")
        else:
            print("- 没有产生有效更新")
            
        if result['errors']:
            print("\n❌ 错误:")
            for e in result['errors']: print(f"  - {e}")
            
        if result['invalid_msg']:
            print(f"\n⚠ 数据库格式警告 ({len(result['invalid_msg'])}):")
            for m in result['invalid_msg'][:5]: print(f"  - {m}")
            if len(result['invalid_msg']) > 5: print("  ...")

def main():
    print("开始处理更新...")
    processor = UpdateProcessor()
    result = processor.process_updates(conflict_resolution='mark')
    processor.print_result(result)
    
    if result['success']:
        print("\n正在重新生成 README...")
        try:
            from src.convert import ReadmeGenerator
            gen = ReadmeGenerator()
            if gen.update_readme_file():
                print("✓ README 更新成功")
            else:
                print("❌ README 更新失败")
        except Exception as e:
            print(f"❌ README 生成出错: {e}")

if __name__ == "__main__":
    main()