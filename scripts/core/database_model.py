"""
数据库模型
定义论文数据模型
"""
from dataclasses import dataclass, field, asdict, fields
from typing import Dict, List, Optional,Union, Any
from datetime import datetime
import hashlib
from scripts.utils import clean_doi
from scripts.core.config_loader import get_config_instance
import sys,os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

@dataclass
class Paper:
    """论文数据模型"""
    
    # 基础信息
    doi: str = ""
    title: str = ""
    authors: str = ""
    date: str = ""
    category: str = ""
    
    # 总结信息（在README中合并为一列）
    summary_motivation: str = ""
    summary_innovation: str = ""
    summary_method: str = ""
    summary_conclusion: str = ""
    summary_limitation: str = ""
    
    # 链接信息（在README中合并为一列）
    paper_url: str = ""
    project_url: str = ""
    
    # 其他信息
    conference: str = ""
    title_translation: str = ""
    analogy_summary: str = ""
    pipeline_image: str = ""
    abstract: str = ""
    contributor: str = ""
    notes: str = ""
    
    # 系统字段
    show_in_readme: bool = True
    status: str = "" # "" "unread" "reading" "done" "adopted"
    submission_time: str = ""
    conflict_marker: bool = False  # 冲突标记
    def __post_init__(self):
        """初始化后处理"""
        # 清理DOI格式
        if self.doi:
            self.doi = self._clean_doi(self.doi)
    
    def _clean_doi(self, doi: str) -> str:
        """清理DOI格式，移除URL部分"""
        if doi.startswith("http"):
            # 提取DOI部分
            doi_patterns = [
                r"doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
                r"dx\.doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
                r"doi:(10\.\d{4,9}/[-._;()/:A-Z0-9]+)"
            ]
            import re
            for pattern in doi_patterns:
                match = re.search(pattern, doi, re.IGNORECASE)
                if match:
                    return match.group(1)
        return doi.strip()
    
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Paper':
        """从字典创建Paper对象"""
        # 过滤掉字典中不在dataclass字段中的键
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    

    
    def get_key(self) -> str:
        """获取论文的唯一键（用于比较和去重）"""
        return f"{self.doi}_{self.title}"
    
    def _normalize_doi_for_compare(self) -> str:
        """清理 DOI 并忽略可能存在的冲突标记（conflict_marker）"""
        conflict_marker=get_config_instance().settings['database'].get('conflict_marker','') 
        if not self.doi:
            return ""
        s = str(self.doi).strip()
        if conflict_marker:
            s = s.replace(conflict_marker, "")
        # 使用 _clean_doi 进一步清理 URL 前缀等
        s = self._clean_doi(s)
        return s.lower()

    
    def _validate_field(self,tag: Dict[str, Any], value: Any) -> bool:
        """
        字段级校验封装：调用 get_config_instance().validate_value 并处理 DOI 中可能的 conflict_marker。
        返回 True 表示合法。
        """
        if tag.get('variable') == 'doi':
            # 对 DOI 先去除冲突标记再校验
            val = self._normalize_doi_for_compare()
            return get_config_instance().validate_value(tag, val)
        return get_config_instance().validate_value(tag, value)
    def is_valid(self) -> List[str]:
        """
        论文级校验，返回错误信息列表（空表示合法）。
        - 校验必填字段
        - 校验字段格式（使用 validate_field）
        - 校验 category 是否为激活分类
        """
        errors = []
        required_tags = get_config_instance().get_required_tags()
        for tag in required_tags:
            var = tag['variable']
            val = getattr(self, var, "")
            if val is None or str(val).strip() == "":
                errors.append(f"{tag.get('display_name', var)} ({var}) 是必填字段")

        # 字段格式校验
        active_tags = get_config_instance().get_active_tags()
        for tag in active_tags:
            var = tag['variable']
            val = getattr(self, var, "")
            if val is None or str(val).strip() == "":
                continue
            if not self._validate_field(tag, val):
                errors.append(f"{tag.get('display_name', var)} ({var}) 格式无效")

        # category 检查
        if self.category:
            valid_categories = [cat['unique_name'] for cat in get_config_instance().get_active_categories()]
            if self.category not in valid_categories:
                errors.append(f"分类 '{self.category}' 无效，有效分类: {', '.join(valid_categories)}")

        return errors

def _normalize_doi_for_compare(doi: Optional[str]) -> str:
    """清理 DOI 并忽略可能存在的冲突标记（conflict_marker）"""
    conflict_marker = get_config_instance().settings['database'].get('conflict_marker','')
    if not doi:
        return ""
    s = str(doi).strip()
    if conflict_marker:
        s = s.replace(conflict_marker, "")
    # 使用 utils.clean_doi 进一步清理 URL 前缀等
    s = clean_doi(s)
    return s.lower()

