
"""
通用工具函数
"""
import urllib.parse
import os
import re
import json
from typing import List, Dict, Any, Optional,Tuple
from datetime import datetime
from pathlib import Path



def validate_url(url: str) -> bool:
    """验证URL格式"""
    if not url:
        return False
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z0-9-]{2,}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(re.match(url_pattern, url))


def clean_doi(doi: str, conflict_marker: str = None) -> str:
    """清理DOI，移除URL部分和冲突标记"""
    if not doi:
        return ""
    
    # 如果提供了冲突标记，先移除
    if conflict_marker:
        doi = doi.replace(conflict_marker, "").strip()
    
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


def validate_doi(doi: str, check_format: bool = True, conflict_marker: str = None) -> Tuple[bool, str]:
    """验证DOI格式，返回(是否有效, 清理后的DOI)"""
    if not doi:
        return (False, "")
    
    # 清理DOI
    cleaned_doi = clean_doi(doi, conflict_marker)
    
    if not cleaned_doi:
        return (False, "")
    
    # 如果不需要格式验证，直接返回
    if not check_format:
        return (True, cleaned_doi)
    
    # DOI正则表达式
    doi_pattern = re.compile(r'^10\.\d{4,9}/[-._;()/:A-Z0-9]+$', re.IGNORECASE)
    
    if bool(re.match(doi_pattern, cleaned_doi)):
        return (True, cleaned_doi)
    else:
        return (False, cleaned_doi)


def format_authors(authors: str, max_length: int = 150) -> str:
    """格式化作者列表"""
    if not authors:
        return ""
    
    authors = str(authors)
    # 清理多余空格和换行
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


def validate_authors(authors: str, max_length: int = 150) -> Tuple[bool, str]:
    """验证作者格式，返回(是否有效, 格式化后的作者)"""
    if not authors:
        return (False, "")
    
    formatted = format_authors(authors, max_length)
    return (len(formatted) > 0, formatted)


def normalize_pipeline_image(path: str, figure_dir: str = "figures") -> str:
    """
    规范化pipeline图片路径
    输入可以是：1) 文件名 2) 相对路径 3) 绝对路径
    输出：相对于项目根的路径，如 "figures/image.png"
    """
    if not path or not str(path).strip():
        return ""
    
    path_s = str(path).strip()
    
    # 统一使用正斜杠
    path_s = path_s.replace('\\', '/')
    figure_dir = figure_dir.replace('\\', '/').rstrip('/')
    # 如果 figure_dir 是绝对路径（来自 setting.config），取其 basename 以保证返回值为相对路径（例如 "figures"）
    if os.path.isabs(figure_dir):
        figure_dir = os.path.basename(figure_dir)
    
    # 如果是绝对路径，提取文件名并放到相对的 figure_dir 下
    if os.path.isabs(path_s):
        filename = os.path.basename(path_s)
        return f"{figure_dir}/{filename}"
    
    # 如果已经是相对路径且以figure_dir开头，直接返回
    if path_s.startswith(figure_dir + '/'):
        return path_s
    
    # 如果只是文件名（不包含路径分隔符），添加figure_dir前缀
    if '/' not in path_s and '\\' not in path_s:
        return f"{figure_dir}/{path_s}"
    
    # 其他情况：提取文件名并放到figure_dir下
    filename = os.path.basename(path_s)
    return f"{figure_dir}/{filename}"


def validate_pipeline_image(path: str, figure_dir: str = "figures") -> Tuple[bool, str]:
    """
    验证pipeline图片，返回(是否有效, 规范化后的路径)
    验证规则：
    1. 非空
    2. 扩展名是图片格式
    3. 路径符合规范
    """
    if not path or not str(path).strip():
        return (True, "")  # 允许为空
    
    path_s = str(path).strip()
    
    # 先规范化路径
    normalized = normalize_pipeline_image(path_s, figure_dir)
    
    # 检查文件扩展名
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
    ext = os.path.splitext(normalized)[1].lower()
    
    if ext not in valid_extensions:
        return (False, normalized)
    
    # 检查路径是否在figure_dir下
    # 规范化 figure_dir，防止 Windows 路径分隔符不一致导致 startswith 失败
    fig_dir_norm = figure_dir.replace('\\', '/').rstrip('/')
    # 如果 figure_dir 是绝对路径，使用其 basename 进行比较（确保与 normalize_pipeline_image 返回的相对路径一致）
    if os.path.isabs(fig_dir_norm):
        fig_dir_norm = os.path.basename(fig_dir_norm)
    if not normalized.startswith(fig_dir_norm + '/'):
        return (False, normalized)
    
    return (True, normalized)



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




