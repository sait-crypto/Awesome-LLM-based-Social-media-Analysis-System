"""
更新文件工具模块
统一处理模板文件（Excel和JSON）的读取、写入和移除操作
只处理非系统字段
"""
import os
import json
import pandas as pd
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from scripts.core.config_loader import get_config_instance
from scripts.core.database_model import Paper
from scripts.utils import ensure_directory

class UpdateFileUtils:
    """更新文件工具类"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.update_excel_path = self.settings['paths']['update_excel']
        self.update_json_path = self.settings['paths']['update_json']

    def read_json_file(self,filepath: str) -> Optional[Dict]:
        """读取JSON文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取JSON文件失败 {filepath}: {e}")
            return None


    def write_json_file(self,filepath: str, data: Dict, indent: int = 2) -> bool:
        """写入JSON文件"""
        try:
            ensure_directory(os.path.dirname(filepath))
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
            return True
        except Exception as e:
            print(f"写入JSON文件失败 {filepath}: {e}")
            return False


    def read_excel_file(self,filepath: str) -> Optional[pd.DataFrame]:
        """读取Excel文件"""
        try:
            if not os.path.exists(filepath):
                return pd.DataFrame()
            
            df = pd.read_excel(filepath, engine='openpyxl')
            return df
        except Exception as e:
            print(f"读取Excel文件失败 {filepath}: {e}")
            return None


    def write_excel_file(self,filepath: str, df: pd.DataFrame) -> bool:
        """写入Excel文件"""
        try:
            ensure_directory(os.path.dirname(filepath))
            df.to_excel(filepath, index=False, engine='openpyxl')
            return True
        except Exception as e:
            print(f"写入Excel文件失败 {filepath}: {e}")
            return False
    def load_papers_from_excel(self, filepath: str = None) -> List[Paper]:
        """从Excel文件加载论文（只读取非系统字段）"""
        if filepath is None:
            filepath = self.update_excel_path
            
        df = self.read_excel_file(filepath)
        if df is None or df.empty:
            return []
        
        papers = []
        
        # 只获取非系统字段的标签
        non_system_tags = self.get_non_system_tags()
        
        for _, row in df.iterrows():
            paper_data = {}
            
            # 将Excel行转换为Paper对象
            for tag in non_system_tags:
                column_name = tag['table_name']
                
                # 只处理在Excel中出现的列
                if column_name in row:
                    value = row[column_name]
                    
                    # 处理NaN值
                    if pd.isna(value):
                        value = ""
                    
                    paper_data[tag['variable']] = str(value).strip()
            
            # 创建Paper对象（系统字段会使用默认值）
            try:
                paper = Paper.from_dict(paper_data)
                papers.append(paper)
            except Exception as e:
                print(f"警告: 解析Excel行失败: {e}")
                continue
        
        return papers
    
    def load_papers_from_json(self, filepath: str = None) -> List[Paper]:
        """从JSON文件加载论文（只读取非系统字段）"""
        if filepath is None:
            filepath = self.update_json_path
            
        data = self.read_json_file(filepath)
        if not data:
            return []
        
        papers = []
        
        # 只获取非系统字段的标签
        non_system_tags = self.get_non_system_tags()
        
        # JSON格式可能是一个论文列表
        def _normalize_dict_to_strings(raw: Dict) -> Dict:
            normalized = {}
            for tag in non_system_tags:
                var = tag['variable']
                val = raw.get(var, "")
                # 只处理文件中出现的字段
                if var not in raw:
                    # 如果JSON中没有这个字段，跳过（系统字段会使用默认值）
                    continue
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
    
    def remove_papers_from_json(self, processed_papers: List[Paper], filepath: str = None):
        """从JSON文件中移除已处理的论文（只处理非系统字段）"""
        if filepath is None:
            filepath = self.update_json_path
            
        data = self.read_json_file(filepath)
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
                self.write_json_file(filepath, filtered_data)
            else:
                self.write_json_file(filepath, {})
        
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
                self.write_json_file(filepath, data)
    
    def remove_papers_from_excel(self, processed_papers: List[Paper], filepath: str = None):
        """从Excel文件中移除已处理的论文（只处理非系统字段）"""
        if filepath is None:
            filepath = self.update_excel_path
            
        df = self.read_excel_file(filepath)
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
            # 确保列的顺序和类型正确（只使用非系统字段）
            new_df = self.normalize_update_file_columns(new_df)
            self.write_excel_file(filepath, new_df)
        else:
            # 如果所有行都被处理，创建空DataFrame（只包含非系统字段）
            empty_df = self.create_empty_update_file_df()
            self.write_excel_file(filepath, empty_df)
    
    def persist_ai_generated_to_update_files(self, papers: List[Paper]):
        """
        把 AI 生成的字段原样写回到更新文件（update_json 和 update_excel）。
        只写回非系统字段。
        匹配策略：优先按 DOI 匹配，若 DOI 不存在则按 title（忽略大小写、首尾空白）匹配。
        """
        if not papers:
            return

        # 获取AI相关字段（都是非系统字段）
        ai_fields = ['title_translation', 'analogy_summary',
                    'summary_motivation', 'summary_innovation',
                    'summary_method', 'summary_conclusion', 'summary_limitation']
        
        # ---------- JSON 处理 ----------
        self._persist_ai_to_json(papers, ai_fields)
        
        # ---------- Excel 处理 ----------
        self._persist_ai_to_excel(papers, ai_fields)
    
    def _persist_ai_to_json(self, papers: List[Paper], ai_fields: List[str]):
        """将AI生成内容写回JSON文件"""
        try:
            json_data = self.read_json_file(self.update_json_path) or {}
            
            # 记录原始数据结构类型
            original_is_dict_with_papers = isinstance(json_data, dict) and 'papers' in json_data
            
            # 规范读取到的结构为 list of dicts（variable keyed）
            if original_is_dict_with_papers and isinstance(json_data['papers'], list):
                existing_list = json_data['papers']
            elif isinstance(json_data, list):
                existing_list = json_data
            else:
                existing_list = []

            # 把 incoming papers 转为 variable-keyed dict 列表
            incoming = [p.to_dict() for p in papers]
            
            # 按 DOI 或 title 匹配并合并 AI 字段
            for inc in incoming:
                doi = (inc.get('doi') or "").strip()
                title = (inc.get('title') or "").strip()
                matched = None
                
                for ex in existing_list:
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
                
                if matched is not None:
                    # 覆盖 AI 相关字段（保留其他原字段）
                    for field in ai_fields:
                        val = inc.get(field, "")
                        if val is not None and val != "":
                            matched[field] = val

            # 写回 JSON（保持原有容器结构）
            if original_is_dict_with_papers:
                final = dict(json_data)
                final['papers'] = existing_list
            else:
                # 保持原始列表结构
                final = existing_list
            
            self.write_json_file(self.update_json_path, final)
            
        except Exception as e:
            raise RuntimeError(f"写入更新JSON失败: {e}")
    
    def _persist_ai_to_excel(self, papers: List[Paper], ai_fields: List[str]):
        """将AI生成内容写回Excel文件"""
        try:
            df = self.read_excel_file(self.update_excel_path)
            if df is None or df.empty:
                # 如果没有数据，跳过Excel处理
                print("警告: Excel文件为空或不存在，跳过AI内容回写")
                return

            # 规范数据框列（只使用非系统字段）
            df = self.normalize_update_file_columns(df)

            # 把 incoming papers 转为 dict 列表
            incoming = [p.to_dict() for p in papers]

            for inc in incoming:
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

                if row_idx is not None:
                    # 更新AI相关字段
                    for field in ai_fields:
                        if field in inc and inc[field] not in ("", None):
                            # 找到对应的列名
                            for tag in self.get_non_system_tags():
                                if tag['variable'] == field:
                                    df.at[row_idx, tag['table_name']] = inc[field]
                                    break

            # 写回 Excel
            self.write_excel_file(self.update_excel_path, df)
            
        except Exception as e:
            raise RuntimeError(f"写入更新Excel失败: {e}")
    
    def get_non_system_tags(self) -> List[Dict[str, Any]]:
        """获取所有非系统字段标签（system_var=False）"""
        non_system_tags = []
        for tag in self.config.get_active_tags():
            # 从配置中读取system_var字段，默认为False
            if not tag.get('system_var', False):
                non_system_tags.append(tag)
        return non_system_tags
    
    def normalize_update_file_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        确保DataFrame列按照非系统字段重新生成
        """
        # 只使用非系统字段
        non_system_tags = self.get_non_system_tags()
        non_system_tags.sort(key=lambda x: x['order'])
        columns = [tag['table_name'] for tag in non_system_tags]
        
        # 添加缺失列
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        
        # 重新排序和保留需要的列
        df = df.reindex(columns=columns)
        
        # 类型转换
        for tag in non_system_tags:
            col = tag['table_name']
            t = tag.get('type', 'string')
            if col in df.columns:
                if t == 'bool':
                    df[col] = df[col].fillna(False).astype(bool)
                elif t == 'int':
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                else:
                    df[col] = df[col].fillna("").astype(str).str.strip()
        return df
    
    def create_empty_update_file_df(self) -> pd.DataFrame:
        """创建空的更新文件DataFrame（只包含非系统字段）"""
        non_system_tags = self.get_non_system_tags()
        non_system_tags.sort(key=lambda x: x['order'])
        columns = [tag['table_name'] for tag in non_system_tags]
        return pd.DataFrame(columns=columns)
    

    def _regenerate_columns_from_tags(self,config_instance) -> List[str]:
        """根据tag_config生成按order排序的表列名（table_name）列表"""
        active_tags = config_instance.get_active_tags()
        active_tags.sort(key=lambda x: x.get('order', 0))
        return [tag['table_name'] for tag in active_tags]

    #暂不实现，因为需要将旧name保存下来以供映射
    def normalize_category_value(self,raw_val: Any, config_instance) -> str:
        """
        把 category 字段的旧name改为新的name，
        若无法匹配则返回原值的字符串形式（strip 后）。
        """
        return raw_val
        if raw_val is None:
            return ""
        val = str(raw_val).strip()
        if not val:
            return ""
        # 构建映射：旧name -> unique_name, unique_name ->新name
        new_cats = config_instance.get_active_categories()
        old_cats=config_instance.old_cats


    def normalize_dataframe_columns(self,df: pd.DataFrame, config_instance) -> pd.DataFrame:
        """
        确保DataFrame列按照tag_config中active tags重新生成：
        - 添加缺失列（置空）
        - 移除未激活的列
        - 按order排序列顺序
        - 对 category 列内值执行规范化（未实现）
        """
        if df is None:
            df = pd.DataFrame()
        cols = self._regenerate_columns_from_tags(config_instance)
        # 保留现有行数据但只保留激活列
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        # 移除多余列
        to_keep = cols
        df = df.loc[:, [c for c in to_keep if c in df.columns]]
        # reorder
        df = df[cols]
        # # 规范化 category 列值
        # if 'category' in df.columns:
        #     df['category'] = df['category'].apply(lambda v: normalize_category_value(v, config_instance))
        # 将所有非-bool/int 列转为 string（保持原有语义）
        for tag in config_instance.get_active_tags():
            col = tag['table_name']
            t = tag.get('type', 'string')
            if col in df.columns:
                if t == 'bool':
                    df[col] = df[col].fillna(False).astype(bool)
                elif t == 'int':
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                else:
                    df[col] = df[col].fillna("").astype(str).str.strip()
        return df


    def normalize_json_papers(self,raw_papers: List[Dict[str, Any]], config_instance) -> List[Dict[str, Any]]:
        """
        把JSON中的每篇论文都规范化为只包含active tag的变量（使用variable作为键），
        并将类型与category规范化。（未实现）
        """
        normalized_list = []
        active_tags = config_instance.get_active_tags()
        for item in raw_papers:
            out = {}
            for tag in active_tags:
                var = tag['variable']
                table_name = tag['table_name']
                # 支持输入既有 variable 也有 table_name 两种键
                val = item.get(var, item.get(table_name, ""))
                if val is None:
                    val = ""
                t = tag.get('type', 'string')
                if t == 'bool':
                    out[var] = bool(val) if val not in ("", None) else False
                elif t == 'int':
                    try:
                        out[var] = int(val)
                    except Exception:
                        out[var] = 0
                else:
                    out[var] = str(val).strip()
            # 规范化 category 存储为 unique_name
            # if 'category' in out:
            #     out['category'] = normalize_category_value(out.get('category', ""), config_instance)
            normalized_list.append(out)
        return normalized_list


# 创建全局单例
_update_file_utils_instance = None

def get_update_file_utils():
    """获取更新文件工具单例"""
    global _update_file_utils_instance
    if _update_file_utils_instance is None:
        _update_file_utils_instance = UpdateFileUtils()
    return _update_file_utils_instance