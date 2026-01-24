"""
提交验证脚本
功能：
1. 验证提交的 Excel/JSON 更新文件内容
   - 对比 main 分支的原始模板，排除未修改的占位条目
   - 使用 validate_paper_fields 验证新增条目的字段合法性
2. 验证 figures 文件夹下的图片格式
"""

import os
import sys
import shutil
import subprocess
import pandas as pd
from typing import List, Tuple

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config_loader import get_config_instance
from src.core.update_file_utils import get_update_file_utils
from src.core.database_model import Paper, is_duplicate_paper

# 初始化配置和工具
config = get_config_instance()
update_utils = get_update_file_utils()

# 路径配置
UPDATE_EXCEL = config.settings['paths']['update_excel']
UPDATE_JSON = config.settings['paths']['update_json']
FIGURE_DIR = config.settings['paths']['figure_dir']
TEMP_DIR = "temp_validation"

def get_original_file(filepath: str, output_path: str):
    """
    从 origin/main 获取原始文件的内容并保存到临时路径
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 使用 git show 获取 main 分支的文件版本
        # 注意：GitHub Action 中 checkout 需要设置 fetch-depth: 0 才能访问 origin/main
        cmd = ["git", "show", f"origin/main:{filepath}"]
        
        with open(output_path, "wb") as f:
            subprocess.run(cmd, stdout=f, check=True, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        # 如果文件在 main 中不存在（可能是新添加的文件），则视为原始文件为空
        print(f"Info: File {filepath} not found in origin/main. Assuming empty baseline.")
        return False
    except Exception as e:
        print(f"Warning: Failed to fetch original file {filepath}: {e}")
        return False

def validate_papers_in_file(file_type: str, submitted_path: str, original_path: str) -> int:
    """
    验证文件中的论文
    返回: 有效且实质性新增的论文数量
    """
    if not os.path.exists(submitted_path):
        return 0

    print(f"\n--- Validating {file_type.upper()}: {submitted_path} ---")

    # 1. 加载提交的论文
    try:
        if file_type == 'excel':
            submitted_papers = update_utils.load_papers_from_excel(submitted_path, skip_invalid=False)
        else:
            submitted_papers = update_utils.load_papers_from_json(submitted_path, skip_invalid=False)
    except Exception as e:
        print(f"Error: Failed to load submitted file: {e}")
        return 0

    if not submitted_papers:
        print("Info: File contains no paper entries.")
        return 0

    # 2. 加载原始模板中的论文（作为基准，用于排除未修改的行）
    original_papers = []
    if os.path.exists(original_path):
        try:
            if file_type == 'excel':
                original_papers = update_utils.load_papers_from_excel(original_path, skip_invalid=False)
            else:
                original_papers = update_utils.load_papers_from_json(original_path, skip_invalid=False)
        except Exception:
            pass # 原始文件可能损坏或为空，不影响后续逻辑

    valid_new_count = 0
    
    # 3. 逐条验证
    for i, paper in enumerate(submitted_papers):
        paper_idx_str = f"Paper #{i+1} (Title: {paper.title[:30]}...)"
        
        # A. 查重检测 (Check against template)
        # 使用 complete_compare=True 检测是否与模板中的占位符完全一致
        is_template_duplicate, _ = is_duplicate_paper(original_papers, paper, complete_compare=True)
        
        if is_template_duplicate:
            # print(f"Skipping {paper_idx_str}: Identical to template/repository version.")
            continue
        
        # B. 字段验证 (Validate fields)
        # Requirement 1: 使用 validate_paper_fields(no_normalize=True)
        is_valid, errors, _ = paper.validate_paper_fields(
            config, 
            check_required=True, 
            check_non_empty=True, 
            no_normalize=True
        )

        if not is_valid:
            print(f"Error in {paper_idx_str}:")
            for err in errors:
                print(f"  - {err}")
            # 这里我们视作验证失败，不通过 CI
            # 如果你希望容忍部分错误，可以修改逻辑
            return -1 # 返回负数表示发现致命错误
        
        # 如果通过了查重且字段验证有效
        print(f"Create/Update Detected: {paper_idx_str} - VALID")
        valid_new_count += 1

    return valid_new_count

def validate_figures_folder():
    """
    验证 figures 文件夹中的文件格式
    """
    if not os.path.exists(FIGURE_DIR):
        return True

    print(f"\n--- Validating Figures in {FIGURE_DIR} ---")
    valid_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
    has_error = False

    for root, _, files in os.walk(FIGURE_DIR):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in valid_extensions:
                # 忽略 .gitkeep 等文件
                if file == '.gitkeep': continue
                print(f"Error: Invalid file format in figures folder: {file}")
                has_error = True
    
    return not has_error

def main():
    # 清理并创建临时目录
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    try:
        # 定义原始文件路径
        original_excel_path = os.path.join(TEMP_DIR, "original_template.xlsx")
        original_json_path = os.path.join(TEMP_DIR, "original_template.json")

        # 1. 获取基准文件
        get_original_file(UPDATE_EXCEL, original_excel_path)
        get_original_file(UPDATE_JSON, original_json_path)

        # 2. 验证 Excel
        excel_result = validate_papers_in_file('excel', UPDATE_EXCEL, original_excel_path)
        if excel_result < 0:
            print("❌ Excel Validation Failed: Invalid entries found.")
            sys.exit(1)

        # 3. 验证 JSON
        json_result = validate_papers_in_file('json', UPDATE_JSON, original_json_path)
        if json_result < 0:
            print("❌ JSON Validation Failed: Invalid entries found.")
            sys.exit(1)

        # 4. 验证 Figures
        if not validate_figures_folder():
            print("❌ Figures Validation Failed.")
            sys.exit(1)

        total_valid_new_papers = excel_result + json_result

        if total_valid_new_papers > 0:
            print(f"\n✅ Validation Passed! Found {total_valid_new_papers} valid new paper submission(s).")
            sys.exit(0)
        else:
            print("\n❌ Validation Failed: No valid new papers found.")
            print("Please ensure you have filled in the template (submit_template.xlsx or .json) correctly.")
            print("Entries identical to the repository template are ignored.")
            sys.exit(1)

    finally:
        # 清理临时文件
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)

if __name__ == "__main__":
    main()