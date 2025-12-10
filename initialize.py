# initialize.py
"""
初始化脚本
在首次运行时设置项目
"""

import os
import shutil
import pandas as pd
from openpyxl import Workbook

def initialize_project():
    """初始化项目"""
    print("正在初始化论文收集系统...")
    
    # 1. 创建目录结构
    directories = [
        "config",
        "master/core",
        "master/backups",
        "resources/figures",
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✓ 创建目录: {directory}")
    
    # 2. 创建核心Excel数据库（如果不存在）
    core_excel = "master/paper_database.xlsx"
    if not os.path.exists(core_excel):
        # 创建空的Excel文件
        wb = Workbook()
        ws = wb.active
        
        # 添加标题行
        from config.tag_config import TAGS_CONFIG
        headers = [tag['table_name'] for tag in TAGS_CONFIG['tags'] if tag['enabled'] or tag['immutable']]
        ws.append(headers)
        
        wb.save(core_excel)
        print(f"✓ 创建核心数据库: {core_excel}")
    
    # 3. 创建示例配置文件
    config_files = {
        "config/tag_config.py": """# 标签配置 - 请根据需要进行修改
TAGS_CONFIG = {
    "config_version": "1.0",
    "last_updated": "2025-01-01",
    "tags": [...]
}""",
        
        "config/categories_config.py": """# 分类配置 - 请根据需要进行修改
CATEGORIES_CONFIG = {
    "config_version": "1.0",
    "last_updated": "2025-01-01",
    "categories": [...]
}""",
        
        "config/setting.config": """# 系统设置
[paths]
core_excel = master/paper_database.xlsx
update_excel = submit_template.xlsx
update_json = submit_template.json
backup_dir = master/backups/

[ai]
enable_ai_generation = false
deepseek_api_key_path = path/to/your/api_key.txt

[excel]
password_path = path/to/your/password.txt

[database]
default_contributor = anonymous
conflict_marker = [冲突标记]

[readme]
max_title_length = 100
max_authors_length = 150
date_format = YYYY-MM-DD"""
    }
    
    for filepath, content in config_files.items():
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ 创建配置文件: {filepath}")
    
    # 4. 创建README模板
    if not os.path.exists("README.md"):
        readme_content = """# Efficient Reasoning Models: A Survey

## 项目说明

这是一个自动化论文收集系统，用于管理高效推理模型领域的学术论文。

## 使用方法

1. **提交论文**: 运行 `python submit.py` 启动图形界面
2. **更新数据库**: 运行 `python master/update.py` 处理更新文件
3. **生成README**: 运行 `python master/convert.py` 从数据库生成README

## 论文列表

<!-- 论文列表将由系统自动生成 -->

## 贡献指南

请参考项目文档了解如何贡献论文。

## 许可证

MIT License
"""
        
        with open("README.md", 'w', encoding='utf-8') as f:
            f.write(readme_content)
        print("✓ 创建README.md")
    
    print("\n✅ 项目初始化完成!")
    print("\n下一步:")
    print("1. 修改配置文件 (config/ 目录下)")
    print("2. 运行 python submit.py 测试提交功能")
    print("3. 添加论文到 submit_template.json")
    print("4. 运行 python master/update.py 更新数据库")

if __name__ == "__main__":
    initialize_project()

