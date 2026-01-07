"""
Validate update template files in PR context.
Checks:
- Only allowed files are modified (submit_template.json, submit_template.xlsx, and files under configured figure_dir)
- Both submit_template.json and submit_template.xlsx (if present) contain only valid papers according to Paper.validate_paper_fields(check_required=True, check_non_empty=True)

Exit codes:
0 - OK
1 - Validation errors in templates
2 - Unauthorized file changes
"""
import os
import sys
import subprocess
import json
import configparser
from typing import List

# ensure project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.update_file_utils import UpdateFileUtils
from src.core.config_loader import ConfigLoader
from src.core.database_model import Paper


def get_changed_files() -> List[str]:
    # Try git diff to get changed files in PR branch vs main
    try:
        # fetch main to ensure origin/main exists
        subprocess.run(["git", "fetch", "origin", "main"], check=False)
        res = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], check=True, stdout=subprocess.PIPE, text=True)
        files = [s.strip() for s in res.stdout.splitlines() if s.strip()]
        return files
    except Exception:
        # Fallback: nothing
        return []


def get_figure_dir_basename() -> str:
    # Read config/setting.config to obtain figure_dir
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'setting.config')
    if not os.path.exists(cfg_path):
        return 'figures'
    cp = configparser.ConfigParser()
    try:
        cp.read(cfg_path, encoding='utf-8')
        paths = cp['paths'] if 'paths' in cp else {}
        figure_dir = paths.get('figure_dir', 'figures') if paths else 'figures'
        # Use basename to make it relative when absolute path given
        figure_dir = os.path.basename(figure_dir) if os.path.isabs(figure_dir) else figure_dir
        return figure_dir.replace('\\', '/').rstrip('/')
    except Exception:
        return 'figures'


def check_changed_files_allowed(changed_files: List[str], figure_dir_basename: str) -> List[str]:
    allowed = set([
        'submit_template.json',
        'submit_template.xlsx',
    ])
    bad = []
    for f in changed_files:
        nf = f.replace('\\', '/')
        if nf in allowed:
            continue
        # allow files under figure_dir
        if nf.startswith(figure_dir_basename + '/') or nf == figure_dir_basename:
            continue
        # allow config changes to setting.config? No - be strict
        bad.append(nf)
    return bad


def validate_json_file(uf: UpdateFileUtils, path: str) -> List[str]:
    errors = []
    data = uf.read_json_file(path)
    if not data:
        return errors
    if isinstance(data, dict) and 'papers' in data:
        papers = data['papers']
    elif isinstance(data, list):
        papers = data
    else:
        papers = [data]

    normalized = uf.normalize_json_papers(papers, uf.config)
    tags = uf.config.get_non_system_tags()
    for idx, item in enumerate(normalized):
        paper_data = uf._dict_to_paper_data(item, tags)
        paper = Paper.from_dict(paper_data)
        valid, es = paper.validate_paper_fields(uf.config, check_required=True, check_non_empty=True)
        if not valid:
            errors.append(f"JSON entry #{idx}: {paper.title[:50]} - {es}")
    return errors


def validate_excel_file(uf: UpdateFileUtils, path: str) -> List[str]:
    errors = []
    df = uf.read_excel_file(path)
    if df is None or df.empty:
        return errors
    try:
        import pandas as pd
    except Exception:
        errors.append('pandas not available to validate Excel')
        return errors

    tags = uf.config.get_non_system_tags()
    for idx, row in df.iterrows():
        paper_data = uf._excel_row_to_paper_data(row, tags)
        paper = Paper.from_dict(paper_data)
        valid, es = paper.validate_paper_fields(uf.config, check_required=True, check_non_empty=True)
        if not valid:
            errors.append(f"Excel row #{idx}: {paper.title[:50]} - {es}")
    return errors


def main():
    uf = UpdateFileUtils()

    # 1. Check changed files in PR
    changed = get_changed_files()
    fig_dir = get_figure_dir_basename()
    bad = check_changed_files_allowed(changed, fig_dir)
    if bad:
        print('Unauthorized files changed in PR:')
        for b in bad:
            print('  -', b)
        print(f"Only modifications to submit_template.json, submit_template.xlsx and '{fig_dir}/**' are allowed.")
        sys.exit(2)

    # 2. Validate contents
    all_errors = []
    repo_root = os.path.dirname(os.path.dirname(__file__))
    json_path = os.path.join(repo_root, 'submit_template.json')
    xlsx_path = os.path.join(repo_root, 'submit_template.xlsx')

    if os.path.exists(json_path):
        print('Validating JSON file:', json_path)
        errs = validate_json_file(uf, json_path)
        all_errors.extend(errs)

    if os.path.exists(xlsx_path):
        print('Validating Excel file:', xlsx_path)
        errs = validate_excel_file(uf, xlsx_path)
        all_errors.extend(errs)

    if all_errors:
        print('Validation failed:')
        for e in all_errors:
            print('  -', e)
        sys.exit(1)

    print('All template validations passed')

if __name__ == '__main__':
    main()
