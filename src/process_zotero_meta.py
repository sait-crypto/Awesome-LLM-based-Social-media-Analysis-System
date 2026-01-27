"""
处理Zotero元数据
将Zotero导出的JSON数据转化为Paper对象
"""
import json
import re
from typing import List, Union, Dict, Any
from src.core.database_model import Paper

class ZoteroProcessor:
    """Zotero元数据处理器"""

    def process_meta_data(self, input_data: Union[str, List[Dict], Dict]) -> List[Paper]:
        """
        处理Zotero元数据，返回Paper对象列表
        参数 input_data: JSON字符串 或 字典列表 或 单个字典
        """
        raw_items = []
        
        # 1. 解析输入
        try:
            if isinstance(input_data, str):
                cleaned_str = input_data.strip()
                if not cleaned_str:
                    return []
                raw_items = json.loads(cleaned_str)
            else:
                raw_items = input_data
            
            # 确保是列表
            if isinstance(raw_items, dict):
                raw_items = [raw_items]
            elif not isinstance(raw_items, list):
                return []
                
        except json.JSONDecodeError as e:
            print(f"Zotero JSON解析失败: {e}")
            return []
        except Exception as e:
            print(f"处理Zotero数据出错: {e}")
            return []

        # 2. 转换为Paper对象
        papers = []
        for item in raw_items:
            try:
                # 跳过非条目类型（如附件/笔记单独导出时可能出现，虽然通常嵌套在items里）
                if item.get("itemType") in ["attachment", "note"]:
                    continue
                    
                paper = self._map_item_to_paper(item)
                papers.append(paper)
            except Exception as e:
                print(f"转换单条Zotero数据失败: {e}")
                continue
                
        return papers

    def _map_item_to_paper(self, item: Dict[str, Any]) -> Paper:
        """将单个Zotero条目映射为Paper对象"""
        
        # 1. 基础字段
        doi = item.get("DOI", "")
        title = item.get("title", "")
        date = item.get("date", "")
        paper_url = item.get("url", "")
        abstract = item.get("abstractNote", "")
        
        # 2. Authors (Creators)
        # 格式化为: FirstName LastName, FirstName LastName
        creators = item.get("creators", [])
        authors_list = []
        for c in creators:
            if c.get("creatorType") == "author":
                first = c.get("firstName", "").strip()
                last = c.get("lastName", "").strip()
                if first and last:
                    authors_list.append(f"{first} {last}")
                elif last:
                    authors_list.append(last)
                elif first:
                    authors_list.append(first)
        authors = ", ".join(authors_list)

        # 3. Conference (按优先级)
        # series -> journalAbbreviation -> conferenceName (Zotero raw) -> proceedingsTitle -> publicationTitle
        conference = ""
        priority_keys = ["journalAbbreviation", "conferenceName", "proceedingsTitle", "publicationTitle","bookTitle","series"]
        for key in priority_keys:
            val = item.get(key)
            if val and str(val).strip():
                conference = str(val).strip()
                break
        
        # 4. 解析 Extra 字段 (TLDR, Translation)
        extra_str = item.get("extra", "")
        title_translation = ""
        analogy_summary = ""
        
        if extra_str:
            # 提取 titleTranslation (仅内容，不含前缀)
            tt_match = re.search(r"titleTranslation:\s*(.*?)(?:\n|$)", extra_str, re.IGNORECASE)
            if tt_match:
                title_translation = tt_match.group(1).strip()
            
            # 提取 TLDR (保留 "TLDR:" 前缀)
            tldr_match = re.search(r"(TLDR:.*?)(?:\n|$)", extra_str, re.IGNORECASE)
            if tldr_match:
                analogy_summary = tldr_match.group(1).strip()

        # 5. Notes
        # Zotero notes 通常包含 html 标签，简单处理移除标签
        notes_content = []
        raw_notes = item.get("notes", [])
        for n in raw_notes:
            if isinstance(n, str):
                notes_content.append(self._strip_html(n))
            elif isinstance(n, dict) and "note" in n:
                notes_content.append(self._strip_html(n["note"]))
        notes = "\n".join(notes_content)

        # 6. 构建Paper对象
        # 注意：这里创建的是基础Paper，不包含ID等数据库特定的信息
        paper = Paper(
            doi=doi,
            title=title,
            authors=authors,
            date=date,
            paper_url=paper_url,
            conference=conference,
            title_translation=title_translation,
            analogy_summary=analogy_summary,
            abstract=abstract,
            notes=notes,
            # 设置默认值
            show_in_readme=True,
            status="unread" 
        )
        return paper

    def _strip_html(self, text: str) -> str:
        """简单的HTML标签移除"""
        if not text:
            return ""
        # 移除 <...> 标签
        text = re.sub(r'<[^>]+>', '', text)
        # 替换常见转义
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        return text.strip()