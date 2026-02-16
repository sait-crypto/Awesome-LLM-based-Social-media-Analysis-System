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

    def generate_readme_tables(self) -> str:
        """生成README的论文表格部分"""
        # 1. 加载数据 (List[Paper])
        success,papers = self.db_manager.load_database()
        if not success:
            print("加载数据库失败，无法生成README表格")
            return ""
        
        # 2. 预处理：截断翻译，过滤不显示的
        display_papers = []
        for p in papers:
            if not p.show_in_readme or p.conflict_marker:
                continue
            
            # 截断翻译逻辑
            if self.is_truncate_translation:
                self._truncate_translation_in_paper(p)
                
            display_papers.append(p)
            
        # 3. 分组
        papers_by_category = self._group_papers_by_category(display_papers)
        
        # 4. 生成 Markdown
        markdown_output = ""
        cats = [c for c in self.config.get_active_categories() if c.get('enabled', True)]
        
        # 构建父子关系
        children_map = {}
        parents = []
        for c in cats:
            p = c.get('primary_category')
            if p is None:
                parents.append(c)
            else:
                children_map.setdefault(p, []).append(c)

        # 排序
        parents = sorted(parents, key=lambda x: x.get('order', 0))
        for k in children_map:
            children_map[k] = sorted(children_map[k], key=lambda x: x.get('order', 0))

        # 遍历生成
        for parent in parents:
            parent_name = parent.get('name', parent.get('unique_name'))
            parent_key = parent.get('unique_name')
            
            # 计算数量
            parent_count, _ = self._get_category_paper_count_and_anchor(parent_key, display_papers)
            
            if parent_count == 0:
                continue

            markdown_output += f"\n### | {parent_name} ({parent_count} papers)\n\n"

            # 父类本身的论文
            parent_papers = papers_by_category.get(parent_key, [])
            if parent_papers:
                markdown_output += self._generate_category_table(parent_papers)

            # 子类
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
            parts = [x.strip() for x in re.split(r'[;；]', raw) if x.strip()]
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
        col2 = self._sanitize_field(paper.analogy_summary)
        col3 = self._generate_pipeline_cell(paper)
        col4 = self._generate_summary_cell(paper)
        if col4:
            col4 = f" <div style=\"line-height: 1.05;font-size: 0.8em\"> {col4}</div>"
        return f"|{col1}|{col2}|{col3}|{col4}|\n"

    def _generate_title_authors_cell(self, paper: Paper) -> str:
        # ===== 恢复：标题作者单元格完整逻辑 =====
        if not paper.title:
            return "Authors (to fill)"
        # 清理和格式化
        title = truncate_text(paper.title, self.max_title_length)
        title = self._sanitize_field(title)
        authors = self._sanitize_field(format_authors(paper.authors, self.max_authors_length))
        if self.enable_markdown:
            # 通信作者符号*必须保留
            authors = authors.replace('*', '\\' + '*')

        date = paper.date if paper.date else ""
        
        # 如果有会议信息，添加会议徽章
        conference_badge = ""
        if paper.conference:
            conference_encoded = quote(paper.conference, safe='').replace('-', '--')
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
                    count, anchor = self._get_category_paper_count_and_anchor(uname, [])  # 仅用于生成锚点，传入空列表即可
                    links.append(f"[{display}](#{anchor})")
                links_str = ", ".join(links)
                multi_line = f" <br> <span style=\"color:cyan\">[multi-category：{links_str}]</span>"
        except Exception:
            multi_line = ""

        return f"{badges}{title_with_link} <br> {authors} <br> {date}{multi_line}"

    def _generate_pipeline_cell(self, paper: Paper) -> str:
        """生成Pipeline图单元格（支持最多3张图片，显示在同一格内）"""
        # ===== 恢复：Pipeline 图片展示完整逻辑 =====
        if not paper.pipeline_image:
            return ""

        # 可能为多图（以分号分隔）
        parts = [p.strip() for p in str(paper.pipeline_image).split(';') if p.strip()]
        if not parts:
            return ""

        # 使用 ConfigLoader 获取准确的 Project Root
        project_root = str(self.config.project_root)

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
        # 这里的 count 逻辑需要优化，为了性能
        # 简单实现：重新遍历
        # 实际生成时需要精确的 anchor
        
        # 1. 找出该分类下的所有论文 (包含子类)
        cat_config = self.config.get_category_by_unique_name(unique_name)
        if not cat_config: return 0, ""
        
        target_cats = {unique_name}
        if cat_config.get('primary_category') is None:
            # 是父类，包含子类
            for c in self.config.get_active_categories():
                if c.get('primary_category') == unique_name:
                    target_cats.add(c['unique_name'])
        
        count = 0
        for p in all_papers:
            p_cats = set([x.strip() for x in re.split(r'[;；]', p.category or "")])
            if not p_cats.isdisjoint(target_cats):
                count += 1
                
        # 构造 Anchor 字符串
        prefix = "|-" if cat_config.get('primary_category') is None else ""
        raw_anchor = f"{prefix}{cat_config.get('name', unique_name)} {count} papers"
        return count, self._slug(raw_anchor)

    def _generate_quick_links(self) -> str:
        """根据 categories 配置生成 Quick Links 列表（插入到表格前）

        支持两级分类：
        - 一级分类（primary_category 为 None）作为父条目列出
        - 二级分类（primary_category 指向父分类的 `unique_name`）会被放在对应一级分类下，换行并缩进显示
        """
        # ===== 恢复：Quick Links 生成完整逻辑 =====
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
                # 加载论文数据用于计数
                papers = self.db_manager.load_database()
                valid_papers = [p for p in papers if p.show_in_readme and not p.conflict_marker]
                parent_count, anchor = self._get_category_paper_count_and_anchor(parent_key, valid_papers)
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
                    child_count, child_anchor = self._get_category_paper_count_and_anchor(child_unique, valid_papers)
                except Exception:
                    child_count = 0
                    child_anchor = ""
                lines.append(f"    - [{child_name}](#{child_anchor}) ({child_count} papers)")

        return "\n".join(lines)

    def update_readme_file(self) -> bool:
        """更新README文件"""
        readme_path = os.path.join(self.config.project_root, 'README.md')
        
        # ===== 恢复：README文件操作相关输出 =====
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
            papers = self.db_manager.load_database()
            valid_papers = [p for p in papers if p.show_in_readme and not p.conflict_marker]
            # 使用 get_key 去重（基于 doi/title）
            unique_keys = set()
            for p in valid_papers:
                unique_keys.add(p.get_key())
            total_unique = len(unique_keys)
        except Exception:
            total_unique = 0

        before_tables = content[:start_index + len(start_marker)] + f" ({total_unique} papers)"
        after_tables = content[end_index:]
        
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

# ===== 恢复：主函数及原有控制台输出 =====
def main():
    """主函数"""
    print("开始生成README论文表格...")
    
    generator = ReadmeGenerator()
    
    
    # 更新README文件
    success = generator.update_readme_file()
    
    if success:
        print("README文件更新成功")
    else:
        print("README文件更新失败")


if __name__ == "__main__":
    main()