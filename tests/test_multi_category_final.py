#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多分类功能真实场景测试 (ASCII版本)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

from src.core.update_file_utils import UpdateFileUtils
from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

config = get_config_instance()
utils = UpdateFileUtils()

# 获取真实的分类列表
active_cats = config.get_active_categories()
cat_names = [c['unique_name'] for c in active_cats][:5]

print("[OK] All modules imported successfully\n")
print(f"Available categories (first 5): {cat_names}\n")

# Test 1
print("=== Test 1: Multi-category validation with real categories ===")
if len(cat_names) >= 2:
    multi_cat = f"{cat_names[0]};{cat_names[1]}"
    paper = Paper(
        doi="10.1234/test.1234",
        title="Test Multi-Category Paper",
        authors="Author One, Author Two",
        date="2024-01-15",
        category=multi_cat,
        paper_url="https://arxiv.org/abs/2401.00000",
        summary_motivation="Motivating work",
        summary_innovation="Novel approach",
        summary_method="Method description",
        summary_conclusion="Conclusion statement"
    )
    valid, errors, _ = paper.validate_paper_fields(config, check_required=True, check_non_empty=True)
    print(f"Input category: {multi_cat}")
    print(f"Validation result: {'[OK] PASS' if valid else '[FAIL] FAIL'}")
    if not valid:
        print(f"Errors: {errors}")
    else:
        print(f"Normalized: {paper.category}")
    print()

# Test 2
print("=== Test 2: Mixed separator handling ===")
if len(cat_names) >= 3:
    test_val = f"{cat_names[0]};{cat_names[1]};{cat_names[2]}"
    normalized = utils.normalize_category_value(test_val, config)
    print(f"Input: {test_val}")
    print(f"Normalized: {normalized}")
    parts = [p for p in normalized.split(';') if p]
    print(f"Count: {len(parts)}\n")

# Test 3
print("=== Test 3: Boundary cases ===")
test_cases = [
    "",
    "   ",
    None,
]
for i, test_val in enumerate(test_cases):
    normalized = utils.normalize_category_value(test_val, config)
    print(f"Test #{i+1}: {repr(test_val)} -> {repr(normalized)}")
print()

# Test 4
print("=== Test 4: README multi-category line generation simulation ===")
if len(cat_names) >= 2:
    paper = Paper(
        doi="10.1234/test.5678",
        title="Multi-Category Example",
        authors="Test Author",
        date="2024-01-20",
        category=f"{cat_names[0]};{cat_names[1]}",
        paper_url="https://example.com/paper",
        summary_motivation="test",
        summary_innovation="test",
        summary_method="test",
        summary_conclusion="test"
    )
    
    parts = [p.strip() for p in paper.category.split(';') if p.strip()]
    if len(parts) > 1:
        links = []
        for uname in parts:
            display = config.get_category_field(uname, 'name') or uname
            anchor = display.lower().replace(' ', '-')
            links.append(f"[{display}](#{anchor})")
        multi_line = f"multi-category: {', '.join(links)}"
        print(f"Paper: {paper.title}")
        print(f"Categories: {paper.category}")
        print(f"Multi-category line: {multi_line}\n")

# Test 5
print("=== Test 5: GUI model - multi-category collection ===")
if len(cat_names) >= 2:
    gui_selections = [cat_names[0], cat_names[1]]
    category_str = ";".join(gui_selections)
    print(f"GUI selections: {gui_selections}")
    print(f"Collected string: {category_str}")
    
    reverse = [p for p in category_str.split(';') if p]
    print(f"Reverse conversion: {reverse}")
    print(f"Consistency check: {'[OK] PASS' if reverse == gui_selections else '[FAIL] FAIL'}\n")

# Test 6
print("=== Test 6: Paper uniqueness check (same paper, different categories) ===")
paper1 = Paper(
    doi="10.1234/unique.9999",
    title="Unique Paper A",
    authors="Author",
    date="2024-01-01",
    category=cat_names[0] if cat_names else "test",
    paper_url="https://example.com"
)
paper2 = Paper(
    doi="10.1234/unique.9999",
    title="Unique Paper A",
    authors="Author",
    date="2024-01-01",
    category=cat_names[1] if len(cat_names) > 1 else cat_names[0],
    paper_url="https://example.com"
)
from src.core.database_model import is_same_identity
result = is_same_identity(paper1, paper2)
print(f"Paper 1 DOI: {paper1.doi}, Category: {paper1.category}")
print(f"Paper 2 DOI: {paper2.doi}, Category: {paper2.category}")
print(f"Same paper: {'[OK] YES' if result else '[NO] NO'}")
print("(Note: Multi-category does not affect uniqueness check, based only on DOI and Title)\n")

print("[OK] All real scenario tests completed!")
