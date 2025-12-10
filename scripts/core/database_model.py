"""
数据库模型
定义论文数据模型
"""
from dataclasses import dataclass, field, asdict, fields
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib


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
    show_in_readme: bool = True
    status: str = "unread"
    notes: str = ""
    
    # 系统字段
    submission_time: str = ""
    paper_id: str = ""  # 基于doi的哈希ID
    conflict_marker: str = ""  # 冲突标记
    
    def __post_init__(self):
        """初始化后处理"""
        # 清理DOI格式
        if self.doi:
            self.doi = self._clean_doi(self.doi)
        
        # 生成论文ID（基于DOI的哈希）
        if self.doi:
            self.paper_id = self._generate_paper_id()
        elif self.title and self.authors:
            # 如果没有DOI，使用标题和作者生成ID
            self.paper_id = self._generate_fallback_id()
    
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
    
    def _generate_paper_id(self) -> str:
        """基于DOI生成论文ID"""
        doi_clean = self.doi.lower().strip()
        return hashlib.md5(doi_clean.encode()).hexdigest()[:12]
    
    def _generate_fallback_id(self) -> str:
        """生成备用ID（当没有DOI时）"""
        identifier = f"{self.title[:50]}_{self.authors[:30]}"
        return hashlib.md5(identifier.encode()).hexdigest()[:12]
    
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
    
    def is_valid(self, config_loader) -> List[str]:
        """验证论文数据是否有效，返回错误消息列表"""
        errors = []
        
        # 检查必填字段
        required_tags = config_loader.get_required_tags()
        for tag in required_tags:
            value = getattr(self, tag['variable'], "")
            if not value or str(value).strip() == "":
                errors.append(f"{tag['display_name']} ({tag['variable']}) 是必填字段")
        
        # 验证字段格式
        active_tags = config_loader.get_active_tags()
        for tag in active_tags:
            value = getattr(self, tag['variable'], "")
            if value and str(value).strip() != "":
                if not config_loader.validate_value(tag, value):
                    errors.append(f"{tag['display_name']} ({tag['variable']}) 格式无效")
        
        # 验证分类是否有效
        if self.category:
            valid_categories = [cat['unique_name'] for cat in config_loader.get_active_categories()]
            if self.category not in valid_categories:
                errors.append(f"分类 '{self.category}' 无效，有效分类: {', '.join(valid_categories)}")
        
        return errors
    
    def get_key(self) -> str:
        """获取论文的唯一键（用于比较和去重）"""
        return f"{self.doi}_{self.title}"
    
    def is_similar_to(self, other: 'Paper') -> bool:
        """检查是否与另一篇论文相似（DOI或标题相同）"""
        self.title=str(self.title).strip()
        other.title=str(other.title).strip()
        if self.doi and other.doi and self.doi == other.doi:
            return True
        if self.title and other.title and self.title.lower() == other.title.lower():
            return True
        return False