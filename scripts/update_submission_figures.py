import os
import sys
import hashlib
import configparser
import pandas as pd
import json
import shutil
import re
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.config_loader import get_config_instance

# 加载配置
config_instance = get_config_instance()
settings = config_instance.settings
UPDATE_EXCEL = settings['paths']['update_excel']
UPDATE_JSON = settings['paths']['update_json']
FIGURE_DIR = settings['paths']['figure_dir']
PROJECT_ROOT = config_instance.project_root

def calculate_file_hash(filepath):
    """计算文件的 MD5 哈希值"""
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

def get_smart_unique_filename(original_path, title):
    """
    智能获取文件名：
    1. 如果目标文件名已存在且哈希相同 -> 直接复用 (不重命名)
    2. 如果目标文件名已存在且哈希不同 -> 增加计数器重命名
    """
    dirname, basename = os.path.split(original_path)
    filename, ext = os.path.splitext(basename)
    title_part = get_clean_title_hash(title)
    
    # 计算原始文件的哈希（用于对比）
    source_hash = calculate_file_hash(original_path)
    
    counter = 1
    while True:
        # 构建目标文件名
        new_basename = f"{filename}-{title_part}-{counter}{ext}"
        new_full_path = os.path.join(FIGURE_DIR, new_basename)
        
        if os.path.exists(new_full_path):
            # 如果文件存在，对比内容
            target_hash = calculate_file_hash(new_full_path)
            if source_hash and target_hash and source_hash == target_hash:
                print(f"  [Info] Duplicate image detected (Hash match). Reuse: {new_basename}")
                return new_full_path
            
            # 哈希不同，说明是冲突，继续增加计数器
            counter += 1
        else:
            # 文件不存在，可以使用该名字
            return new_full_path

def process_figures():
    print(f"Processing figures in: {FIGURE_DIR}")
    if not os.path.exists(FIGURE_DIR):
        os.makedirs(FIGURE_DIR)

    # --- 处理 Excel ---
    if os.path.exists(UPDATE_EXCEL):
        try:
            print(f"Checking Excel template: {UPDATE_EXCEL}")
            df = pd.read_excel(UPDATE_EXCEL, engine='openpyxl')
            updated = False
            
            target_col = "pipeline figure" 
            title_col = "title"
            if target_col not in df.columns and "pipeline_image" in df.columns:
                target_col = "pipeline_image"

            if target_col in df.columns:
                for idx, row in df.iterrows():
                    img_path_raw = row[target_col]
                    title = row.get(title_col, "unknown")
                    
                    if pd.isna(img_path_raw) or str(img_path_raw).strip() == "":
                        continue

                    paths = [p.strip() for p in re.split(r'[;；]', str(img_path_raw).strip()) if p.strip()]
                    new_paths = []
                    row_updated = False
                        
                    for p in paths:
                        # 解析路径
                        if os.path.isabs(p):
                            full_current_path = p
                        else:
                            full_current_path = os.path.join(PROJECT_ROOT, p)
                            if not os.path.exists(full_current_path):
                                full_current_path = os.path.join(FIGURE_DIR, os.path.basename(p))
                        
                        if os.path.exists(full_current_path):
                            # 获取智能目标路径
                            new_full_path = get_smart_unique_filename(full_current_path, title)
                            
                            # 如果源路径和目标路径不一样，则重命名(移动)
                            if os.path.abspath(full_current_path) != os.path.abspath(new_full_path):
                                os.rename(full_current_path, new_full_path)
                                print(f"Renamed: {os.path.basename(full_current_path)} -> {os.path.basename(new_full_path)}")
                            
                            # 关键：生成相对于 Project Root 的路径，并强制使用正斜杠
                            rel_path = os.path.relpath(new_full_path, PROJECT_ROOT).replace('\\', '/')
                            new_paths.append(rel_path)
                            row_updated = True
                            updated = True
                        else:
                            print(f"Warning: Image not found: {p}")
                            new_paths.append(p)
                    
                    if row_updated:
                        df.at[idx, target_col] = ";".join(new_paths)
            
            if updated:
                from src.core.update_file_utils import get_update_file_utils
                get_update_file_utils().write_excel_file(UPDATE_EXCEL, df)
                print("Excel template updated with new image paths.")

        except Exception as e:
            print(f"Error processing Excel figures: {e}")
            import traceback
            traceback.print_exc()

    # --- 处理 JSON ---
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

                    title = paper.get('title', 'unknown')
                    paths = [p.strip() for p in re.split(r'[;；]', img_path_str) if p.strip()]
                    new_paths = []
                    row_updated = False

                    for p in paths:
                        if os.path.isabs(p):
                            full_current_path = p
                        else:
                            full_current_path = os.path.join(PROJECT_ROOT, p)
                            if not os.path.exists(full_current_path):
                                full_current_path = os.path.join(FIGURE_DIR, os.path.basename(p))
                        
                        if os.path.exists(full_current_path):
                            new_full_path = get_smart_unique_filename(full_current_path, title)
                            
                            if os.path.abspath(full_current_path) != os.path.abspath(new_full_path):
                                os.rename(full_current_path, new_full_path)
                            
                            rel_path = os.path.relpath(new_full_path, PROJECT_ROOT).replace('\\', '/')
                            new_paths.append(rel_path)
                            row_updated = True
                            json_updated = True
                        else:
                            new_paths.append(p)
                    
                    if row_updated:
                        paper['pipeline_image'] = ";".join(new_paths)

            if json_updated:
                with open(UPDATE_JSON, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("JSON template updated with new image paths.")

        except Exception as e:
            print(f"Error processing JSON figures: {e}")

if __name__ == "__main__":
    process_figures()