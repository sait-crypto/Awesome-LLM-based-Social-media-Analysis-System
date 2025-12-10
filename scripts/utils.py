"""
通用工具函数
"""
import os
import re
import json
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path


def validate_url(url: str) -> bool:
    """验证URL格式"""
    if not url:
        return False
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(re.match(url_pattern, url))


def validate_doi(doi: str) -> bool:
    """验证DOI格式"""
    if not doi:
        return False
    
    # 清理DOI
    doi = clean_doi(doi)
    
    # DOI正则表达式
    doi_pattern = re.compile(r'^10\.\d{4,9}/[-._;()/:A-Z0-9]+$', re.IGNORECASE)
    return bool(re.match(doi_pattern, doi))


def clean_doi(doi: str) -> str:
    """清理DOI，移除URL部分"""
    if not doi:
        return ""
    
    doi = doi.strip()
    
    # 移除常见的URL前缀
    prefixes = ['https://doi.org/', 'http://doi.org/', 
                'https://dx.doi.org/', 'http://dx.doi.org/',
                'doi:', 'DOI:']
    
    for prefix in prefixes:
        if doi.lower().startswith(prefix.lower()):
            doi = doi[len(prefix):]
            break
    
    return doi


def extract_doi_from_url(url: str) -> Optional[str]:
    """从URL中提取DOI"""
    if not url:
        return None
    
    # 匹配DOI URL
    doi_patterns = [
        r'doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        r'dx\.doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        r'doi:(10\.\d{4,9}/[-._;()/:A-Z0-9]+)'
    ]
    
    for pattern in doi_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def ensure_directory(path: str) -> bool:
    """确保目录存在，如果不存在则创建"""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"创建目录失败 {path}: {e}")
        return False


def read_json_file(filepath: str) -> Optional[Dict]:
    """读取JSON文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取JSON文件失败 {filepath}: {e}")
        return None


def write_json_file(filepath: str, data: Dict, indent: int = 2) -> bool:
    """写入JSON文件"""
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except Exception as e:
        print(f"写入JSON文件失败 {filepath}: {e}")
        return False


def read_excel_file(filepath: str) -> Optional[pd.DataFrame]:
    """读取Excel文件"""
    try:
        if not os.path.exists(filepath):
            return pd.DataFrame()
        
        df = pd.read_excel(filepath, engine='openpyxl')
        return df
    except Exception as e:
        print(f"读取Excel文件失败 {filepath}: {e}")
        return None


def write_excel_file(filepath: str, df: pd.DataFrame) -> bool:
    """写入Excel文件"""
    try:
        ensure_directory(os.path.dirname(filepath))
        df.to_excel(filepath, index=False, engine='openpyxl')
        return True
    except Exception as e:
        print(f"写入Excel文件失败 {filepath}: {e}")
        return False


def truncate_text(text: str, max_length: int, ellipsis: str = "...") -> str:
    """截断文本，保留最大长度"""
    if not text:
        return ""
    
    if len(str(text)) <= max_length:
        return text
    
    return text[:max_length - len(ellipsis)] + ellipsis


def format_authors(authors: str, max_length: int = 150) -> str:
    """格式化作者列表"""
    if not authors:
        return ""
    authors = str(authors)
    # 清理空格
    authors = ' '.join(authors.split())
    
    # 如果作者列表太长，截断
    if len(authors) > max_length:
        # 尝试在逗号处截断
        parts = authors.split(',')
        truncated = parts[0]
        
        for i in range(1, len(parts)):
            if len(truncated + ', ' + parts[i]) <= max_length - 3:  # 为"..."留空间
                truncated += ', ' + parts[i]
            else:
                truncated += ', ...'
                break
        
        return truncated
    
    return authors


def get_current_timestamp() -> str:
    """获取当前时间戳"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def compare_papers(paper1: Dict, paper2: Dict, key_fields: List[str] = None) -> List[str]:
    """比较两篇论文的差异，返回差异字段列表"""
    if key_fields is None:
        key_fields = ['doi', 'title', 'authors']
    
    differences = []
    
    for field in key_fields:
        val1 = paper1.get(field, "")
        val2 = paper2.get(field, "")
        
        if str(val1).strip().lower() != str(val2).strip().lower():
            differences.append(field)
    
    return differences


def merge_paper_data(existing: Dict, new: Dict, prefer_new: bool = True) -> Dict:
    """合并两篇论文的数据"""
    result = existing.copy()
    
    for key, new_value in new.items():
        existing_value = existing.get(key, "")
        
        if not existing_value or (prefer_new and new_value):
            result[key] = new_value
    
    return result


def create_hyperlink(text: str, url: str) -> str:
    """创建Markdown超链接"""
    if not url:
        return text
    
    # 确保URL格式正确
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    return f"[{text}]({url})"


def escape_markdown(text: str) -> str:
    """转义Markdown特殊字符"""

    if not text:
        return ""
    text = str(text)
    # 需要转义的Markdown字符
    special_chars = ['\\', '`', '*', '_', '{', '}', '[', ']', '(', ')', '#', '+', '-', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    
    return text


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符"""
    # 移除非法字符
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    
    # 移除开头和结尾的空格和点
    filename = filename.strip('. ')
    
    # 限制长度
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    
    return filename