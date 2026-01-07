"""
更新文件工具模块
统一处理模板文件（Excel和JSON）的读取、写入和移除操作
只处理非系统字段
提供以下方法：
read_json_file
write_json_file
read_excel_file
write_excel_file
load_papers_from_excel
load_papers_from_json
remove_papers_from_json
remove_papers_from_excel
persist_ai_generated_to_update_files
normalize_update_file_columns
create_empty_update_file_df
normalize_category_value
normalize_dataframe_columns
excel_to_paper
json_to_paper
paper_to_excel
paper_to_json
"""
import os
import json
from typing import List, Dict, Any, Optional,Union,Tuple
from dataclasses import asdict

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper,is_same_identity, is_duplicate_paper
from src.utils import (
    ensure_directory,
)

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


    def read_excel_file(self,filepath: str) :
        """读取Excel文件"""
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return
        try:
            if not os.path.exists(filepath):
                return pd.DataFrame()
            
            df = pd.read_excel(filepath, engine='openpyxl')
            return df
        except Exception as e:
            print(f"读取Excel文件失败 {filepath}: {e}")
            return None


    def write_excel_file(self,filepath: str, df) -> bool:
        """写入Excel文件"""
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return False
        try:
            ensure_directory(os.path.dirname(filepath))
            with pd.ExcelWriter(
                filepath,
                engine='openpyxl'
            ) as writer:
                df.to_excel(writer, index=False, sheet_name='Papers')
                workbook = writer.book
                worksheet = writer.sheets['Papers']
                # 应用格式
                self.apply_excel_formatting(workbook, worksheet, df)
                return True
        except Exception as e:
            print(f"写入Excel文件失败 {filepath}: {e}")
            return False
    def load_papers_from_excel(self, filepath: str = None) -> List[Paper]:
        """从Excel文件加载论文"""

        if filepath is None:
            filepath = self.update_excel_path
            
        df = self.read_excel_file(filepath)
        if df is None or df.empty:
            return []
        
        return self.excel_to_paper(df, only_non_system=True)
    
    def load_papers_from_json(self, filepath: str = None) -> List[Paper]:
        """从JSON文件加载论文"""
        if filepath is None:
            filepath = self.update_json_path
            
        data = self.read_json_file(filepath)
        if not data:
            return []
        
        # 处理不同的JSON结构
        if isinstance(data, dict) and 'papers' in data:
            papers_data = data['papers']
        elif isinstance(data, list):
            papers_data = data
        else:
            papers_data = [data]
        
        return self.json_to_paper(papers_data, only_non_system=True)
    
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
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return
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
        try:
            # ---------- JSON 处理 ----------
            self._persist_ai_to_json(papers, ai_fields)
            
            # ---------- Excel 处理 ----------
            self._persist_ai_to_excel(papers, ai_fields)
            print("已将AI生成内容回写到更新文件")
        except Exception as e:
            err = f"回写AI生成内容到更新文件失败: {e}"
            print(err)
            raise
    
    def _persist_ai_to_json(self, papers: List[Paper], ai_fields: List[str]):
        try:
            
            # 读取现有数据并转换为Paper对象列表
            json_data = self.read_json_file(self.update_json_path) or {}
            
            if 'papers' not in json_data:
                json_data['papers'] = []
            
            existing_papers = self.json_to_paper(json_data['papers'], only_non_system=True)
            
            # 匹配并更新AI字段
            for ai_paper in papers:
                for existing_paper in existing_papers:
                    if is_same_identity(ai_paper, existing_paper):
                        # 更新AI相关字段
                        for field in ai_fields:
                            new_value = getattr(ai_paper, field, "")
                            if new_value:
                                setattr(existing_paper, field, new_value)
                        break
            
            # 转换回JSON格式并保存
            json_data['papers'] = self.paper_to_json(existing_papers)
            self.write_json_file(self.update_json_path, json_data)
        
        except Exception as e:
            raise RuntimeError(f"写入更新JSON失败: {e}")
    
    def _persist_ai_to_excel(self, papers: List[Paper], ai_fields: List[str]):
        try:            
            # 读取现有数据
            df = self.read_excel_file(self.update_excel_path)
            if df is None or df.empty:
                return
            
            # 转换为Paper对象列表
            existing_papers = self.excel_to_paper(df, only_non_system=True)
            
            # 匹配并更新AI字段
            for ai_paper in papers:
                for existing_paper in existing_papers:
                    if is_same_identity(ai_paper, existing_paper):
                        # 更新AI相关字段
                        for field in ai_fields:
                            new_value = getattr(ai_paper, field, "")
                            if new_value:
                                setattr(existing_paper, field, new_value)
                        break
            
            # 转换回DataFrame并保存
            new_df = self.paper_to_excel(existing_papers, only_non_system=True)
            self.write_excel_file(self.update_excel_path, new_df)
            
        except Exception as e:
            raise RuntimeError(f"写入更新Excel失败: {e}")
    

    
    def normalize_update_file_columns(self, df):
        """
        确保DataFrame列按照非系统字段重新生成
        """
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return
        # 只使用非系统字段
        non_system_tags = self.config.get_non_system_tags()
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
    
    def create_empty_update_file_df(self):
        """创建空的更新文件DataFrame（只包含非系统字段）"""
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return
        non_system_tags = self.config.get_non_system_tags()
        non_system_tags.sort(key=lambda x: x['order'])
        columns = [tag['table_name'] for tag in non_system_tags]
        df= pd.DataFrame(columns=columns)
        

        return df
    

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


    def normalize_dataframe_columns(self,df, config_instance) -> Any:
        """
        确保DataFrame列按照tag_config中active tags重新生成：
        - 添加缺失列（置空）
        - 移除未激活的列
        - 按order排序列顺序
        - 对 category 列内值执行规范化（未实现）
        """
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return 
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
    
    #===================数据规范化===========================
    def json_to_paper(self, json_data: Union[Dict, List[Dict]], only_non_system: bool = False) -> List[Paper]:
        """
        数据规范化方法：将JSON数据转换为Paper对象列表
        """
        # 统一处理为列表
        if isinstance(json_data, dict):
            data_list = [json_data]
        else:
            data_list = json_data
        
        # 获取标签配置
        if only_non_system:
            tags = self.config.get_non_system_tags()
        else:
            tags = self.config.get_active_tags()
        
        # 规范化JSON数据
        normalized_list = self.normalize_json_papers(data_list, self.config)
        
        papers = []
        for item in normalized_list:
            try:
                # 转换为Paper对象
                paper_data = self._dict_to_paper_data(item, tags)
                paper = Paper.from_dict(paper_data)
                
                # 验证论文字段
                valid, errors = paper.validate_paper_fields(
                    self.config,
                    check_required=False,  # 更新文件可能不完整
                    check_non_empty=True
                )
                
                if not valid:
                    print(f"警告: 跳过验证失败的论文: {paper.title[:50]}...")
                    continue
                
                papers.append(paper)
            except Exception as e:
                print(f"警告: 解析JSON条目失败: {e}")
                continue
        
        return papers
    
    def excel_to_paper(self, df, only_non_system: bool = False) -> List[Paper]:
        """
        数据规范化方法：将Excel数据转换为Paper对象列表
        """
        try:
            import pandas as pd
        except ImportError:
            print("警告: pandas未安装，无法处理Excel文件")
            return []
        
        # 统一处理为DataFrame
        if isinstance(df, pd.Series):
            df = pd.DataFrame([df])
        
        if df is None or df.empty:
            return []
        
        # 获取标签配置
        if only_non_system:
            tags = self.config.get_non_system_tags()
        else:
            tags = self.config.get_active_tags()
        
        papers = []
        for _, row in df.iterrows():
            try:
                # 转换为Paper对象
                paper_data = self._excel_row_to_paper_data(row, tags)
                paper = Paper.from_dict(paper_data)
                
                # 验证论文字段
                valid, errors = paper.validate_paper_fields(
                    self.config,
                    check_required=False,  # Excel文件可能不完整
                    check_non_empty=True
                )
                
                if not valid:
                    print(f"警告: 跳过验证失败的论文: {paper.title[:50]}...")
                    continue
                
                papers.append(paper)
            except Exception as e:
                print(f"警告: 解析Excel行失败: {e}")
                continue
        
        return papers
    
    def paper_to_json(self, papers: Union[Paper, List[Paper]]) -> Union[Dict, List[Dict]]:
        """
        数据规范化方法：将Paper对象（或列表）转换为JSON可序列化的字典（或字典列表）
        
        Args:
            papers: Paper对象或Paper对象列表
            
        Returns:
            如果是单个Paper返回字典，如果是列表返回字典列表
        """
        # 统一处理为列表
        if isinstance(papers, Paper):
            input_is_single = True
            papers_list = [papers]
        else:
            input_is_single = False
            papers_list = papers
        

        result = []
        for paper in papers_list:
            try:
                paper_dict = self._paper_to_dict(paper)
                result.append(paper_dict)
            except Exception as e:
                print(f"警告: 转换Paper到字典失败: {e}")
                continue
        paper_dict=self.normalize_json_papers(result, self.config)
        # 返回与输入一致的格式
        if input_is_single and result:
            return result[0]
        return result
    
    def paper_to_excel(self, papers: Union[Paper, List[Paper]], only_non_system: bool = False) :
        """
        数据规范化方法：将Paper对象（或列表）转换为Excel DataFrame
        
        Args:
            papers: Paper对象或Paper对象列表
            only_non_system: 是否只包含非系统字段
            
        Returns:
            DataFrame
        """
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return
        # 统一处理为列表
        if isinstance(papers, Paper):
            papers_list = [papers]
        else:
            papers_list = papers
        
        if not papers_list:
            return pd.DataFrame()
        
        # 获取标签配置
        if only_non_system:
            tags = self.config.get_non_system_tags()
        else:
            tags = self.config.get_active_tags()
        
        # 按order排序
        tags.sort(key=lambda x: x['order'])
        
        # 准备数据
        data = []
        for paper in papers_list:
            try:
                # 新增检查：确保paper是Paper实例
                if not isinstance(paper, Paper):
                    print(f"警告: 跳过非Paper实例: {type(paper)}")
                    continue
                row_data = self._paper_to_excel_row(paper, tags)
                data.append(row_data)
            except Exception as e:
                print(f"警告: 转换Paper到Excel行失败: {e}")
                continue
        
        # 创建DataFrame
        if not data:
            return pd.DataFrame()
        
        # 获取列名（使用table_name）
        columns = [tag['table_name'] for tag in tags]
        df = pd.DataFrame(data, columns=columns)
        df = self.normalize_dataframe_columns(df, self.config)

        
        return df
    
    # ========== 核心私有方法 ==========
    
    def _dict_to_paper_data(self, data_dict: Dict, tags: List[Dict]) -> Dict:
        """
        核心方法：将字典数据转换为Paper可用的数据字典
        
        Args:
            data_dict: 原始数据字典
            tags: 标签配置列表
            
        Returns:
            规范化的Paper数据字典
        """
        paper_data = {}
        
        for tag in tags:
            var_name = tag['variable']
            table_name = tag['table_name']
            tag_type = tag.get('type', 'string')
            
            # 尝试从两种键名获取值
            value = data_dict.get(var_name, data_dict.get(table_name, ""))
            
            # 处理空值
            if value is None or (isinstance(value, str) and value.strip() == ""):
                # 根据类型设置默认值
                if tag_type == 'bool':
                    value = False
                elif tag_type == 'int':
                    value = 0
                elif tag_type == 'float':
                    value = 0.0
                else:
                    value = ""
            else:
                # 类型转换
                value = self._convert_value_by_type(value, tag_type)
                
                # 特殊处理：验证pipeline_image字段
                if var_name == 'pipeline_image' and value:
                    # 验证图片格式和路径
                    from src.utils import validate_figure
                    fig_dir = self.config.settings['paths'].get('figure_dir', 'figures')
                    if not validate_figure(value, fig_dir):
                        print(f"警告: 图片路径格式无效: {value}")
                        value = ""  # 如果无效，清空
            
            paper_data[var_name] = value
        
        return paper_data
    
    def _excel_row_to_paper_data(self, row, tags: List[Dict]) -> Dict:
        """
        核心方法：将Excel行转换为Paper可用的数据字典
        
        Args:
            row: pandas Series
            tags: 标签配置列表
            
        Returns:
            规范化的Paper数据字典
        """
        try:
            import pandas as pd

        except Exception as e:
            print( f"无法导入pandas依赖:{e}\n 注意如果要加载excel文件，你需要安装pandas依赖包")
            return {}
        paper_data = {}
        
        for tag in tags:
            var_name = tag['variable']
            table_name = tag['table_name']
            tag_type = tag.get('type', 'string')
            
            # Excel中使用table_name作为列名
            if table_name in row:
                value = row[table_name]
            else:
                value = ""
            
            # 处理pandas NaN
            if pd.isna(value):
                # 根据类型设置默认值
                if tag_type == 'bool':
                    value = False
                elif tag_type == 'int':
                    value = 0
                elif tag_type == 'float':
                    value = 0.0
                else:
                    value = ""
            else:
                # 类型转换
                value = self._convert_value_by_type(value, tag_type)
            
            paper_data[var_name] = value
        
        return paper_data
    
    def _paper_to_dict(self, paper: Paper) -> Dict:
        """
        核心方法：将Paper对象转换为字典
        
        Args:
            paper: Paper对象
            
        Returns:
            字典，键为variable名称
        """
        paper_dict = asdict(paper)
        
        # 确保所有字段都是可序列化的
        for key, value in paper_dict.items():
            if value is None:
                paper_dict[key] = ""
            elif isinstance(value, bool):
                paper_dict[key] = value
            elif isinstance(value, (int, float)):
                paper_dict[key] = value
            else:
                paper_dict[key] = str(value)
        
        return paper_dict
    
    def _paper_to_excel_row(self, paper: Paper, tags: List[Dict]) -> Dict:
        """
        核心方法：将Paper对象转换为Excel行数据
        
        Args:
            paper: Paper对象
            tags: 标签配置列表
            
        Returns:
            字典，键为table_name
        """
        row_data = {}
        paper_dict = asdict(paper)
        
        for tag in tags:
            var_name = tag['variable']
            table_name = tag['table_name']
            tag_type = tag.get('type', 'string')
            
            value = paper_dict.get(var_name, "")
            
            # 处理空值
            if value is None or (isinstance(value, str) and value.strip() == ""):
                value = ""
            
            # 类型转换确保Excel中的格式正确
            if tag_type == 'bool':
                # Excel中布尔值通常显示为TRUE/FALSE
                value = bool(value)
            elif tag_type == 'int':
                try:
                    value = int(value) if value not in ("", None) else 0
                except (ValueError, TypeError):
                    value = 0
            elif tag_type == 'float':
                try:
                    value = float(value) if value not in ("", None) else 0.0
                except (ValueError, TypeError):
                    value = 0.0
            
            row_data[table_name] = value
        
        return row_data
    
    def _convert_value_by_type(self, value: Any, tag_type: str) -> Any:
        """
        根据标签类型转换值
        
        Args:
            value: 原始值
            tag_type: 标签类型
            
        Returns:
            转换后的值
        """
        if tag_type == 'bool':
            # 布尔类型转换
            if isinstance(value, bool):
                return value
            elif isinstance(value, (int, float)):
                return bool(value)
            elif isinstance(value, str):
                value_lower = value.strip().lower()
                if value_lower in ('True','TRUE','true', 'yes', '1', 'y', '是', '真'):
                    return True
                elif value_lower in ('False''FALSE','false', 'no', '0', 'n', '否', '假'):
                    return False
                else:
                    # 尝试转换为布尔值
                    try:
                        return bool(int(value))
                    except:
                        return False
            else:
                return bool(value)
        
        elif tag_type == 'int':
            # 整数类型转换
            if isinstance(value, (int, float)):
                return int(value)
            elif isinstance(value, str) and value.strip():
                try:
                    return int(float(value.strip()))
                except (ValueError, TypeError):
                    return 0
            else:
                return 0
        
        elif tag_type == 'float':
            # 浮点数类型转换
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str) and value.strip():
                try:
                    return float(value.strip())
                except (ValueError, TypeError):
                    return 0.0
            else:
                return 0.0
        
        elif tag_type == 'text':
            # 文本类型，保持原样
            if isinstance(value, (list, dict)):
                # 复杂结构转换为JSON字符串
                try:
                    return json.dumps(value, ensure_ascii=False)
                except:
                    return str(value)
            else:
                return str(value).strip()
        
        else:  # 'string' 或 'enum' 或其他
            # 字符串类型
            if isinstance(value, (list, dict)):
                # 复杂结构转换为JSON字符串
                try:
                    return json.dumps(value, ensure_ascii=False)
                except:
                    return str(value)
            else:
                return str(value).strip()
    def get_header_styles(self) -> Tuple[str, str, str]:
        """
        从 settings 中读取颜色配置（优先支持多种可能的key名称以兼容你的 setting_config）。
        返回 (header_row_fill, required_header_fill, required_font_color)。
        提供安全的默认值以避免配置缺失导致错误。
        """
        cfg_candidates = (
            self.settings.get('ui'),
            self.settings.get('visual'),
            self.settings.get('setting_config'),
            self.settings.get('colors'),
            {}
        )
        cfg = {}
        for c in cfg_candidates:
            if isinstance(c, dict) and c:
                cfg = c
                break

        header = cfg.get('header_row_fill', cfg.get('header_fill', '#D9EEFF'))
        required = cfg.get('required_header_fill', cfg.get('required_fill', '#0B66C3'))
        req_font = cfg.get('required_font_color', '#FFFFFF')
        # 规范化带或不带#的颜色
        def norm(c): return (c or '').lstrip('#')[:6].upper() if c else ''
        return ('#' + norm(header), '#' + norm(required), '#' + norm(req_font))

    def apply_excel_formatting(self, workbook, worksheet, df):
        """对Excel应用列宽、表头格式等美化"""
        try:
            from openpyxl.styles import PatternFill, Font
            from openpyxl.utils import get_column_letter

        except Exception as e:
            print( f"无法导入openpyxl依赖:{e}\n 注意如果要应用excel格式，你需要安装openpyxl依赖包")
            return
        # 获取样式（优先使用 df.attrs 中保存的初始化样式）
        hs = df.attrs.get('header_styles', None) if hasattr(df, 'attrs') else None
        if hs:
            header_row_color = hs.get('header_row_fill', '#D9EEFF')
            required_color = hs.get('required_header_fill', '#0B66C3')
            required_font_color = hs.get('required_font_color', '#FFFFFF')
        else:
            header_row_color, required_color, required_font_color = self.get_header_styles()

        header_fill = PatternFill(start_color=header_row_color.lstrip('#'), end_color=header_row_color.lstrip('#'), fill_type="solid")
        header_font = Font(bold=True)
        required_fill = PatternFill(start_color=required_color.lstrip('#'), end_color=required_color.lstrip('#'), fill_type="solid")
        required_font = Font(color=required_font_color.lstrip('#'), bold=True)

        # 第一行表头样式
        for i, col in enumerate(df.columns):
            col_letter = get_column_letter(i + 1)
            cell = worksheet[f"{col_letter}1"]
            cell.fill = header_fill
            cell.font = header_font

        # 对必填列的表头应用深色标注
        required_vars = [t['table_name'] for t in self.config.get_required_tags()]
        for i, col in enumerate(df.columns):
            if col in required_vars:
                col_letter = get_column_letter(i + 1)
                cell = worksheet[f"{col_letter}1"]
                cell.fill = required_fill
                cell.font = required_font

        # 设置列宽
        for column in df.columns:
            column_letter = get_column_letter(df.columns.get_loc(column) + 1)
            max_length = max(
                df[column].astype(str).map(len).max(),
                len(str(column))
            )
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

# 创建全局单例
_update_file_utils_instance = None

def get_update_file_utils():
    """获取更新文件工具单例"""
    global _update_file_utils_instance
    if _update_file_utils_instance is None:
        _update_file_utils_instance = UpdateFileUtils()
    return _update_file_utils_instance