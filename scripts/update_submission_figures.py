import os
import sys
import hashlib
import shutil
import re
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.config_loader import get_config_instance
from src.core.update_file_utils import get_update_file_utils

config_instance = get_config_instance()
settings = config_instance.settings
update_utils = get_update_file_utils()

# 路径配置
PROJECT_ROOT = config_instance.project_root
UPDATE_CSV = settings['paths'].get('update_csv')
UPDATE_JSON = settings['paths'].get('update_json')

# 目标目录（Main Branch）
FIGURE_DIR = str(Path(settings['paths']['figure_dir']).resolve())
ASSETS_DIR = str(Path(settings['paths'].get('assets_dir', os.path.join(PROJECT_ROOT, 'assets'))).resolve())

# 源目录（PR Branch 暂存，工作流通过环境变量传入）
PR_ASSETS_DIR_ENV = os.environ.get('PR_ASSETS_DIR')
PR_ASSETS_DIR = str(Path(PR_ASSETS_DIR_ENV).resolve()) if PR_ASSETS_DIR_ENV else ''
PR_FIGURE_DIR_ENV = os.environ.get('PR_FIGURES_DIR')
PR_FIGURE_DIR = str(Path(PR_FIGURE_DIR_ENV).resolve()) if PR_FIGURE_DIR_ENV else FIGURE_DIR

SOURCE_ROOTS = []
for d in [PR_ASSETS_DIR, PR_FIGURE_DIR, ASSETS_DIR, FIGURE_DIR]:
    if d and os.path.isdir(d) and d not in SOURCE_ROOTS:
        SOURCE_ROOTS.append(d)

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
    if not title:
        return "untitled"
    clean_prefix = re.sub(r'[^a-zA-Z0-9]', '', str(title)[:8])
    return clean_prefix or "untitled"

def get_smart_unique_path(source_path, target_dir, original_basename, title):
    """
    决定图片的最终目标路径：
    1. 目标不存在 -> 使用原名
    2. 目标存在且哈希相同 -> 使用原名 (后续逻辑会跳过覆盖)
    3. 目标存在且哈希不同 -> 重命名 (Name-Title-Count)
    """
    filename, ext = os.path.splitext(original_basename)
    source_hash = calculate_file_hash(source_path)
    
    # 尝试 1: 原名
    target_path = os.path.join(target_dir, original_basename)
    
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
        new_full_path = os.path.join(target_dir, new_basename)
        
        if not os.path.exists(new_full_path):
            return new_full_path, True # True 表示发生了重命名
            
        # 如果生成的新名字也存在，继续对比哈希（防止重复运行脚本产生多余副本）
        if calculate_file_hash(new_full_path) == source_hash:
            return new_full_path, False
            
        counter += 1


def is_subpath(path: str, parent: str) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except Exception:
        return False


def split_image_paths(value: str):
    s = str(value or '').strip()
    if not s:
        return []
    return [p.strip() for p in re.split(r'[|;；]', s) if p.strip()]


def normalize_rel_path(path_str: str) -> str:
    return str(path_str).replace('\\', '/')


