"""
Validate update template files in PR context.
Checks:
- Only allowed files are modified (submit_template.json, submit_template.xlsx, and files under configured figure_dir)
- Both submit_template.json and submit_template.xlsx (if present) contain only valid papers according to Paper.validate_paper_fields(check_required=True, check_non_empty=True)

Exit codes:
0 - OK
1 - Validation errors in templates or unable to close PR when nothing to process
2 - (deprecated) previously used for unauthorized file changes, now such changes are warned and ignored
3 - PR had no actionable changes (no added images and no template changes); script will attempt to comment and close PR
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


def get_changed_files_with_status() -> List[tuple]:
    """Return list of (status, filepath) from git diff --name-status origin/main...HEAD
    status is one of A, M, D, etc.
    """
    try:
        subprocess.run(["git", "fetch", "origin", "main"], check=False)
        res = subprocess.run(["git", "diff", "--name-status", "origin/main...HEAD"], check=True, stdout=subprocess.PIPE, text=True)
        lines = [s.strip() for s in res.stdout.splitlines() if s.strip()]
        out = []
        for l in lines:
            parts = l.split('\t')
            if len(parts) == 1:
                parts = l.split()
            if len(parts) >= 2:
                status = parts[0]
                path = parts[1]
                out.append((status, path))
        return out
    except Exception:
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


def _close_pr_with_comment(reason: str):
    """Post a comment and close the PR using GITHUB_TOKEN and GITHUB_EVENT_PATH"""
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    token = os.environ.get('GITHUB_TOKEN')
    if not event_path or not token:
        print('No event or token available to close PR')
        return
    try:
        with open(event_path, 'r', encoding='utf-8') as f:
            ev = json.load(f)
        pr = ev.get('pull_request')
        if not pr:
            print('No pull_request in event payload')
            return
        pr_num = pr.get('number')
        repo = ev.get('repository', {}).get('full_name')
        if not pr_num or not repo:
            print('Cannot determine PR number or repo')
            return
        owner, repo_name = repo.split('/')
        url = f'https://api.github.com/repos/{owner}/{repo_name}/issues/{pr_num}/comments'
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        # post comment
        requests.post(url, headers=headers, json={'body': reason})
        # close PR
        url2 = f'https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_num}'
        requests.patch(url2, headers=headers, json={'state': 'closed'})
        print(f'Closed PR #{pr_num} with reason: {reason}')
    except Exception as e:
        print('Failed to close PR:', e)


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
        valid, es, _ = paper.validate_paper_fields(uf.config, check_required=True, check_non_empty=True)
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
        valid, es, _ = paper.validate_paper_fields(uf.config, check_required=True, check_non_empty=True)
        if not valid:
            errors.append(f"Excel row #{idx}: {paper.title[:50]} - {es}")
    return errors


def main():
    uf = UpdateFileUtils()

    # 1. Check changed files in PR
    changed = get_changed_files_with_status()
    fig_dir = get_figure_dir_basename()

    # Determine added images and template changes
    added_images = [p for s,p in changed if s == 'A' and p.replace('\\','/').startswith(fig_dir + '/')]
    json_changed = any(p == 'submit_template.json' for s,p in changed)
    xlsx_changed = any(p == 'submit_template.xlsx' for s,p in changed)

    # If nothing to process (no added images and no template changes), close PR and exit
    if not added_images and not json_changed and not xlsx_changed:
        msg = 'This PR does not add new images under the configured figure dir nor modify submit templates. Closing PR as there is nothing to process.'
        print(msg)
        # Try to close PR with a comment
        _close_pr_with_comment(msg)
        sys.exit(3)

    # Now check unauthorized files
    bad = check_changed_files_allowed([p for s,p in changed], fig_dir)
    if bad:
        print('Warning: PR contains other changed files (these will be ignored by automated processing):')
        for b in bad:
            print('  -', b)
        print(f"NOTE: Only modifications to submit_template.json, submit_template.xlsx and '{fig_dir}/**' will be applied by this automation.")
        # Do not exit; continue but ignore those files

    # 2. Validate contents
    all_errors = []
    repo_root = os.path.dirname(os.path.dirname(__file__))
    json_path = os.path.join(repo_root, 'submit_template.json')
    xlsx_path = os.path.join(repo_root, 'submit_template.xlsx')

    if json_changed and os.path.exists(json_path):
        print('Validating JSON file:', json_path)
        errs = validate_json_file(uf, json_path)
        all_errors.extend(errs)

    if xlsx_changed and os.path.exists(xlsx_path):
        print('Validating Excel file:', xlsx_path)
        errs = validate_excel_file(uf, xlsx_path)
        all_errors.extend(errs)

    # Validate added images have allowed extensions
    valid_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}
    for f in added_images:
        ext = os.path.splitext(f)[1].lower()
        if ext not in valid_exts:
            all_errors.append(f'Added image {f} has invalid extension {ext}')

    if all_errors:
        print('Validation failed:')
        for e in all_errors:
            print('  -', e)
        sys.exit(1)

    # Export info for next processing step
    # Write JSON file listing added images and flags
    info = {
        'added_images': added_images,
        'json_changed': json_changed,
        'xlsx_changed': xlsx_changed
    }
    with open(os.path.join(os.path.dirname(__file__), 'validate_info.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)

    print('All template validations passed')

if __name__ == '__main__':
    main()
