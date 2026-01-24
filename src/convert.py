"""
项目入口1：从核心excel生成readme论文表格部分
"""
import os
import sys
from pathlib import Path
from urllib.parse import quote

# 添加 src 目录到 Python 路径（使 `core` 包可被导入）
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.database_manager import DatabaseManager
from core.database_model import Paper
from src.core.update_file_utils import get_update_file_utils
from src.utils import truncate_text, format_authors, create_hyperlink, escape_markdown,escape_markdown_base
import pandas as pd
from typing import Dict, List, Tuple
import re

from src.core.config_loader import get_config_instance


class ReadmeGenerator:
    """README生成器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.db_manager = DatabaseManager()
        self.update_utils = get_update_file_utils()

        self.max_title_length = int(self.settings['readme'].get('max_title_length', 100))
        self.max_authors_length = int(self.settings['readme'].get('max_authors_length', 150))
        self.translation_separator=self.settings['database']['translation_separator']
        
        # 兼容配置项为 bool 或 str 的情况；确保得到布尔值
        truncate_val = self.settings['readme'].get('truncate_translation', 'true')
        try:
            self.is_truncate_translation = str(truncate_val).lower() == 'true'
        except Exception:
            self.is_truncate_translation = bool(truncate_val)
        # 兼容配置项为 bool 或 str 的情况；确保得到布尔值
        markdown_val = self.settings['readme'].get('enable_markdown', 'false')
        try:
            self.enable_markdown = str(markdown_val).lower() == 'true'
        except Exception:
            self.enable_markdown = bool(markdown_val)

    def generate_readme_tables(self) -> str:
        """生成README的论文表格部分

        现在按照一级/二级分类组织输出：
        - 一级分类（primary_category 为 None）作为分组头，前面加一个额外的标注
        - 对应的二级分类会在其下面显示（保持原有 '###' 级别），并只列出有论文的分类
        - 若一级分类本身包含论文，则在一级标题下先显示这些论文表格
        """
        # 加载数据库
        df = self.db_manager.load_database()
        # 若开启翻译截断，在生成 README 之前，确保所有字段在 "翻译分隔符" 之前截断
        if self.is_truncate_translation==True:
            if df is not None and not df.empty:
                df = self._truncate_translation_suffix(df)
        papers = self.update_utils.excel_to_paper(df, only_non_system=False, skip_invalid=True)
        # 排除冲突条目
        papers=[p for p in papers if p.conflict_marker==False]
        # 按分类分组
        papers_by_category = self._group_papers_by_category(papers)
        
        # 生成Markdown表格（按一级分类组织）
        markdown_output = ""

        cats = [c for c in self.config.get_active_categories() if c.get('enabled', True)]
        # 构建父 -> 子 的映射（主键使用父类的 unique_name）
        children_map = {}
        parents = []
        for c in cats:
            p = c.get('primary_category')
            if p is None:
                parents.append(c)
            else:
                children_map.setdefault(p, []).append(c)

        # 按 order 排序父和子（order 仍用于显示排序）
        parents = sorted(parents, key=lambda x: x.get('order', 0))
        for k in children_map:
            children_map[k] = sorted(children_map[k], key=lambda x: x.get('order', 0))

        for parent in parents:
            parent_name = parent.get('name', parent.get('unique_name'))
            parent_key = parent.get('unique_name')
            # 收集该父类以及其所有子类是否有论文
            parent_papers = papers_by_category.get(parent_key, [])
            # children_map 的键现在是父类的 unique_name
            child_list = children_map.get(parent.get('unique_name'), [])

            # 使用统一的计数函数计算论文总数（去重）
            parent_count,_ = self._get_category_paper_count_and_anchor(parent_key)

            has_any = parent_count > 0

            if not has_any:
                continue

            
            # 添加一级分类标题（包含计数）
            markdown_output += f"\n### | {parent_name} ({parent_count} papers)\n\n"

            # 若父类本身有论文，先显示父类表格
            if parent_papers:
                markdown_output += self._generate_category_table(parent_papers)

            # 依次显示每个二级分类（保持原来的 ### 级别）
            for child in child_list:
                child_name = child.get('name', child.get('unique_name'))
                child_papers = papers_by_category.get(child.get('unique_name'), [])
                if not child_papers:
                    continue
                # 子类计数
                child_count = len(child_papers)
                markdown_output += f"\n### {child_name} ({child_count} papers)\n\n"
                markdown_output += self._generate_category_table(child_papers)

        return markdown_output
    
    def _slug(self, name: str) -> str:
        """简单 slug（用于Anchor链接）"""
        s = str(name or "").strip()
        s = re.sub(r'[^A-Za-z0-9\s\-]', '', s)
        return re.sub(r'\s+', '-', s)
    
    def _get_category_paper_count_and_anchor(self, unique_name: str) -> Tuple[int,str]:
        """计算分类的论文总数（去重）
        
        自动判断是一级还是二级分类：
        - 一级分类（primary_category为None）：计算该一级分类及其所有二级分类的论文总数
        - 二级分类（有primary_category）：只计算该分类的论文总数
        
        Args:
            unique_name: 分类的 unique_name
        
        Returns:
            去重后的论文总数，对应的anchor字符串
        """
        # 自动加载论文数据
        try:
            df = self.db_manager.load_database()
            if self.is_truncate_translation and df is not None and not df.empty:
                df = self._truncate_translation_suffix(df)
            papers = self.update_utils.excel_to_paper(df, only_non_system=False, skip_invalid=True)
            papers = [p for p in papers if p.conflict_marker == False and p.show_in_readme]
            papers_by_category = self._group_papers_by_category(papers)
        except Exception:
            return 0,''
        
        # 获取分类信息
        category_config = self.config.get_category_by_unique_name(unique_name)
        if not category_config:
            return len(papers_by_category.get(unique_name, [])), ''
        
        unique_paper_keys = set()
        
        # 判断是一级还是二级分类
        primary_category = category_config.get('primary_category')
        
        if primary_category is None:
            # 一级分类：计算该分类加所有子分类的论文
            # 先计算该分类本身的论文
            for paper in papers_by_category.get(unique_name, []):
                unique_paper_keys.add(paper.get_key())
            
            # 再计算所有子分类的论文
            all_cats = [c for c in self.config.get_active_categories() if c.get('enabled', True)]
            for cat in all_cats:
                if cat.get('primary_category') == unique_name:
                    cat_unique = cat.get('unique_name')
                    if cat_unique:
                        for paper in papers_by_category.get(cat_unique, []):
                            unique_paper_keys.add(paper.get_key())

            count = len(unique_paper_keys)
            anchor = self._slug(f"|-{category_config.get('name', unique_name)} {count} papers")
        else:
            # 二级分类：只计算该分类的论文
            for paper in papers_by_category.get(unique_name, []):
                unique_paper_keys.add(paper.get_key())
            count = len(unique_paper_keys)
            anchor = self._slug(f"{category_config.get('name', unique_name)} {count} papers")
        
        return count, anchor
    
    def _generate_quick_links(self) -> str:
        """根据 categories 配置生成 Quick Links 列表（插入到表格前）

        支持两级分类：
        - 一级分类（primary_category 为 None）作为父条目列出
        - 二级分类（primary_category 指向父分类的 `unique_name`）会被放在对应一级分类下，换行并缩进显示
        """
        cats = [c for c in self.config.get_active_categories() if c.get('enabled', True)]
        if not cats:
            return ""

        # 构建父 -> 子 的映射（按 order 排序）
        children_map = {}
        parents = []
        for c in cats:
            p = c.get('primary_category')
            if p is None:
                parents.append(c)
            else:
                children_map.setdefault(p, []).append(c)

        # 按 order 排序父和子
        parents = sorted(parents, key=lambda x: x.get('order', 0))
        for k in children_map:
            children_map[k] = sorted(children_map[k], key=lambda x: x.get('order', 0))

        lines = ["### Quick Links", ""]
        for parent in parents:
            name = parent.get('name', parent.get('unique_name'))
            # 顶级分类前置两个空格以保持与历史样式一致
            # 使用统一的计数函数计算论文总数（去重）
            try:
                # 获取该父分类的论文总数（包括其子分类）
                parent_key = parent.get('unique_name')
                parent_count, anchor = self._get_category_paper_count_and_anchor(parent_key)
            except Exception:
                parent_count = 0
                anchor = ""

            lines.append(f"  - [{name}](#{anchor}) ({parent_count} papers)")
            
            # 添加二级分类（若有），每个子项换行并缩进（再加两个空格）
            for child in children_map.get(parent.get('unique_name'), []):
                child_name = child.get('name', child.get('unique_name'))
                # 子类计数（二级分类只计算自己的论文）
                try:
                    child_unique = child.get('unique_name')
                    child_count, child_anchor = self._get_category_paper_count_and_anchor(child_unique)
                except Exception:
                    child_count = 0
                    child_anchor = ""
                lines.append(f"    - [{child_name}](#{child_anchor}) ({child_count} papers)")

        return "\n".join(lines)
    
    def _group_papers_by_category(self, papers: List[Paper]) -> Dict[str, List[Paper]]:
        """按分类分组论文"""
        papers_by_category = {}
        
        for paper in papers:
            # 只处理需要在README中显示的论文
            if not paper.show_in_readme:
                continue
            # 支持多分类（分号分隔），一篇论文可出现在多个分类中
            raw_cat = paper.category or ""
            parts = [p.strip() for p in re.split(r'[;；]', raw_cat) if p.strip()]
            if not parts:
                # 空分类，放到空字符串键下
                papers_by_category.setdefault("", []).append(paper)
                continue

            for c in parts:
                papers_by_category.setdefault(c, []).append(paper)
        
        # 在每个分类内按提交时间排序（越晚提交越靠前）
        for category in papers_by_category:
            papers_by_category[category].sort(
                key=lambda x: x.submission_time if hasattr(x, 'submission_time') and x.submission_time else "",
                reverse=True
            )
        
        return papers_by_category
    
    def _generate_category_table(self, papers: List[Paper]) -> str:
        """为单个分类生成Markdown表格"""
        if not papers:
            return ""
        
        # 表格头（只保留 Title、Analogy、Pipeline、Summary）
        table_header = "| Title & Info | Analogy Summary | Pipeline | Summary |\n"
        table_separator = "|:--| :---: | :----: | :---: |\n"
        
        table_rows = ""
        
        for paper in papers:
            row = self._generate_paper_row(paper)
            table_rows += row
        
        return table_header + table_separator + table_rows
    
    def _generate_paper_row(self, paper: Paper) -> str:
        """生成单篇论文的表格行"""
        # 第1列：标题、作者、年份
        title_authors_cell = self._generate_title_authors_cell(paper)
        
        # 第2列：类比总结
        analogy_cell = self._generate_analogy_cell(paper)
        
        # 第3列：Pipeline图
        pipeline_cell = self._generate_pipeline_cell(paper)
        
        # 第4列：一句话总结（小字体显示）
        summary_cell = self._generate_summary_cell(paper)
        if summary_cell:
            summary_cell = f" <div style=\"line-height: 1.05;font-size: 0.8em\"> {summary_cell}</div>"

        return f"|{title_authors_cell}|{analogy_cell}|{pipeline_cell}|{summary_cell}|\n"
    
    def _generate_title_authors_cell(self, paper: Paper) -> str:
        """生成标题和作者单元格"""
        if not paper.title:
            return "Authors (to fill)"
        if not hasattr(self, 'enable_markdown'):
            self.enable_markdown = False
        # 清理和格式化
        # 标题不使用过度转义（避免将 '-' 或 '.' 变为 '\\-' 或 '\\.'），交给 create_hyperlink 的内部转义处理
        title = truncate_text(paper.title, self.max_title_length)
        title=self._sanitize_field(title)
        authors = self._sanitize_field(format_authors(paper.authors, self.max_authors_length))
        if self.enable_markdown:
            # 通信作者符号*必须保留
            authors=authors.replace('*', '\\' + '*')

        date = paper.date if paper.date else ""
        
        # 如果有会议信息，添加会议徽章
        conference_badge = ""
        if paper.conference:
            # 对conference值进行URL编码以处理特殊字符（如"-"）
            #conference_encoded = quote(paper.conference, safe='')
            conference_encoded =quote(paper.conference, safe='').replace('-', '--')
            conference_badge = f" [![Publish](https://img.shields.io/badge/Conference-{conference_encoded}-blue)]()"
        
        # 如果有项目链接，添加项目标：GitHub 使用 Star 徽章，否则使用简单 Project 徽章
        project_badge = ""
        if paper.project_url:
            if 'github.com' in paper.project_url:
                match = re.search(r'github\.com/([^/]+/[^/]+)', paper.project_url)
                if match:
                    repo_path = match.group(1)
                    project_badge = f'[![Star](https://img.shields.io/github/stars/{repo_path}.svg?style=social&label=Star)](https://github.com/{repo_path})'
                else:
                    project_badge = f'[![Project](https://img.shields.io/badge/Project-View-blue)]({paper.project_url})'
            else:
                project_badge = f'[![Project](https://img.shields.io/badge/Project-View-blue)]({paper.project_url})'

        # 组合（project first, then conference）
        badges = ""
        if project_badge or conference_badge:
            badges = f"{project_badge}{conference_badge}<br>"
        
        title_with_link = create_hyperlink(title, paper.paper_url)
        
        # 如果属于多个分类，在最后一行显示 multi-category：并列出所有分类（逗号分隔，每个分类链接到对应分类锚点），蓝色字体
        multi_line = ""
        try:
            raw_cat = paper.category or ""
            parts = [p.strip() for p in re.split(r'[;；]', raw_cat) if p.strip()]
            if len(parts) > 1:
                links = []
                for uname in parts:
                    # 获取分类显示名
                    display = self.config.get_category_field(uname, 'name') or uname
                    count, anchor = self._get_category_paper_count_and_anchor(uname)  # 仅用于生成锚点，自动加载数据
                    links.append(f"[{display}](#{anchor})")
                links_str = ", ".join(links)
                multi_line = f" <br> <span style=\"color:cyan\">[multi-category：{links_str}]</span>"
        except Exception:
            multi_line = ""

        return f"{badges}{title_with_link} <br> {authors} <br> {date}{multi_line}"
    
    def _generate_analogy_cell(self, paper: Paper) -> str:
        """生成类比总结单元格"""
        if not hasattr(self, 'enable_markdown'):
            self.enable_markdown = False
        if not paper.analogy_summary:
            return ""
        
        analogy = paper.analogy_summary.strip()
        analogy = self._sanitize_field(analogy)

        return analogy
    
    def _sanitize_field(self, text: str) -> str:
        """将字段文本中的回车换行规范为 HTML <br>，并转义 Markdown 特殊字符"""
        if not hasattr(self, 'enable_markdown'):
            self.enable_markdown = False
        if text is None:
            return ""
        s = str(text).strip()
        # 统一换行符并替换为 <br>，避免 Markdown 表格被换行符破坏
        s = s.replace('\r\n', '\n').replace('\r', '\n')
        if self.enable_markdown==False:
            s = escape_markdown(s)
        else:
            s = escape_markdown_base(s)
        s = s.replace('\n', '<br>')
        return s

    def _generate_summary_cell(self, paper: Paper) -> str:
        """生成一句话总结单元格（显示简短标签，悬浮或点击可查看完整内容；若存在 notes 则在下方同格显示 [notes]）"""
        import html as _html
        fields = []

        if paper.summary_motivation:
            motivation = self._sanitize_field(paper.summary_motivation)
            fields.append(f"**[{self.config.get_tag_field('summary_motivation', 'display_name')}]** {motivation}")

        if paper.summary_innovation:
            innovation = self._sanitize_field(paper.summary_innovation)
            fields.append(f"**[{self.config.get_tag_field('summary_innovation', 'display_name')}]** {innovation}")

        if paper.summary_method:
            method = self._sanitize_field(paper.summary_method)
            fields.append(f"**[{self.config.get_tag_field('summary_method', 'display_name')}]** {method}")

        if paper.summary_conclusion:
            conclusion = self._sanitize_field(paper.summary_conclusion)
            fields.append(f"**[{self.config.get_tag_field('summary_conclusion', 'display_name')}]** {conclusion}")

        if paper.summary_limitation:
            limitation = self._sanitize_field(paper.summary_limitation)
            fields.append(f"**[{self.config.get_tag_field('summary_limitation', 'display_name')}]** {limitation}")

        # 组合为完整HTML（保留换行）
        full_html = "<br>".join(fields) if fields else ""

        # notes 部分，如果存在则放在 summary 下方（同格）显示，与 summary 使用相同的 details/summary 展示方式
        notes_html = ""
        if getattr(paper, 'notes', None):
            notes_content = self._sanitize_field(paper.notes)
            notes_label = "**[notes]**"
            notes_html = f'<details><summary>{notes_label}</summary><div style="margin-top:6px">{notes_content}</div></details>'

        # 如果 summary 和 notes 都不存在，则返回空字符串
        if not full_html and not notes_html:
            return ""

        # 生成悬浮提示的纯文本（移除 <br> 并做 HTML 转义）
        tooltip_text = _html.escape(re.sub(r'<br\s*/?>', ' ', full_html or notes_content or ""))

        # 最终展示：若有 summary，则使用带标题的 details 展示 summary（小 label），并在下方添加 notes 的 details；
        # 若只有 notes，则仅显示 notes 的 details（无 summary label）
        if full_html:
            summary_label = "**[summary]**"
            summary_block = f'<details><summary title="{tooltip_text}">{summary_label}</summary><div style="margin-top:6px">{full_html}</div></details>'
            if notes_html:
                # 放在 summary 下方同格
                return summary_block + '<div style="margin-top:6px">' + notes_html + '</div>'
            else:
                return summary_block
        else:
            return notes_html
    
    def _generate_pipeline_cell(self, paper: Paper) -> str:
            """生成Pipeline图单元格（支持最多3张图片，显示在同一格内）"""
            if not paper.pipeline_image:
                return ""

            # 可能为多图（以分号分隔）
            parts = [p.strip() for p in str(paper.pipeline_image).split(';') if p.strip()]
            if not parts:
                return ""

            # 修改点：使用 ConfigLoader 获取准确的 Project Root
            # 即使 sys.path 没有设置好，ConfigLoader 也会基于文件定位
            from src.core.config_loader import get_config_instance
            project_root = str(get_config_instance().project_root)

            existing_imgs = []
            for p in parts[:3]:
                # 这里的 p 已经是 scripts/update_submission_figures.py 生成的相对路径 (e.g. "figures/abc.png")
                # 组合成绝对路径进行检查
                full_image_path = os.path.join(project_root, p)
                
                if os.path.exists(full_image_path):
                    # 只有文件存在时才放入链接
                    # 在 Markdown 中我们直接使用相对路径 p 即可，因为 README 就在根目录
                    existing_imgs.append(p)
                else:
                    # 尝试修复路径：有时候 p 可能还是文件名
                    # 如果 p 不包含 figures/ 前缀，尝试加上
                    possible_path = os.path.join("figures", os.path.basename(p))
                    full_possible_path = os.path.join(project_root, possible_path)
                    
                    if os.path.exists(full_possible_path):
                        existing_imgs.append(possible_path)
                    else:
                        print(f"警告: pipeline图片不存在: {full_image_path}")

            if not existing_imgs:
                return ""

            # 生成图片标签：如果只有一张，保留原来的大图；多张则并列显示并缩小宽度
            n = len(existing_imgs)
            if n == 1:
                return f'<img width="1200" alt="pipeline" src="{existing_imgs[0]}">' 
            else:
                # 多张图片垂直堆叠，适当缩小，保持长宽比
                imgs_html = ''.join([f'<img width="1000" style="display:block;margin:6px auto" alt="pipeline" src="{p}">' for p in existing_imgs])
                return f'<div style="display:flex;flex-direction:column;gap:6px;align-items:center">{imgs_html}</div>'
        
    def _generate_links_cell(self, paper: Paper) -> str:
            """生成链接单元格"""
            links = []
            
            if paper.paper_url:
                paper_link = create_hyperlink("Paper", paper.paper_url)
                links.append(paper_link)
            
            if paper.project_url:
                project_link = create_hyperlink("Github", paper.project_url)
                links.append(project_link)
            
            return "<br>".join(links)
    
    def update_readme_file(self, readme_path: str = None) -> bool:
        """更新README文件"""
        if readme_path is None:
            readme_path = os.path.join(os.path.dirname(__file__), '../README.md')
        
        if not os.path.exists(readme_path):
            print(f"README文件不存在: {readme_path}")
            return False
        
        # 读取原始README
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"读取README文件失败: {e}")
            return False
        
        # 生成新的表格部分
        new_tables = self.generate_readme_tables()
        # 生成 Quick Links（基于 categories 配置）
        tables_intro = self._generate_quick_links()
        
        # 查找并替换表格部分
        # 表格部分在"## Full paper list"之后开始
        start_marker = "## Full paper list"
        end_marker = "=====List End====="  # 或任何其他合适的结束标记
        
        start_index = content.find(start_marker)
        end_index = content.find(end_marker)
        
        if start_index == -1 or end_index == -1:
            print("无法找到README中的标记部分")
            return False
        # 计算表格中论文总数（不重复计数）并把数量附加到标题后
        try:
            df = self.db_manager.load_database()
            if self.is_truncate_translation and df is not None and not df.empty:
                df = self._truncate_translation_suffix(df)
            papers = self.update_utils.excel_to_paper(df, only_non_system=False, skip_invalid=True)
            papers = [p for p in papers if p.conflict_marker == False and p.show_in_readme]
            # 使用 get_key 去重（基于 doi/title）
            unique_keys = set()
            for p in papers:
                unique_keys.add(p.get_key())
            total_unique = len(unique_keys)
        except Exception:
            total_unique = 0

        before_tables = content[:start_index + len(start_marker)] + f" ({total_unique} papers)"
        after_tables = content[end_index:]
        
        # 在表格前添加说明
#         tables_intro = """
# > **Contributions**
# >
# > If you want to add your paper or update details like conference info or code URLs, please submit a pull request. You can generate the necessary markdown for each paper by filling out `generate_item.py` and running `python generate_item.py`. We greatly appreciate your contributions. Alternatively, you can email me ([Gmail](fscnkucs@gmail.com)) the links to your paper and code, and I will add your paper to the list as soon as possible.

