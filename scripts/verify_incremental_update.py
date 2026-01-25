import sys
import os
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.update_file_utils import get_update_file_utils
from src.core.database_model import is_duplicate_paper

def verify_incremental(old_excel_path, new_excel_path):
    utils = get_update_file_utils()
    
    print(f"Verifying incremental update...")
    print(f"Old DB: {old_excel_path}")
    print(f"New DB: {new_excel_path}")

    if not os.path.exists(old_excel_path):
        print("Old database not found. Assuming first initialization.")
        return True

    if not os.path.exists(new_excel_path):
        print("New database not found! Update failed.")
        return False

    old_papers = utils.load_papers_from_excel(old_excel_path, skip_invalid=False)
    new_papers = utils.load_papers_from_excel(new_excel_path, skip_invalid=False)

    print(f"Old papers count: {len(old_papers)}")
    print(f"New papers count: {len(new_papers)}")

    if len(new_papers) < len(old_papers):
        print("Error: New database has fewer papers than old database.")
        return False

    # 验证每一篇旧论文是否都在新数据库中存在且完全一致
    missing_papers = []
    for old_p in old_papers:
        # 使用 complete_compare=True 严格检查
        found, _ = is_duplicate_paper(new_papers, old_p, complete_compare=True)
        if not found:
            missing_papers.append(old_p.title)

    if missing_papers:
        print(f"Error: {len(missing_papers)} papers from old database are missing or modified in new database:")
        for t in missing_papers[:5]:
            print(f"  - {t}")
        return False
    
    print("Verification Passed: Strict incremental update confirmed.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python verify_incremental_update.py <old_path> <new_path>")
        sys.exit(1)
    
    success = verify_incremental(sys.argv[1], sys.argv[2])
    if not success:
        sys.exit(1)