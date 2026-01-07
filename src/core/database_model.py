"""
数据库模型
定义论文数据模型
"""
from dataclasses import dataclass, field, asdict, fields
from typing import Dict, List, Optional, Union, Any, Tuple
from datetime import datetime
import hashlib
import sys
import os
import re

from src.core.config_loader import get_config_instance

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

# 导入工具函数
from src.utils import (
    validate_url, validate_doi, clean_doi, format_authors,
    validate_authors, normalize_pipeline_image, validate_pipeline_image,
    get_current_timestamp
)


@dataclass
class Paper:
    """论文数据模型"""
    
    # 基础信息
    doi: str = ""
    title: str = ""
    authors: str = ""
    date: str = ""
    category: str = ""
    
    # 总结信息
    summary_motivation: str = ""
    summary_innovation: str = ""
    summary_method: str = ""
    summary_conclusion: str = ""
    summary_limitation: str = ""
    
    # 链接信息
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
    status: str = ""  # "" "unread" "reading" "done" "adopted"
    submission_time: str = ""
    conflict_marker: bool = False
    
    def __post_init__(self):
        """初始化后处理"""
        # 获取配置实例
        from src.core.config_loader import get_config_instance
        config = get_config_instance()
        conflict_marker = config.settings['database'].get('conflict_marker', '[💥冲突]')
        
        # 规范化字段
        self.doi = clean_doi(self.doi, conflict_marker) if self.doi else ""
        self.authors = format_authors(self.authors) if self.authors else ""
        
        # 规范化pipeline_image
        if self.pipeline_image:
            figure_dir = config.settings['paths'].get('figure_dir', 'figures')
            self.pipeline_image = normalize_pipeline_image(self.pipeline_image, figure_dir)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Paper':
        """从字典创建Paper对象"""
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    def get_key(self) -> str:
        """获取论文的唯一键（用于比较和去重）"""
        return f"{self.doi}_{self.title}"
    
    def validate_paper_fields(
        self, 
        config_instance,
        check_required: bool = True,
        check_non_empty: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        统一的论文字段验证函数
        
        参数:
            config_instance: 配置实例
            check_required: 是否检查必填字段
            check_non_empty: 是否检查非空字段（包括类型验证和validation字段验证）
        
        返回:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        # 获取配置
        conflict_marker = config_instance.settings['database'].get('conflict_marker', '[💥冲突]')
        required_tags = config_instance.get_required_tags() if check_required else []
        active_tags = config_instance.get_active_tags()
        
        # 1. 特殊字段验证
        # DOI验证
        if self.doi:
            doi_valid, cleaned_doi = validate_doi(self.doi, check_format=True, conflict_marker=conflict_marker)
            if not doi_valid and check_non_empty:
                errors.append(f"DOI格式无效: {self.doi}")
        
        # 作者验证
        if self.authors:
            authors_valid, formatted_authors = validate_authors(self.authors)
            if not authors_valid and check_non_empty:
                errors.append(f"作者格式无效")
        
        # Pipeline图片验证
        if self.pipeline_image:
            figure_dir = config_instance.settings['paths'].get('figure_dir', 'figures')
            pipeline_valid, normalized_path = validate_pipeline_image(self.pipeline_image, figure_dir)
            if not pipeline_valid and check_non_empty:
                errors.append(f"Pipeline图片格式无效: {self.pipeline_image}")
            elif pipeline_valid:
                # 更新规范化后的路径
                self.pipeline_image = normalized_path
        
        # URL验证
        if self.paper_url and not validate_url(self.paper_url) and check_non_empty:
            errors.append(f"论文链接格式无效: {self.paper_url}")
        
        if self.project_url and not validate_url(self.project_url) and check_non_empty:
            errors.append(f"项目链接格式无效: {self.project_url}")
        
        # 2. 必填字段检查
        if check_required:
            for tag in required_tags:
                var_name = tag['variable']
                display_name = tag.get('display_name', var_name)
                value = getattr(self, var_name, "")
                
                if not value or str(value).strip() == "":
                    errors.append(f"必填字段为空: {display_name} ({var_name})")
        
        # 3. 非空字段检查（类型验证和validation字段验证）
        if check_non_empty:
            for tag in active_tags:
                var_name = tag['variable']
                display_name = tag.get('display_name', var_name)
                tag_type = tag.get('type', 'string')
                validation_pattern = tag.get('validation')
                value = getattr(self, var_name, "")
                
                # 跳过空值（除非是必填字段）
                if not value or str(value).strip() == "":
                    continue
                
                # 类型验证
                if tag_type == 'bool':
                    if str(value).lower() not in ['true', 'false', 'yes', 'no', '1', '0', 'y', 'n']:
                        errors.append(f"字段类型不匹配: {display_name} 应为布尔值")
                elif tag_type == 'enum' and var_name == 'category':
                    # 验证分类是否有效
                    valid_categories = [cat['unique_name'] for cat in config_instance.get_active_categories()]
                    if value not in valid_categories:
                        errors.append(f"分类无效: {value}")
                elif tag_type == 'int':
                    try:
                        int(value)
                    except ValueError:
                        errors.append(f"字段类型不匹配: {display_name} 应为整数")
                elif tag_type == 'float':
                    try:
                        float(value)
                    except ValueError:
                        errors.append(f"字段类型不匹配: {display_name} 应为浮点数")
                
                # validation字段验证（正则表达式）
                if validation_pattern:
                    try:
                        if not re.match(validation_pattern, str(value)):
                            errors.append(f"字段格式无效: {display_name} 不符合验证规则")
                    except re.error:
                        # 如果正则表达式有问题，跳过验证
                        pass
        
        return (len(errors) == 0, errors)
    
    def is_valid(self, config_instance = None) -> List[str]:
        """
        兼容性方法，调用新的验证函数
        """
        if not config_instance:
            from src.core.config_loader import get_config_instance
            config_instance = get_config_instance()
        
        valid, errors = self.validate_paper_fields(
            config_instance, 
            check_required=True,
            check_non_empty=True
        )
        return errors


def _normalize_doi_for_compare(doi: Optional[str]) -> str:
    """清理 DOI 并忽略可能存在的冲突标记"""
    from src.core.config_loader import get_config_instance
    config = get_config_instance()
    conflict_marker = config.settings['database'].get('conflict_marker', '[💥冲突]')
    
    if not doi:
        return ""
    
    s = str(doi).strip()
    if conflict_marker:
        s = s.replace(conflict_marker, "")
    
    # 清理URL部分
    s = clean_doi(s, conflict_marker)
    return s.lower()


# ... (is_same_identity, _papers_fields_equal, is_duplicate_paper 函数保持不变)

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