def truncate_text(text: str, max_length: int, ellipsis: str = "...") -> str:
    """截断文本，保留最大长度"""
    if not text:
        return ""
    
    if len(str(text)) <= max_length:
        return text
    
    return text[:max_length - len(ellipsis)] + ellipsis



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


def _escape_md_text(text: str) -> str:
    """对 Markdown 链接文本做基础转义（中括号/反斜杠/换行）"""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", " ")
    s = s.replace("]", "\\]")
    s = s.replace("[", "\\[")
    return s

def create_hyperlink(text: str, url: str) -> str:
    """
    生成 Markdown 风格超链接： [text](url)
    - 当 url 为空或 None 时仅返回文本
    - 对显示文本做基础转义以避免破坏 Markdown
    """
    if not url:
        return _escape_md_text(text)
    # 保证 URL 中的空格等被安全编码，但保留常见 URL 字符
    try:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.scheme:
            # 若缺少 scheme，假定为 https
            url = "https://" + url
        # 只对 URL 的路径/查询部分做 quote，保留 :// 和主机
        url = urllib.parse.urlunsplit(parsed._replace(path=urllib.parse.quote(parsed.path, safe="/"), query=urllib.parse.quote_plus(parsed.query, safe="=&")) )
    except Exception:
        url = url.replace(" ", "%20")
    return f"[{_escape_md_text(text)}]({url})"


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


def validate_figure(path: str, figure_dir: str) -> bool:
    """
    验证 pipeline 图像路径/文件名是否合法：
    - 扩展名必须是 .jpg/.jpeg/.png
    - 必须为相对路径，且位于 figure_dir 下（如果给的是带目录的路径）
    - 当只给文件名时视为有效（后续会补全为 figure_dir/filename）
    
    注意：这里只验证格式和位置，不验证文件是否存在
    """
    if not path or not str(path).strip():
        return False
    
    path_s = str(path).strip()
    
    # 检查文件扩展名
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
    ext = os.path.splitext(path_s)[1].lower()
    if ext not in valid_extensions:
        return False
    
    # 规范化路径，确保使用正斜杠
    path_s = path_s.replace('\\', '/')
    
    # 如果只是文件名（不包含路径分隔符），直接返回True
    if '/' not in path_s:
        return True
    
    # 如果包含路径，检查是否在figure_dir下
    # 规范化figure_dir
    fig_dir_norm = figure_dir.replace('\\', '/').rstrip('/')
    
    # 检查路径是否以figure_dir开头
    if not path_s.startswith(fig_dir_norm + '/'):
        return False
    
    return True


def normalize_figure_path(path: str, figure_dir: str) -> str:
    """
    把用户输入的图像名/路径规范为相对于仓库根的路径（使用正斜杠）。
    - 若仅是文件名：返回 figure_dir/filename
    - 若已有路径且以 figure_dir 开头：返回规范化的路径
    - 若已有路径但不以 figure_dir 开头：提取文件名并放到 figure_dir 下
    
    注意：这里不验证文件是否存在，只做路径规范化
    """
    if not path or not str(path).strip():
        return ""
    
    path_s = str(path).strip()
    
    # 统一使用正斜杠
    path_s = path_s.replace('\\', '/')
    fig_dir_norm = figure_dir.replace('\\', '/').rstrip('/')
    
    # 如果只是文件名（不包含路径分隔符），添加figure_dir前缀
    if '/' not in path_s and '\\' not in path_s:
        return f"{fig_dir_norm}/{path_s}"
    
    # 如果已经以figure_dir开头，直接返回规范化的路径
    if path_s.startswith(fig_dir_norm + '/'):
        # 确保只有一个figure_dir前缀
        parts = path_s.split('/')
        if parts[0] == fig_dir_norm:
            return path_s
        else:
            # 如果figure_dir包含多级目录，需要特殊处理
            return f"{fig_dir_norm}/{os.path.basename(path_s)}"
    
    # 其他情况：提取文件名并放到figure_dir下
    return f"{fig_dir_norm}/{os.path.basename(path_s)}"



def figure_exists_in_repo(figure_path: str, project_root: str = None) -> bool:
    """
    检查图片是否存在于仓库中
    - figure_path: 规范化后的图片路径
    - project_root: 项目根目录，如果为None则使用当前工作目录
    """
    if not figure_path:
        return False
    
    if project_root is None:
        project_root = os.getcwd()
    
    # 构建完整路径
    full_path = os.path.join(project_root, figure_path)
    
    # 检查文件是否存在
    return os.path.isfile(full_path)
