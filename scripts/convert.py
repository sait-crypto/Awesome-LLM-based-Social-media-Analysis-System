"""
项目入口1：从核心excel生成readme论文表格部分
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database_manager import DatabaseManager
from core.database_model import Paper
from scripts.utils import truncate_text, format_authors, create_hyperlink, escape_markdown
import pandas as pd
from typing import Dict, List

from scripts.core.config_loader import get_config_instance


class ReadmeGenerator:
    """README生成器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.db_manager = DatabaseManager()
        self.max_title_length = int(self.settings['readme'].get('max_title_length', 100))
        self.max_authors_length = int(self.settings['readme'].get('max_authors_length', 150))
    
    def generate_readme_tables(self) -> str:
        """生成README的论文表格部分"""
        # 加载数据库
        df = self.db_manager.load_database()
        # 在生成 README 之前，确保所有字段在 "[翻译]" 之前截断
        if df is not None and not df.empty:
            df = self._truncate_translation_suffix(df)
        papers = self.db_manager.get_papers_from_dataframe(df)
        
        # 按分类分组
        papers_by_category = self._group_papers_by_category(papers)
        
        # 生成Markdown表格
        markdown_output = ""
        
        for category in self.config.get_active_categories():
            category_name = category['name']
            category_papers = papers_by_category.get(category['unique_name'], [])
            
            if not category_papers:
                continue
            
            # 添加分类标题
            markdown_output += f"\n### {category_name}\n\n"
            
            # 生成表格
            markdown_output += self._generate_category_table(category_papers)
        
        return markdown_output
    
    def _group_papers_by_category(self, papers: List[Paper]) -> Dict[str, List[Paper]]:
        """按分类分组论文"""
        papers_by_category = {}
        
        for paper in papers:
            # 只处理需要在README中显示的论文
            if not paper.show_in_readme:
                continue
            
            category = paper.category
            if category not in papers_by_category:
                papers_by_category[category] = []
            
            papers_by_category[category].append(paper)
        
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
        
        # 表格头
        table_header = "| Title & Authors | Analogy Summary | Summary | Pipeline | Links |\n"
        table_separator = "|:--| :----: | :---: | :---: | :---: |\n"
        
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
        
        # 第3列：一句话总结（5个字段）
        summary_cell = self._generate_summary_cell(paper)
        
        # 第4列：Pipeline图
        pipeline_cell = self._generate_pipeline_cell(paper)
        
        # 第5列：链接
        links_cell = self._generate_links_cell(paper)
        
        return f"|{title_authors_cell}|{analogy_cell}|{summary_cell}|{pipeline_cell}|{links_cell}|\n"
    
    def _generate_title_authors_cell(self, paper: Paper) -> str:
        """生成标题和作者单元格"""
        # 清理和格式化
        title = escape_markdown(truncate_text(paper.title, self.max_title_length))
        authors = escape_markdown(format_authors(paper.authors, self.max_authors_length))
        date = paper.date if paper.date else ""
        
        # 如果有会议信息，添加会议徽章
        conference_badge = ""
        if paper.conference:
            conference_badge = f" [![Publish](https://img.shields.io/badge/Conference-{paper.conference.replace(' ', '_')}-blue)]()"
        
        # 如果有项目链接，添加GitHub星星徽章
        github_badge = ""
        if paper.project_url and 'github.com' in paper.project_url:
            # 提取GitHub仓库路径
            import re
            match = re.search(r'github\.com/([^/]+/[^/]+)', paper.project_url)
            if match:
                repo_path = match.group(1)
                github_badge = f'[![Star](https://img.shields.io/github/stars/{repo_path}.svg?style=social&label=Star)](https://github.com/{repo_path})'
        
        # 组合
        badges = ""
        if github_badge or conference_badge:
            badges = f"{github_badge}{conference_badge}<br>"
        
        title_with_link = create_hyperlink(title, paper.paper_url)
        
        return f"{badges}{title_with_link} <br> {authors} <br> {date}"
    
    def _generate_analogy_cell(self, paper: Paper) -> str:
        """生成类比总结单元格"""
        if not paper.analogy_summary:
            return ""
        
        
        analogy = paper.analogy_summary.strip()
        return escape_markdown(analogy)
    
    def _generate_summary_cell(self, paper: Paper) -> str:
        """生成一句话总结单元格（5个字段）"""
        fields = []
        
        if paper.summary_motivation:
            motivation = paper.summary_motivation.strip()
            fields.append(f"{self.config.get_tag_field('summary_motivation', 'display_name')}: {escape_markdown(motivation)}")
        
        if paper.summary_innovation:
            innovation = paper.summary_innovation.strip()
            fields.append(f"{self.config.get_tag_field('summary_innovation', 'display_name')}: {escape_markdown(innovation)}")
        
        if paper.summary_method:
            method = paper.summary_method.strip()
            fields.append(f"{self.config.get_tag_field('summary_method', 'display_name')}: {escape_markdown(method)}")
        
        if paper.summary_conclusion:
            conclusion = paper.summary_conclusion.strip()
            fields.append(f"{self.config.get_tag_field('summary_conclusion', 'display_name')}: {escape_markdown(conclusion)}")
        
        if paper.summary_limitation:
            limitation = paper.summary_limitation.strip()
            fields.append(f"{self.config.get_tag_field('summary_limitation', 'display_name')}: {escape_markdown(limitation)}")
        
        if not fields:
            return ""
        
        return "<br>".join(fields)
    
    def _generate_pipeline_cell(self, paper: Paper) -> str:
        """生成Pipeline图单元格"""
        if not paper.pipeline_image:
            return ""
        
        # 检查图片文件是否存在
        image_path = paper.pipeline_image
        if not os.path.isabs(image_path):
            # 相对路径，转换为相对于README的路径
            root_dir = os.path.dirname(os.path.dirname(__file__))
            image_path = os.path.join(root_dir, image_path)
        
        if os.path.exists(image_path):
            # 生成Markdown图片标签
            # 使用相对路径（相对于README.md）
            relative_path = os.path.relpath(image_path, start=os.path.dirname(__file__) + "/..")
            return f'<img width="1002" alt="image" src="{relative_path}">'
        
        return ""
    
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
        
        # 查找并替换表格部分
        # 表格部分在"## Full paper list"之后开始
        start_marker = "## Full paper list"
        end_marker = "=====List End====="  # 或任何其他合适的结束标记
        
        start_index = content.find(start_marker)
        end_index = content.find(end_marker)
        
        if start_index == -1 or end_index == -1:
            print("无法找到README中的标记部分")
            return False
        
        # 构建新内容
        before_tables = content[:start_index + len(start_marker)]
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
        对 DataFrame 中的文本字段进行处理：若单元格包含 "[翻译]" 字符串，
        则截取该字符串之前的内容并去除末尾空白，避免 README 中出现翻译分隔及之后内容。
        仅对字符串/对象列生效，保留其它类型不变。
        """
        df = df.copy()

        def _truncate_val(v):
            import pandas as _pd
            if _pd.isna(v):
                return ""
            try:
                s = str(v)
                if "[翻译]" in s:
                    return s.split("[翻译]")[0].rstrip()
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