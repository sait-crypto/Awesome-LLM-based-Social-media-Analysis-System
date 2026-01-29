import os
import sys
import hashlib
import configparser
import pandas as pd
import json
import shutil
import re
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.config_loader import get_config_instance

config_instance = get_config_instance()
settings = config_instance.settings

# 路径配置
PROJECT_ROOT = config_instance.project_root
UPDATE_EXCEL = str(Path(settings['paths']['update_excel']).resolve())
UPDATE_JSON = str(Path(settings['paths']['update_json']).resolve())

# 目标目录 (Main Branch Figures)
FIGURE_DIR_REL = settings['paths']['figure_dir']
FIGURE_DIR = str(Path(PROJECT_ROOT) / FIGURE_DIR_REL)

# 源目录 (PR Branch Figures - 通过环境变量传入)
# 如果没有设置环境变量，默认认为就在 figures (本地运行情况)
PR_FIGURE_DIR_ENV = os.environ.get('PR_FIGURES_DIR')
PR_FIGURE_DIR = str(Path(PR_FIGURE_DIR_ENV).resolve()) if PR_FIGURE_DIR_ENV else FIGURE_DIR

def calculate_file_hash(filepath):
    """计算文件的 MD5 哈希值"""
    if not os.path.exists(filepath):
        return None
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    except Exception:
        return None

def get_clean_title_hash(title):
    if not title or pd.isna(title):
        return "untitled"
    clean_prefix = re.sub(r'[^a-zA-Z0-9]', '', str(title)[:8])
    return clean_prefix

def get_smart_unique_path(source_path, original_basename, title):
    """
    决定图片的最终目标路径：
    1. 目标不存在 -> 使用原名
    2. 目标存在且哈希相同 -> 使用原名 (后续逻辑会跳过覆盖)
    3. 目标存在且哈希不同 -> 重命名 (Name-Title-Count)
    """
    filename, ext = os.path.splitext(original_basename)
    source_hash = calculate_file_hash(source_path)
    
    # 尝试 1: 原名
    target_path = os.path.join(FIGURE_DIR, original_basename)
    
    if not os.path.exists(target_path):
        return target_path, False # False 表示没有冲突
        
    # 如果目标存在，对比哈希
    target_hash = calculate_file_hash(target_path)
    if source_hash == target_hash:
        return target_path, False # 哈希相同，视为无冲突，复用即可
    
    # 哈希不同，说明是真正的文件名冲突，需要重命名
    title_part = get_clean_title_hash(title)
    counter = 1
    
    while True:
        new_basename = f"{filename}-{title_part}-{counter}{ext}"
        new_full_path = os.path.join(FIGURE_DIR, new_basename)
        
        if not os.path.exists(new_full_path):
            return new_full_path, True # True 表示发生了重命名
            
        # 如果生成的新名字也存在，继续对比哈希（防止重复运行脚本产生多余副本）
        if calculate_file_hash(new_full_path) == source_hash:
            return new_full_path, False
            
        counter += 1

def resolve_pr_image(p):
    """
    在 PR 目录或 Main 目录中查找图片
    返回: (找到的绝对路径, 是否在PR目录中)
    """
    # 1. 优先去 PR 暂存区找
    pr_path = os.path.join(PR_FIGURE_DIR, os.path.basename(p))
    if os.path.exists(pr_path):
        return pr_path, True
    
    # 2. 如果 PR 目录和 Main 目录是同一个（本地运行），或者 PR 里没这个图
    # 去 Main 目录找 (可能是以前提交过的图)
    main_path = os.path.join(FIGURE_DIR, os.path.basename(p))
    if os.path.exists(main_path):
        return main_path, False
        
    return None, False