def resolve_source_file(raw_path: str, uid: str = ''):
    """
    在 PR/main 的 assets/figures 目录中查找资源。
    返回: (找到的绝对路径, 是否来自PR暂存目录)
    """
    clean = str(raw_path or '').strip()
    if not clean:
        return None, False

    # 1) 绝对路径
    if os.path.isabs(clean) and os.path.exists(clean):
        from_pr = (PR_ASSETS_DIR and is_subpath(clean, PR_ASSETS_DIR)) or (PR_FIGURE_DIR and is_subpath(clean, PR_FIGURE_DIR))
        return clean, bool(from_pr)

    # 2) 项目相对路径
    rel_candidate = os.path.join(PROJECT_ROOT, clean)
    if os.path.exists(rel_candidate):
        from_pr = (PR_ASSETS_DIR and is_subpath(rel_candidate, PR_ASSETS_DIR)) or (PR_FIGURE_DIR and is_subpath(rel_candidate, PR_FIGURE_DIR))
        return rel_candidate, bool(from_pr)

    base = os.path.basename(clean)

    # 3) 有 UID 时优先找 assets/{uid}/{base}
    if uid:
        for root in SOURCE_ROOTS:
            cand = os.path.join(root, uid, base)
            if os.path.exists(cand):
                from_pr = (PR_ASSETS_DIR and is_subpath(cand, PR_ASSETS_DIR)) or (PR_FIGURE_DIR and is_subpath(cand, PR_FIGURE_DIR))
                return cand, bool(from_pr)

    # 4) 按 basename 在已知目录查找
    for root in SOURCE_ROOTS:
        cand = os.path.join(root, base)
        if os.path.exists(cand):
            from_pr = (PR_ASSETS_DIR and is_subpath(cand, PR_ASSETS_DIR)) or (PR_FIGURE_DIR and is_subpath(cand, PR_FIGURE_DIR))
            return cand, bool(from_pr)

    return None, False

def process_pipeline_images_for_file(file_path: str) -> bool:
    success, papers = update_utils.read_data(file_path)
    if not success:
        print(f"Failed to load update file: {file_path}")
        return False

    changed = False
    for paper in papers:
        raw_value = str(getattr(paper, 'pipeline_image', '') or '').strip()
        if not raw_value:
            continue

        title = getattr(paper, 'title', 'untitled')
        uid = str(getattr(paper, 'uid', '') or '').strip()
        raw_paths = split_image_paths(raw_value)
        new_relative_paths = []
        row_dirty = False

        for p in raw_paths:
            src_path, is_from_pr = resolve_source_file(p, uid)
            if not src_path:
                print(f"Warning: Image not found in PR/Main assets or figures: {p}")
                new_relative_paths.append(normalize_rel_path(p))
                continue

            # 优先落到 assets/{uid}/，无 uid 时兼容落到 figures/
            target_dir = os.path.join(ASSETS_DIR, uid) if uid else FIGURE_DIR
            os.makedirs(target_dir, exist_ok=True)

            dst_path, _ = get_smart_unique_path(src_path, target_dir, os.path.basename(src_path), title)

            if os.path.abspath(src_path) != os.path.abspath(dst_path):
                if not os.path.exists(dst_path):
                    if is_from_pr:
                        shutil.move(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
                else:
                    if is_from_pr and os.path.exists(src_path):
                        os.remove(src_path)

            rel_path = normalize_rel_path(os.path.relpath(dst_path, PROJECT_ROOT))
            new_relative_paths.append(rel_path)
            if rel_path != normalize_rel_path(p):
                row_dirty = True

        normalized_old = '|'.join(split_image_paths(raw_value))
        normalized_new = '|'.join(new_relative_paths)
        if row_dirty or normalized_old != normalized_new:
            paper.pipeline_image = normalized_new
            changed = True

    if changed:
        if not update_utils.write_data(file_path, papers):
            print(f"Failed to write update file: {file_path}")
            return False
        print(f"Updated: {file_path}")
    else:
        print(f"No changes: {file_path}")

    return True


def process_figures():
    print(f"Processing figures.")
    if PR_ASSETS_DIR:
        print(f"  - Source (PR assets): {PR_ASSETS_DIR}")
    print(f"  - Source (PR): {PR_FIGURE_DIR}")
    print(f"  - Target (Main assets): {ASSETS_DIR}")
    print(f"  - Target (Main figures): {FIGURE_DIR}")

    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(FIGURE_DIR, exist_ok=True)

    targets = []
    if UPDATE_CSV and os.path.exists(UPDATE_CSV):
        targets.append(UPDATE_CSV)
    if UPDATE_JSON and os.path.exists(UPDATE_JSON):
        targets.append(UPDATE_JSON)

    if not targets:
        print("No update CSV/JSON files found, skipping.")
        return

    for target in targets:
        process_pipeline_images_for_file(target)

if __name__ == "__main__":
    process_figures()