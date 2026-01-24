#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick multi-category feature test
"""
import sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

from src.core.update_file_utils import UpdateFileUtils
from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

config = get_config_instance()
utils = UpdateFileUtils()

# Get real categories
cats = [c['unique_name'] for c in config.get_active_categories()][:3]
print(f"Test categories: {cats}\n")

# TEST 1: Normalization with real categories
print("TEST 1: Normalization")
val = f"{cats[0]};{cats[1]}"
normalized = utils.normalize_category_value(val, config)
print(f"  Input:  {val}")
print(f"  Output: {normalized}")
print(f"  Result: {'PASS' if normalized == val else 'FAIL'}\n")

# TEST 2: Deduplication
print("TEST 2: Deduplication")
val_dup = f"{cats[0]};{cats[1]};{cats[0]}"
normalized_dup = utils.normalize_category_value(val_dup, config)
print(f"  Input:  {val_dup}")
print(f"  Output: {normalized_dup}")
print(f"  Result: {'PASS' if normalized_dup == f'{cats[0]};{cats[1]}' else 'FAIL'}\n")

# TEST 3: Paper validation with real categories
print("TEST 3: Paper validation with multi-category")
paper = Paper(
    doi="10.1234/test1234",
    title="Test Paper",
    authors="Test Author",
    date="2024-01-21",
    category=f"{cats[0]};{cats[1]}",
    paper_url="https://example.com",
    summary_motivation="M",
    summary_innovation="I", 
    summary_method="M",
    summary_conclusion="C"
)
valid, errors , _= paper.validate_paper_fields(config, check_required=True, check_non_empty=True)
print(f"  Category: {paper.category}")
print(f"  Valid: {valid}")
if errors:
    print(f"  Errors: {[e for e in errors if 'categor' in e.lower()]}")
else:
    print(f"  Errors: None")
print(f"  Result: {'PASS' if valid else 'FAIL'}\n")

# TEST 4: Chinese semicolon handling
print("TEST 4: Chinese semicolon handling")
val_cn = f"{cats[0]}；{cats[1]}"
normalized_cn = utils.normalize_category_value(val_cn, config)
print(f"  Input (Chinese;): {val_cn}")
print(f"  Output: {normalized_cn}")
print(f"  Result: {'PASS' if normalized_cn == f'{cats[0]};{cats[1]}' else 'FAIL'}\n")

# TEST 5: Max category limit
print("TEST 5: Max category limit")
max_allowed = int(config.settings['database'].get('max_categories_per_paper', 4))
all_cats = [c['unique_name'] for c in config.get_active_categories()]
big_val = ";".join(all_cats[:10])
normalized_limited = utils.normalize_category_value(big_val, config)
actual_count = len([c for c in normalized_limited.split(';') if c])
print(f"  Max allowed: {max_allowed}")
print(f"  Input count: 10")
print(f"  Output count: {actual_count}")
print(f"  Result: {'PASS' if actual_count <= max_allowed else 'FAIL'}\n")

print("=== All tests completed ===")