def is_same_identity(a: Union[Paper, Dict[str, Any]], b: Union[Paper, Dict[str, Any]]) -> bool:
    """
    判断 a 和 b 是否表示同一篇论文（基于 DOI 或 title）。
    DOI 比较时会忽略 conflict_marker。
    支持 Paper 对象或 dict。
    """
    
    def get_field(x, name):
        if isinstance(x, Paper):
            return getattr(x, name, "") or ""
        return x.get(name, "") if isinstance(x, dict) else ""

    doi_a = _normalize_doi_for_compare(get_field(a, 'doi') )
    doi_b = _normalize_doi_for_compare(get_field(b, 'doi') )
    if doi_a and doi_b and doi_a == doi_b:
        return True

    title_a = (get_field(a, 'title') or "").strip().lower()
    title_b = (get_field(b, 'title') or "").strip().lower()
    if title_a and title_b and title_a == title_b:
        return True

    return False

def _papers_fields_equal(new: Union[Paper, Dict[str, Any]], exist: Union[Paper, Dict[str, Any]],
                         complete_compare=False, ignore_fields: Optional[List[str]] = None) -> bool:
    """
    精确比较两个论文条目的字段（用于判定是否"完全相同"）。
    参数：
        new：新提交论文
        exist：用于比较的已存在论文
        complete_compare：bool，是否进行严格的所有字段比较
        ignore_fields：List，需要忽略的字段，默认值：系统字段
    complete_compare=False：除忽略ignore_fields外，需要特殊处理空字段：
        如果new的非空域集合是exist的子集，则只判断new中所有非空字段是否相同，相同返回True
        如果new的非空域集合非exist的子集（前者包含后者或无包含关系），则直接返回False
    complete_compare=True：除忽略ignore_fields外，比较全部字段
    
    比较 DOI 时会忽略 conflict_marker。
    """
    conflict_marker = get_config_instance().settings['database'].get('conflict_marker','')
    if ignore_fields is None:
        system_tags=get_config_instance().get_system_tags()
        ignore_fields = [t["variable"] for t in system_tags]

    if isinstance(new, Paper):
        a_dict = new.to_dict()
    else:
        a_dict = dict(new)

    if isinstance(exist, Paper):
        b_dict = exist.to_dict()
    else:
        b_dict = dict(exist)

    # 规范化 DOI 比较：移除 conflict_marker 并清理
    a_doi = _normalize_doi_for_compare(a_dict.get('doi', ""))
    b_doi = _normalize_doi_for_compare(b_dict.get('doi', ""))
    a_dict['doi'] = a_doi
    b_dict['doi'] = b_doi

    def is_non_empty(value):
        """判断字段值是否为非空"""
        if value is None:
            return False
        if isinstance(value, (str, list, dict, set)):
            return bool(value)
        if isinstance(value, (int, float)):
            # 数字类型总是视为有值
            return True
        # 其他类型转为字符串判断
        return str(value).strip() != ""

    def get_non_empty_keys(dict_obj, ignore_keys):
        """获取字典中非空的键（排除忽略字段）"""
        return {
            k: dict_obj[k] 
            for k in dict_obj 
            if k not in ignore_keys and is_non_empty(dict_obj[k])
        }

    if not complete_compare:
        # 获取非空字段集合
        a_non_empty = get_non_empty_keys(a_dict, ignore_fields)
        b_non_empty = get_non_empty_keys(b_dict, ignore_fields)
        
        # 检查new的非空字段是否是exist的非空字段的子集
        a_keys_set = set(a_non_empty.keys())
        b_keys_set = set(b_non_empty.keys())
        
        if not a_keys_set.issubset(b_keys_set):
            # new的非空域集合不是exist的子集，直接返回False
            return False
        
        # 比较new中的所有非空字段
        for k in a_non_empty:
            if k in ignore_fields:
                continue
                
            va = a_non_empty[k]
            vb = b_dict.get(k, "")
            
            # 统一转换为字符串比较（保持 bool/int 的语义）
            if isinstance(va, bool) or isinstance(vb, bool):
                if bool(va) != bool(vb):
                    return False
            
            else:
                if str(va).strip() != str(vb).strip():
                    return False
        return True
    
    else:
        # complete_compare=True：除忽略ignore_fields外，比较全部字段
        # 获取所有需要比较的键（排除忽略字段）
        all_keys = set(a_dict.keys()) | set(b_dict.keys())
        
        for k in all_keys:
            if k in ignore_fields:
                continue
                
            va = a_dict.get(k, "")
            vb = b_dict.get(k, "")
            
            # 统一转换为字符串比较（保持 bool/int 的语义）
            if isinstance(va, bool) or isinstance(vb, bool):
                if bool(va) != bool(vb):
                    return False
            else:
                if str(va).strip() != str(vb).strip():
                    return False
        return True
def is_duplicate_paper(existing_papers: List[Paper], new_paper: Paper,complete_compare=False) -> bool:
    """
    判断新提交是否为重复论文条目：
    - 在 existing_papers 中找出与 new_paper 表示相同论文（一致 identity）的条目集合；
    - 如果该集合中存在任一条目的所有字段都与 new_paper 完全一致，则为重复paper，返回 True。
    """
    same_identity_entries = [p for p in existing_papers if is_same_identity(p, new_paper)]
    if not same_identity_entries:
        return False
    for ex in same_identity_entries:
        if _papers_fields_equal(ex, new_paper,complete_compare):
            return True
    return False
