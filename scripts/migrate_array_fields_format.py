"""
将更新文件中的数组字段迁移到统一格式：
- JSON: `category` / `pipeline_image` / `invalid_fields` 写为列表
- CSV: `category` / `pipeline_image` / `invalid_fields` 写为竖线分隔字符串（CSV 会自动按需加双引号）

其中 `invalid_fields` 会自动将旧 order 数字值映射为 tag variable。

默认仅处理项目根目录下的 .json/.csv 文件。
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.update_file_utils import UpdateFileUtils
from src.utils import backup_file


TARGET_FIELDS = ('category', 'pipeline_image', 'invalid_fields')


def _build_invalid_fields_maps(utils: UpdateFileUtils) -> Tuple[Dict[str, str], set]:
    order_to_var: Dict[str, str] = {}
    valid_vars = set()
    for tag in utils.config.get_active_tags():
        var = str(tag.get('variable') or '').strip()
        if not var:
            continue
        valid_vars.add(var)
        order = tag.get('order')
        if order is not None:
            order_to_var[str(order)] = var
    return order_to_var, valid_vars


def _normalize_invalid_fields_items(items: List[str], order_to_var: Dict[str, str], valid_vars: set) -> List[str]:
    out: List[str] = []
    for raw in items:
        token = str(raw).strip()
        if not token:
            continue
        if token in valid_vars:
            mapped = token
        elif token.isdigit() and token in order_to_var:
            mapped = order_to_var[token]
        else:
            mapped = token

        if mapped and mapped not in out:
            out.append(mapped)
    return out


def _parse_array_items(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        return [x.strip() for x in re.split(r'[|;,；，]', s) if x.strip()]
    return []


def _load_csv_rows(filepath: Path) -> Tuple[bool, List[List[str]], str]:
    encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'cp1252', 'latin-1']
    for enc in encodings_to_try:
        try:
            with open(filepath, 'r', encoding=enc, errors='strict') as f:
                rows = list(csv.reader(f))
            return True, rows, enc
        except Exception:
            continue
    return False, [], ''


def _migrate_json(path: Path, do_backup: bool, dry_run: bool, backup_dir: str, order_to_var: Dict[str, str], valid_vars: set) -> Tuple[bool, str]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return False, f"跳过（读取失败）: {path.name} | {e}"

    papers_ref = None
    if isinstance(data, dict):
        if isinstance(data.get('papers'), list):
            papers_ref = data['papers']
        elif 'title' in data:
            papers_ref = [data]
    elif isinstance(data, list):
        papers_ref = data

    if papers_ref is None:
        return False, f"跳过（结构不支持）: {path.name}"

    changed_cells = 0
    valid_paper_count = 0

    for paper in papers_ref:
        if not isinstance(paper, dict):
            continue
        valid_paper_count += 1
        for field in TARGET_FIELDS:
            if field not in paper:
                continue
            old_val = paper.get(field)
            parsed_items = _parse_array_items(old_val)
            if field == 'invalid_fields':
                new_val = _normalize_invalid_fields_items(parsed_items, order_to_var, valid_vars)
            else:
                new_val = parsed_items
            if old_val != new_val:
                paper[field] = new_val
                changed_cells += 1

    if dry_run:
        return True, f"可迁移(JSON): {path.name} ({valid_paper_count} 篇, 变更字段 {changed_cells})"

    if changed_cells == 0:
        return True, f"无需迁移(JSON): {path.name}"

    if do_backup:
        backup_file(str(path), backup_dir)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return True, f"已迁移(JSON): {path.name} ({valid_paper_count} 篇, 变更字段 {changed_cells})"


def _migrate_csv(path: Path, do_backup: bool, dry_run: bool, backup_dir: str, order_to_var: Dict[str, str], valid_vars: set) -> Tuple[bool, str]:
    ok, rows, _ = _load_csv_rows(path)
    if not ok:
        return False, f"跳过（读取失败）: {path.name}"

    if len(rows) < 2:
        return False, f"跳过（CSV行数不足）: {path.name}"

    header_ids = [h.strip() for h in rows[1]]
    target_indices = [i for i, tid in enumerate(header_ids) if tid in TARGET_FIELDS]
    if not target_indices:
        if dry_run:
            return True, f"可迁移(CSV): {path.name} (0 行, 变更字段 0)"
        return True, f"无需迁移(CSV): {path.name}"

    changed_cells = 0
    data_row_count = 0

    for r_idx in range(2, len(rows)):
        row = rows[r_idx]
        if not any(row):
            continue
        data_row_count += 1

        if len(row) < len(header_ids):
            row.extend([''] * (len(header_ids) - len(row)))

        for col_idx in target_indices:
            old_val = row[col_idx] if col_idx < len(row) else ''
            parsed_items = _parse_array_items(old_val)
            if header_ids[col_idx] == 'invalid_fields':
                parsed_items = _normalize_invalid_fields_items(parsed_items, order_to_var, valid_vars)
            new_val = '|'.join(parsed_items)
            if old_val != new_val:
                row[col_idx] = new_val
                changed_cells += 1

    if dry_run:
        return True, f"可迁移(CSV): {path.name} ({data_row_count} 行, 变更字段 {changed_cells})"

    if changed_cells == 0:
        return True, f"无需迁移(CSV): {path.name}"

    if do_backup:
        backup_file(str(path), backup_dir)

    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    return True, f"已迁移(CSV): {path.name} ({data_row_count} 行, 变更字段 {changed_cells})"


def collect_target_files(root: Path, recursive: bool):
    patterns = ['*.json', '*.csv']
    files = []
    if recursive:
        for pattern in patterns:
            files.extend(root.rglob(pattern))
    else:
        for pattern in patterns:
            files.extend(root.glob(pattern))
    return sorted(set(files))


def should_skip(path: Path) -> bool:
    banned_parts = {'__pycache__', 'build'}
    return any(part in banned_parts for part in path.parts)


def migrate_file(path: Path, utils: UpdateFileUtils, do_backup: bool, dry_run: bool):
    ext = path.suffix.lower()
    order_to_var, valid_vars = _build_invalid_fields_maps(utils)
    if ext == '.json':
        return _migrate_json(
            path,
            do_backup=do_backup,
            dry_run=dry_run,
            backup_dir=utils.backup_dir,
            order_to_var=order_to_var,
            valid_vars=valid_vars,
        )
    if ext == '.csv':
        return _migrate_csv(
            path,
            do_backup=do_backup,
            dry_run=dry_run,
            backup_dir=utils.backup_dir,
            order_to_var=order_to_var,
            valid_vars=valid_vars,
        )
    return False, f"跳过（不支持格式）: {path.name}"


def main():
    parser = argparse.ArgumentParser(description='迁移 category/pipeline_image/invalid_fields 的 JSON/CSV 存储格式')
    parser.add_argument('--recursive', action='store_true', help='递归扫描子目录（默认仅根目录）')
    parser.add_argument('--no-backup', action='store_true', help='不创建备份文件')
    parser.add_argument('--dry-run', action='store_true', help='仅扫描，不写回')
    args = parser.parse_args()

    utils = UpdateFileUtils()
    root = Path(utils.project_root)

    targets = [p for p in collect_target_files(root, args.recursive) if not should_skip(p)]
    if not targets:
        print('未找到可处理的 json/csv 文件。')
        return

    print(f"扫描到 {len(targets)} 个文件，开始处理...")

    ok_count = 0
    skip_or_fail_count = 0

    for path in targets:
        ok, message = migrate_file(path, utils, do_backup=not args.no_backup, dry_run=args.dry_run)
        print(message)
        if ok:
            ok_count += 1
        else:
            skip_or_fail_count += 1

    print('\n=== 迁移完成 ===')
    print(f"成功: {ok_count}")
    print(f"跳过/失败: {skip_or_fail_count}")


if __name__ == '__main__':
    main()