def process_figures():
    print(f"Processing figures.")
    print(f"  - Source (PR): {PR_FIGURE_DIR}")
    print(f"  - Target (Main): {FIGURE_DIR}")
    
    if not os.path.exists(FIGURE_DIR):
        os.makedirs(FIGURE_DIR)

    # --- 处理 Excel ---
    if os.path.exists(UPDATE_EXCEL):
        try:
            print(f"Checking Excel template: {UPDATE_EXCEL}")
            df = pd.read_excel(UPDATE_EXCEL, engine='openpyxl')
            updated = False
            
            target_col = "pipeline figure" 
            if target_col not in df.columns and "pipeline_image" in df.columns:
                target_col = "pipeline_image"
            title_col = "title"

            if target_col in df.columns:
                for idx, row in df.iterrows():
                    img_path_raw = row[target_col]
                    title = row.get(title_col, "untitled")
                    
                    if pd.isna(img_path_raw) or str(img_path_raw).strip() == "":
                        continue

                    raw_paths = [p.strip() for p in re.split(r'[;；]', str(img_path_raw).strip()) if p.strip()]
                    new_relative_paths = []
                    row_dirty = False
                        
                    for p in raw_paths:
                        # 查找图片
                        src_path, is_from_pr = resolve_pr_image(p)
                        
                        if src_path:
                            # 计算目标路径
                            dst_path, renamed = get_smart_unique_path(src_path, os.path.basename(p), title)
                            
                            # 只有当图片来自 PR 目录，且目标路径文件不存在时，才执行移动/复制
                            # 或者目标已存在但我们确定要覆盖（这里逻辑是哈希相同不覆盖，不同才重命名后写入）
                            
                            # 如果 src 和 dst 是同一个文件（比如本地运行），跳过
                            if os.path.abspath(src_path) != os.path.abspath(dst_path):
                                if not os.path.exists(dst_path):
                                    print(f"Moving new image: {os.path.basename(src_path)} -> {os.path.basename(dst_path)}")
                                    shutil.move(src_path, dst_path)
                                else:
                                    print(f"Image exists (Hash match), linking: {os.path.basename(dst_path)}")
                                    # 如果来自 PR 且目标已存在（哈希相同），删除 PR 里的冗余副本
                                    if is_from_pr:
                                        os.remove(src_path)

                            # 计算相对路径写入 Excel
                            rel_path = os.path.relpath(dst_path, PROJECT_ROOT).replace('\\', '/')
                            if rel_path != p.replace('\\', '/'):
                                row_dirty = True
                            
                            new_relative_paths.append(rel_path)
                        else:
                            print(f"Warning: Image not found in PR or Main: {p}")
                            new_relative_paths.append(p)
                    
                    if row_dirty:
                        df.at[idx, target_col] = ";".join(new_relative_paths)
                        updated = True
            
            if updated:
                from src.core.update_file_utils import get_update_file_utils
                get_update_file_utils().write_excel_file(UPDATE_EXCEL, df)
                print("Excel template updated.")

        except Exception as e:
            print(f"Error processing Excel figures: {e}")
            import traceback
            traceback.print_exc()

    # --- 处理 JSON (逻辑同上，略微简化) ---
    if os.path.exists(UPDATE_JSON):
        try:
            print(f"Checking JSON template: {UPDATE_JSON}")
            with open(UPDATE_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            json_updated = False
            
            papers = data if isinstance(data, list) else data.get('papers', [])
            for paper in papers:
                if 'pipeline_image' in paper and paper['pipeline_image']:
                    img_path_str = str(paper['pipeline_image']).strip()
                    if not img_path_str: continue
                    title = paper.get('title', 'untitled')
                    raw_paths = [p.strip() for p in re.split(r'[;；]', img_path_str) if p.strip()]
                    new_relative_paths = []
                    row_dirty = False

                    for p in raw_paths:
                        src_path, is_from_pr = resolve_pr_image(p)
                        if src_path:
                            dst_path, renamed = get_smart_unique_path(src_path, os.path.basename(p), title)
                            if os.path.abspath(src_path) != os.path.abspath(dst_path):
                                if not os.path.exists(dst_path):
                                    shutil.move(src_path, dst_path)
                                else:
                                    if is_from_pr: os.remove(src_path)
                            
                            rel_path = os.path.relpath(dst_path, PROJECT_ROOT).replace('\\', '/')
                            new_relative_paths.append(rel_path)
                            row_dirty = True
                        else:
                            new_relative_paths.append(p)
                    
                    if row_dirty:
                        paper['pipeline_image'] = ";".join(new_relative_paths)
                        json_updated = True

            if json_updated:
                from src.core.update_file_utils import get_update_file_utils
                get_update_file_utils().write_json_file(UPDATE_JSON, data)

        except Exception as e:
            print(f"Error processing JSON figures: {e}")

if __name__ == "__main__":
    process_figures()