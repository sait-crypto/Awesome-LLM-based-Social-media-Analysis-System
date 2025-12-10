"""
项目入口2：将更新文件（excel和json）的内容更新到核心excel
!!!!!注意：运行该脚本前请关闭核心excel文件，以免写入冲突，它不会提醒的，只会默默处理完并尝试写入!!!!!
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import asdict

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

from scripts.core.config_loader import get_config_instance
from scripts.core.database_manager import DatabaseManager
from scripts.core.database_model import Paper, is_duplicate_paper
from scripts.ai_generator import AIGenerator
from scripts.utils import read_json_file, read_excel_file, get_current_timestamp, write_json_file, write_excel_file, normalize_dataframe_columns, normalize_json_papers
import pandas as pd


class UpdateProcessor:
    """更新处理器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
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
                excel_papers = self._load_papers_from_excel()
                new_papers.extend(excel_papers)
                print(f"Excel文件中有 {len(excel_papers)} 个论文条目")
            except Exception as e:
                error_msg = f"加载Excel文件失败: {e}"
                result['errors'].append(error_msg)
                print(f"错误: {error_msg}")
        
        if json_exists:
            try:
                json_papers = self._load_papers_from_json()
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
                    self._persist_ai_generated_to_update_files(valid_papers)
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
        
        # 从更新文件中移除已成功处理的论文
        try:
            self._remove_processed_papers(added_papers)
            print(f"已从更新文件中移除 {len(added_papers)} 篇已处理论文")
        except Exception as e:
            err = f"清理更新文件失败: {e}"
            result['errors'].append(err)
            print(f"警告: {err}")
        
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
            try:
                paper = Paper.from_dict(paper_data)
                papers.append(paper)
            except Exception as e:
                print(f"警告: 解析Excel行失败: {e}")
                continue
        
        return papers
    
    def _load_papers_from_json(self) -> List[Paper]:
        """从JSON文件加载论文"""
        data = read_json_file(self.update_json_path)
        if not data:
            return []
        
        papers = []
        
        # JSON格式可能是一个论文列表
        def _normalize_dict_to_strings(raw: Dict) -> Dict:
            normalized = {}
            for tag in self.config.get_active_tags():
                var = tag['variable']
                val = raw.get(var, "")
                
                # 处理空值
                if val is None or (isinstance(val, (str, list, dict)) and not val):
                    normalized[var] = ""
                    continue
                
                # 根据类型安全转换
                t = tag.get('type', 'string')
                try:
                    if t == 'bool':
                        if isinstance(val, bool):
                            normalized[var] = val
                        elif isinstance(val, str):
                            normalized[var] = val.lower() in ('true', 'yes', '1', 'y', '是')
                        elif isinstance(val, (int, float)):
                            normalized[var] = bool(val)
                        else:
                            normalized[var] = False
                    elif t == 'int':
                        if isinstance(val, (int, float)):
                            normalized[var] = int(val)
                        elif isinstance(val, str) and val.strip():
                            normalized[var] = int(float(val.strip()))
                        else:
                            normalized[var] = 0
                    elif t == 'float':
                        if isinstance(val, (int, float)):
                            normalized[var] = float(val)
                        elif isinstance(val, str) and val.strip():
                            normalized[var] = float(val.strip())
                        else:
                            normalized[var] = 0.0
                    else:  # string类型
                        if isinstance(val, (list, dict)):
                            # 对于复杂结构，转换为JSON字符串
                            normalized[var] = json.dumps(val, ensure_ascii=False)
                        else:
                            normalized[var] = str(val).strip()
                except (ValueError, TypeError, json.JSONDecodeError) as e:
                    print(f"警告: 字段 {var} 值转换失败: {val} -> {e}")
                    normalized[var] = ""
            
            return normalized
        
        if isinstance(data, list):
            for paper_data in data:
                try:
                    norm = _normalize_dict_to_strings(paper_data)
                    paper = Paper.from_dict(norm)
                    papers.append(paper)
                except Exception as e:
                    print(f"警告: 解析JSON条目失败: {e}")
                    continue
        elif isinstance(data, dict):
            # 或者是一个包含论文列表的对象
            if 'papers' in data and isinstance(data['papers'], list):
                for paper_data in data['papers']:
                    try:
                        norm = _normalize_dict_to_strings(paper_data)
                        paper = Paper.from_dict(norm)
                        papers.append(paper)
                    except Exception as e:
                        print(f"警告: 解析JSON论文条目失败: {e}")
                        continue
            else:
                # 或者直接是一个论文对象
                try:
                    norm = _normalize_dict_to_strings(data)
                    paper = Paper.from_dict(norm)
                    papers.append(paper)
                except Exception as e:
                    print(f"警告: 解析JSON对象失败: {e}")
        
        return papers
    
    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """去重论文列表（基于DOI和标题）"""
        unique_papers = []
        
        for paper in papers:
            if is_duplicate_paper(unique_papers, paper):
                continue
            unique_papers.append(paper)

        return unique_papers
    
    def _remove_processed_papers(self, processed_papers: List[Paper]):
        """从更新文件中移除已处理的论文"""
        # 1. 处理JSON文件
        if os.path.exists(self.update_json_path):
            try:
                self._remove_papers_from_json(processed_papers)
            except Exception as e:
                raise Exception(f"从JSON文件移除论文失败: {e}")
        
        # 2. 处理Excel文件
        if os.path.exists(self.update_excel_path):
            try:
                self._remove_papers_from_excel(processed_papers)
            except Exception as e:
                raise Exception(f"从Excel文件移除论文失败: {e}")
    
    def _remove_papers_from_json(self, processed_papers: List[Paper]):
        """从JSON文件中移除已处理的论文"""
        data = read_json_file(self.update_json_path)
        if not data:
            return
        
        # 收集已处理论文的DOI和标题用于匹配
        processed_keys = []
        for paper in processed_papers:
            key = paper.get_key()
            if key:
                processed_keys.append(key)
        
        # 根据数据结构类型进行过滤
        if isinstance(data, list):
            # 直接是论文列表
            filtered_data = []
            for item in data:
                # 从item中提取DOI和标题构建key
                doi = item.get('doi', '').strip()
                title = item.get('title', '').strip()
                item_key = f"{doi.lower()}|{title.lower()}" if doi else title.lower()
                
                # 如果不在已处理列表中，保留
                if item_key not in processed_keys:
                    filtered_data.append(item)
            
            # 如果过滤后还有数据，写回文件，否则清空
            if filtered_data:
                # 保持原始列表结构
                write_json_file(self.update_json_path, filtered_data)
            else:
                write_json_file(self.update_json_path, {})
        
        elif isinstance(data, dict) and 'papers' in data:
            # 是包含papers字段的字典
            if isinstance(data['papers'], list):
                filtered_papers = []
                for item in data['papers']:
                    doi = item.get('doi', '').strip()
                    title = item.get('title', '').strip()
                    item_key = f"{doi.lower()}|{title.lower()}" if doi else title.lower()
                    
                    if item_key not in processed_keys:
                        filtered_papers.append(item)
                
                data['papers'] = filtered_papers
                write_json_file(self.update_json_path, data)
    
    def _remove_papers_from_excel(self, processed_papers: List[Paper]):
        """从Excel文件中移除已处理的论文"""
        df = read_excel_file(self.update_excel_path)
        if df is None or df.empty:
            return
        
        # 收集已处理论文的DOI和标题用于匹配
        processed_keys = []
        for paper in processed_papers:
            key = paper.get_key()
            if key:
                processed_keys.append(key)
        
        # 过滤DataFrame
        rows_to_keep = []
        for idx, row in df.iterrows():
            # 从行中提取DOI和标题
            doi = str(row.get('doi', '')).strip() if 'doi' in row and pd.notna(row.get('doi')) else ''
            title = str(row.get('title', '')).strip() if 'title' in row and pd.notna(row.get('title')) else ''
            row_key = f"{doi.lower()}|{title.lower()}" if doi else title.lower()
            
            # 如果不在已处理列表中，保留
            if row_key not in processed_keys:
                rows_to_keep.append(row)
        
        # 创建新的DataFrame
        if rows_to_keep:
            new_df = pd.DataFrame(rows_to_keep)
            # 确保列的顺序和类型正确
            new_df = normalize_dataframe_columns(new_df, self.config)
            write_excel_file(self.update_excel_path, new_df)
        else:
            # 如果所有行都被处理，创建空DataFrame
            active_tags = self.config.get_active_tags()
            active_tags.sort(key=lambda x: x['order'])
            columns = [tag['table_name'] for tag in active_tags]
            empty_df = pd.DataFrame(columns=columns)
            write_excel_file(self.update_excel_path, empty_df)
    
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


    def _persist_ai_generated_to_update_files(self, papers: List[Paper]):
        """
        把 AI 生成的字段原样写回到更新文件（update_json 和 update_excel）。
        匹配策略：优先按 DOI 匹配，若 DOI 不存在则按 title（忽略大小写、首尾空白）匹配。
        如果匹配不上，说明数据有问题，提醒用户排查。
        """
        if not papers:
            return

        # ---------- JSON 处理 ----------
        json_matched = 0
        json_unmatched = []
        try:
            json_data = read_json_file(self.update_json_path) or {}
            
            # 记录原始数据结构类型
            original_is_dict_with_papers = isinstance(json_data, dict) and 'papers' in json_data
            
            # 规范读取到的结构为 list of dicts（variable keyed）
            if original_is_dict_with_papers and isinstance(json_data['papers'], list):
                existing_list = json_data['papers']
            elif isinstance(json_data, list):
                existing_list = json_data
            else:
                existing_list = []

            # 先将 existing_list 规范为 variable-keyed 列表
            existing_norm = normalize_json_papers(existing_list, self.config)

            # 把 incoming papers 转为 variable-keyed dict 列表
            incoming = [p.to_dict() for p in papers]
            incoming_norm = normalize_json_papers(incoming, self.config)

            # 按 DOI 或 title 匹配并合并 AI 字段（variable keys）
            for inc in incoming_norm:
                doi = (inc.get('doi') or "").strip()
                title = (inc.get('title') or "").strip()
                matched = None
                
                for ex in existing_norm:
                    ex_doi = (ex.get('doi') or "").strip()
                    ex_title = (ex.get('title') or "").strip()
                    
                    # 优先按DOI匹配
                    if doi and ex_doi and ex_doi.lower() == doi.lower():
                        matched = ex
                        break
                    # 其次按标题匹配
                    if not matched and title and ex_title and ex_title.lower() == title.lower():
                        matched = ex
                        break
                
                if matched is None:
                    json_unmatched.append(f"标题: {title[:50]}... (DOI: {doi[:20]}...)")
                else:
                    json_matched += 1
                    # 覆盖 AI 相关字段（保留其他原字段）
                    for f in ['title_translation','analogy_summary',
                              'summary_motivation','summary_innovation',
                              'summary_method','summary_conclusion','summary_limitation']:
                        val = inc.get(f, "")
                        if val is not None and val != "":
                            matched[f] = val

            # 写回 JSON（保持原有容器结构）
            if original_is_dict_with_papers:
                final = dict(json_data)
                final['papers'] = existing_norm
            else:
                # 保持原始列表结构
                final = existing_norm
            
            write_json_file(self.update_json_path, final)
            
        except Exception as e:
            raise RuntimeError(f"写入更新JSON失败: {e}")

        # ---------- Excel 处理 ----------
        excel_matched = 0
        excel_unmatched = []
        try:
            df = read_excel_file(self.update_excel_path)
            if df is None or df.empty:
                # 如果没有数据，跳过Excel处理
                print("警告: Excel文件为空或不存在，跳过AI内容回写")
                if json_unmatched:
                    print(f"JSON匹配失败 {len(json_unmatched)} 条，请检查数据一致性")
                return

            # 规范数据框列
            df = normalize_dataframe_columns(df, self.config)

            # 把 incoming papers 转为 variable-keyed dict 列表并映射到 table_name 列
            incoming = [p.to_dict() for p in papers]
            incoming_norm = normalize_json_papers(incoming, self.config)

            for inc in incoming_norm:
                doi = (inc.get('doi') or "").strip()
                title = (inc.get('title') or "").strip()
                row_idx = None

                # 优先按DOI匹配
                if 'doi' in df.columns and doi:
                    mask = df['doi'].astype(str).str.strip().str.lower() == doi.lower()
                    if mask.any():
                        row_idx = df[mask].index[0]
                
                # 其次按标题匹配
                if row_idx is None and 'title' in df.columns and title:
                    mask = df['title'].astype(str).str.strip().str.lower() == title.lower()
                    if mask.any():
                        row_idx = df[mask].index[0]

                if row_idx is None:
                    excel_unmatched.append(f"标题: {title[:50]}... (DOI: {doi[:20]}...)")
                else:
                    excel_matched += 1
                    # 将 variable-keyed inc 映射回 table_name 并写入
                    for tag in self.config.get_active_tags():
                        var = tag['variable']
                        col = tag['table_name']
                        if var in inc and inc[var] not in ("", None):
                            df.at[row_idx, col] = inc[var]

            # 在最终写入前再次规范列
            df = normalize_dataframe_columns(df, self.config)

            # 写回 Excel
            write_excel_file(self.update_excel_path, df)
            
        except Exception as e:
            raise RuntimeError(f"写入更新Excel失败: {e}")
        
        # 输出匹配统计信息
        print(f"AI内容回写匹配统计:")
        print(f"  JSON: 成功匹配 {json_matched}/{len(papers)} 条记录")
        print(f"  Excel: 成功匹配 {excel_matched}/{len(papers)} 条记录")
        
        # 检查不匹配的记录
        if json_unmatched or excel_unmatched:
            print("警告: 以下记录在更新文件中找不到匹配项，请检查数据一致性:")
            
            # 合并并去重不匹配记录
            all_unmatched = set(json_unmatched + excel_unmatched)
            for i, record in enumerate(all_unmatched, 1):
                print(f"  {i}. {record}")
            
            print("建议: 检查DOI和标题是否在更新文件中正确填写")
    
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
    if result['success'] and result['new_papers'] > 0:
        print("\n重新生成README...")
        try:
            from scripts.convert import ReadmeGenerator
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