# ---
# <p align="center">
# <img src="assets/taxonomy.png" width = "95%" alt="" align=center />
# </p>

# ### Quick Links
#   - [Make Long CoT Short](#Make-Long-CoT-Short)
#   - [Build SLM with Strong Reasoning Ability](#Build-SLM-with-Strong-Reasoning-Ability)
#   - [Let Decoding More Efficient](#Let-Decoding-More-Efficient)
#   - [Efficient Multimodal Reasoning](#efficient-agentic-reasoning)
#   - [Efficient Agentic Reasoning](#Efficient-Agentic-Reasoning)
#   - [Evaluation and Benchmarks](#Evaluation-and-Benchmarks)
#   - [Background Papers](#Background-Papers)
#   - [Competition](#Competition)
# """
        
        #new_content = before_tables + tables_intro + "\n" + new_tables + "\n" + after_tables
        # 插入 Quick Links（若有）
        if tables_intro:
            new_content = before_tables + "\n" + tables_intro + "\n\n" + new_tables + "\n" + after_tables
        else:
            new_content = before_tables +  "\n" + new_tables + "\n" + after_tables
        
        # 写入文件
        try:
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"README文件已更新: {readme_path}")
            return True
        except Exception as e:
            print(f"写入README文件失败: {e}")
            return False
    
    def _truncate_translation_suffix(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        对 DataFrame 中的文本字段进行处理：若单元格包含翻译分隔符，
        则截取该字符串之前的内容并去除末尾空白，避免 README 中出现翻译分隔及之后内容。
        仅对字符串/对象列生效，保留其它类型不变。
        """
        df = df.copy()

        def _truncate_val(v):
            if pd.isna(v):
                return ""
            try:
                s = str(v)
                if self.translation_separator in s:
                    return s.split(self.translation_separator)[0].rstrip()
                return s
            except Exception:
                return str(v)

        for col in df.columns:
            try:
                # 仅对字符串列或 object 列应用
                if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
                    df[col] = df[col].apply(_truncate_val)
            except Exception:
                # 如果某列处理失败，跳过该列以保证生成流程不中断
                continue

        return df


def main():
    """主函数"""
    print("开始生成README论文表格...")
    
    generator = ReadmeGenerator()
    
    # 生成表格
    tables = generator.generate_readme_tables()
    print("论文表格生成完成")
    
    # 更新README文件
    success = generator.update_readme_file()
    
    if success:
        print("README文件更新成功")
    else:
        print("README文件更新失败")
        # 输出生成的表格以供检查
        print("\n生成的表格内容：")
        print(tables)


if __name__ == "__main__":
    main()