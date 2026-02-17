"""
项目入口1：从核心数据库生成README论文表格部分
"""
import os
import sys
import re
from typing import Dict, List, Tuple
from urllib.parse import quote

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.database_manager import DatabaseManager
from src.core.database_model import Paper
from src.core.config_loader import get_config_instance
from src.utils import truncate_text, format_authors, create_hyperlink, escape_markdown, escape_markdown_base

class ReadmeGenerator:
    """README生成器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = self.config.settings
        self.db_manager = DatabaseManager()
        self.project_root = str(self.config.project_root)
        self.assets_dir = self.settings['paths'].get('assets_dir', 'assets/').replace('\\', '/').rstrip('/')
        self.legacy_figure_dir = self.settings['paths'].get('figure_dir', 'figures/').replace('\\', '/').rstrip('/')
        self._current_display_papers: List[Paper] = []
        
        self.max_title_length = int(self.settings['readme'].get('max_title_length', 100))
        self.max_authors_length = int(self.settings['readme'].get('max_authors_length', 150))
        self.translation_separator = self.settings['database'].get('translation_separator', '[翻译]')
        
        # ===== 恢复：配置项兼容逻辑 =====
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

    def _load_display_papers(self) -> Tuple[bool, List[Paper]]:
        """加载并预处理用于 README 展示的论文列表"""
        success, papers = self.db_manager.load_database()
        if not success:
            return False, []

        display_papers = []
        for paper in papers:
            if not paper.show_in_readme or paper.conflict_marker:
                continue
            if self.is_truncate_translation:
                self._truncate_translation_in_paper(paper)
            display_papers.append(paper)
        return True, display_papers

    def generate_readme_tables(self) -> str:
        """生成README的论文表格部分"""
        success, display_papers = self._load_display_papers()
        self._current_display_papers = display_papers
        if not success:
            print("加载数据库失败，无法生成README表格")
            return ""

        papers_by_category = self._group_papers_by_category(display_papers)

        markdown_output = ""
        cats = [c for c in self.config.get_active_categories() if c.get('enabled', True)]

        children_map = {}
        parents = []
        for c in cats:
            p = c.get('primary_category')
            if p is None:
                parents.append(c)
            else:
                children_map.setdefault(p, []).append(c)

        parents = sorted(parents, key=lambda x: x.get('order', 0))
        for k in children_map:
            children_map[k] = sorted(children_map[k], key=lambda x: x.get('order', 0))

        for parent in parents:
            parent_name = parent.get('name', parent.get('unique_name'))
            parent_key = parent.get('unique_name')

            parent_count, _ = self._get_category_paper_count_and_anchor(parent_key, display_papers)

            if parent_count == 0:
                continue

            markdown_output += f"\n### | {parent_name} ({parent_count} papers)\n\n"

            parent_papers = papers_by_category.get(parent_key, [])
            if parent_papers:
                markdown_output += self._generate_category_table(parent_papers)

            child_list = children_map.get(parent_key, [])
            for child in child_list:
                child_name = child.get('name', child.get('unique_name'))
                child_key = child.get('unique_name')
                child_papers = papers_by_category.get(child_key, [])

                if child_papers:
                    markdown_output += f"\n### {child_name} ({len(child_papers)} papers)\n\n"
                    markdown_output += self._generate_category_table(child_papers)

        return markdown_output

    def _truncate_translation_in_paper(self, paper: Paper):
        """对 Paper 对象中的所有字符串字段执行翻译截断"""
        sep = self.translation_separator
        for field in paper.__dataclass_fields__:
            val = getattr(paper, field)
            if isinstance(val, str) and sep in val:
                setattr(paper, field, val.split(sep)[0].rstrip())

    def _group_papers_by_category(self, papers: List[Paper]) -> Dict[str, List[Paper]]:
        grouped = {}
        for p in papers:
            # 支持多分类
            raw = p.category or ""
            parts = [x.strip() for x in str(raw).split('|') if x.strip()]
            if not parts:
                grouped.setdefault("", []).append(p)
            else:
                for cat in parts:
                    grouped.setdefault(cat, []).append(p)
        
        # 排序：按提交时间倒序
        for k in grouped:
            grouped[k].sort(key=lambda x: x.submission_time or "", reverse=True)
            
        return grouped

    def _generate_category_table(self, papers: List[Paper]) -> str:
        if not papers: return ""
        header = "| Title & Info | Analogy Summary | Pipeline | Summary |\n"
        sep = "|:--| :---: | :----: | :---: |\n"
        rows = "".join([self._generate_paper_row(p) for p in papers])
        return header + sep + rows

    def _generate_paper_row(self, paper: Paper) -> str:
        col1 = self._generate_title_authors_cell(paper)
        col2 = self._generate_analogy_cell(paper)
        col3 = self._generate_pipeline_cell(paper)
        col4 = self._generate_summary_cell(paper)
        if col4:
            col4 = f" <div style=\"line-height: 1.05;font-size: 0.8em\"> {col4}</div>"
        return f"|{col1}|{col2}|{col3}|{col4}|\n"

    def _generate_analogy_cell(self, paper: Paper) -> str:
        if not paper.analogy_summary:
            return ""
        return self._sanitize_field(paper.analogy_summary)

    def _generate_title_authors_cell(self, paper: Paper) -> str:
        if not paper.title:
            return "Authors (to fill)"

        title = truncate_text(paper.title, self.max_title_length)
        title = self._sanitize_field(title)
        authors = self._sanitize_field(format_authors(paper.authors, self.max_authors_length))
        if self.enable_markdown:
            authors = authors.replace('*', '\\' + '*')

        date = paper.date if paper.date else ""

        conference_badge = ""
        if paper.conference:
            conference_encoded = quote(paper.conference, safe='').replace('-', '--')
            conference_badge = f" [![Publish](https://img.shields.io/badge/Conference-{conference_encoded}-blue)]()"

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

        badges = ""
        if project_badge or conference_badge:
            badges = f"{project_badge}{conference_badge}<br>"

        title_with_link = create_hyperlink(title, paper.paper_url)

        multi_line = ""
        try:
            raw_cat = paper.category or ""
            parts = [p.strip() for p in str(raw_cat).split('|') if p.strip()]
            if len(parts) > 1:
                links = []
                for uname in parts:
                    display = self.config.get_category_field(uname, 'name') or uname
                    _, anchor = self._get_category_paper_count_and_anchor(uname, self._current_display_papers)
                    links.append(f"[{display}](#{anchor})")
                links_str = ", ".join(links)
                multi_line = f" <br> <span style=\"color:cyan\">[multi-category：{links_str}]</span>"
        except Exception:
            multi_line = ""

        return f"{badges}{title_with_link} <br> {authors} <br> {date}{multi_line}"

    def _generate_pipeline_cell(self, paper: Paper) -> str:
        """生成Pipeline图单元格（支持最多3张图片，显示在同一格内）"""
        if not paper.pipeline_image:
            return ""

        parts = [p.strip() for p in str(paper.pipeline_image).split('|') if p.strip()]
        if not parts:
            return ""

        existing_imgs = []
        for raw_path in parts[:3]:
            normalized = raw_path.replace('\\', '/')
            full_path = normalized if os.path.isabs(normalized) else os.path.join(self.project_root, normalized)
            if os.path.exists(full_path):
                if os.path.isabs(normalized):
                    try:
                        rel_path = os.path.relpath(full_path, self.project_root).replace('\\', '/')
                    except Exception:
                        rel_path = normalized
                    existing_imgs.append(rel_path)
                else:
                    existing_imgs.append(normalized)
            else:
                print(f"警告: pipeline图片不存在: {raw_path}")

        if not existing_imgs:
            return ""

        n = len(existing_imgs)
        if n == 1:
            return f'<img width="1200" alt="pipeline" src="{existing_imgs[0]}">' 
        else:
            imgs_html = ''.join([f'<img width="1000" style="display:block;margin:6px auto" alt="pipeline" src="{p}">' for p in existing_imgs])
            return f'<div style="display:flex;flex-direction:column;gap:6px;align-items:center">{imgs_html}</div>'

    def _generate_summary_cell(self, paper: Paper) -> str:
        # 复用原有逻辑
        import html as _html
        fields = []
        tags_map = {
            'summary_motivation': 'motivation',
            'summary_innovation': 'innovation',
            'summary_method': 'method',
            'summary_conclusion': 'conclusion',
            'summary_limitation': 'limitation'
        }
        
        for k, name in tags_map.items():
            val = getattr(paper, k, "")
            if val:
                disp = self.config.get_tag_field(k, 'display_name') or name
                fields.append(f"**[{disp}]** {self._sanitize_field(val)}")
        
        full_html = "<br>".join(fields)
        
        notes_html = ""
        if paper.notes:
            notes_html = f'<details><summary>**[notes]**</summary><div style="margin-top:6px">{self._sanitize_field(paper.notes)}</div></details>'
            
        if not full_html and not notes_html: return ""
        
        tooltip = _html.escape(re.sub(r'<br\s*/?>', ' ', full_html))
        if full_html:
            blk = f'<details><summary title="{tooltip}">**[summary]**</summary><div style="margin-top:6px">{full_html}</div></details>'
            if notes_html: return blk + '<div style="margin-top:6px">' + notes_html + '</div>'
            return blk
        return notes_html

    def _sanitize_field(self, text: str) -> str:
        if not text: return ""
        s = str(text).strip().replace('\r\n', '\n').replace('\r', '\n')
        if not self.enable_markdown:
            s = escape_markdown(s)
        else:
            s = escape_markdown_base(s)
        return s.replace('\n', '<br>')

    def _slug(self, name: str) -> str:
        s = str(name or "").strip()
        s = re.sub(r'[^A-Za-z0-9\s\-]', '', s)
        return re.sub(r'\s+', '-', s)

    def _get_category_paper_count_and_anchor(self, unique_name: str, all_papers: List[Paper]) -> Tuple[int, str]:
        cat_config = self.config.get_category_by_unique_name(unique_name)
        if not cat_config:
            return 0, ""

        target_cats = {unique_name}
        if cat_config.get('primary_category') is None:
            for c in self.config.get_active_categories():
                if c.get('primary_category') == unique_name:
                    target_cats.add(c['unique_name'])

        count = 0
        for p in all_papers:
            p_cats = set([x.strip() for x in str(p.category or "").split('|')])
            if not p_cats.isdisjoint(target_cats):
                count += 1

        prefix = "|-" if cat_config.get('primary_category') is None else ""
        raw_anchor = f"{prefix}{cat_config.get('name', unique_name)} {count} papers"
        return count, self._slug(raw_anchor)

    def _generate_quick_links(self) -> str:
        """根据 categories 配置生成 Quick Links 列表（插入到表格前）

        支持两级分类：
        - 一级分类（primary_category 为 None）作为父条目列出
        - 二级分类（primary_category 指向父分类的 `unique_name`）会被放在对应一级分类下，换行并缩进显示
        """
        success, display_papers = self._load_display_papers()
        if success:
            self._current_display_papers = display_papers
        cats = [c for c in self.config.get_active_categories() if c.get('enabled', True)]
        if not cats:
            return ""

        children_map = {}
        parents = []
        for c in cats:
            p = c.get('primary_category')
            if p is None:
                parents.append(c)
            else:
                children_map.setdefault(p, []).append(c)

        parents = sorted(parents, key=lambda x: x.get('order', 0))
        for k in children_map:
            children_map[k] = sorted(children_map[k], key=lambda x: x.get('order', 0))

        lines = ["### Quick Links", ""]
        for parent in parents:
            name = parent.get('name', parent.get('unique_name'))
            try:
                parent_key = parent.get('unique_name')
                parent_count, anchor = self._get_category_paper_count_and_anchor(parent_key, display_papers)
            except Exception:
                parent_count = 0
                anchor = ""

            lines.append(f"  - [{name}](#{anchor}) ({parent_count} papers)")
            
            for child in children_map.get(parent.get('unique_name'), []):
                child_name = child.get('name', child.get('unique_name'))
                try:
                    child_unique = child.get('unique_name')
                    child_count, child_anchor = self._get_category_paper_count_and_anchor(child_unique, display_papers)
                except Exception:
                    child_count = 0
                    child_anchor = ""
                lines.append(f"    - [{child_name}](#{child_anchor}) ({child_count} papers)")

        return "\n".join(lines)

    def update_readme_file(self) -> bool:
        """更新README文件"""
        readme_path = os.path.join(self.config.project_root, 'README.md')

        if not os.path.exists(readme_path):
            print(f"README文件不存在: {readme_path}")
            return False

        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"读取README文件失败: {e}")
            return False

        new_tables = self.generate_readme_tables()
        tables_intro = self._generate_quick_links()

        start_marker = "## Full paper list"
        end_marker = "=====List End====="

        start_index = content.find(start_marker)
        end_index = content.find(end_marker)

        if start_index == -1 or end_index == -1:
            print("无法找到README中的标记部分")
            return False

        try:
            success, valid_papers = self._load_display_papers()
            if not success:
                valid_papers = []
            self._current_display_papers = valid_papers
            unique_keys = set()
            for p in valid_papers:
                unique_keys.add(p.get_key())
            total_unique = len(unique_keys)
        except Exception:
            total_unique = 0

        before_tables = content[:start_index + len(start_marker)] + f" ({total_unique} papers)"
        after_tables = content[end_index:]

        if tables_intro:
            new_content = before_tables + "\n" + tables_intro + "\n\n" + new_tables + "\n" + after_tables
        else:
            new_content = before_tables +  "\n" + new_tables + "\n" + after_tables

        try:
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"README文件已更新: {readme_path}")
            return True
        except Exception as e:
            print(f"写入README文件失败: {e}")
            return False

def main():
    """主函数"""
    print("开始生成README论文表格...")

    generator = ReadmeGenerator()

    tables = generator.generate_readme_tables()
    print("论文表格生成完成")

    # 更新README文件
    success = generator.update_readme_file()

    if success:
        print("README文件更新成功")
    else:
        print("README文件更新失败")
        print("\n生成的表格内容：")
        print(tables)


if __name__ == "__main__":
    main()