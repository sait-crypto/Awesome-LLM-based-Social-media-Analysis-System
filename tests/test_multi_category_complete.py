#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Complete multi-category feature test with full validation
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

print("="*60)
print("MULTI-CATEGORY FEATURE TEST SUITE")
print("="*60 + "\n")

# TEST 1: Normalization with real categories
print("TEST 1: Normalization")
print("-" * 40)
val = f"{cats[0]};{cats[1]}"
normalized = utils.normalize_category_value(val, config)
print(f"  Input:  {val}")
print(f"  Output: {normalized}")
success1 = normalized == val
print(f"  Result: {'PASS' if success1 else 'FAIL'}\n")

# TEST 2: Deduplication
print("TEST 2: Deduplication")
print("-" * 40)
val_dup = f"{cats[0]};{cats[1]};{cats[0]}"
normalized_dup = utils.normalize_category_value(val_dup, config)
expected_dup = f"{cats[0]};{cats[1]}"
print(f"  Input:  {val_dup}")
print(f"  Output: {normalized_dup}")
print(f"  Expect: {expected_dup}")
success2 = normalized_dup == expected_dup
print(f"  Result: {'PASS' if success2 else 'FAIL'}\n")

# TEST 3: Paper validation with real categories (with all required fields)
print("TEST 3: Paper validation with multi-category")
print("-" * 40)
paper = Paper(
    doi="10.1234/test1234",
    title="Test Paper",
    authors="Test Author",
    date="2024-01-21",
    category=f"{cats[0]};{cats[1]}",
    paper_url="https://example.com",
    abstract="Test abstract",
    summary_motivation="Motivation text",
    summary_innovation="Innovation text", 
    summary_method="Method text",
    summary_conclusion="Conclusion text"
)
valid3, errors3, _ = paper.validate_paper_fields(config, check_required=True, check_non_empty=True)
print(f"  Category: {paper.category}")
print(f"  Valid: {valid3}")
if errors3:
    print(f"  Errors: {errors3}")
else:
    print(f"  Status: All fields valid")
success3 = valid3
print(f"  Result: {'PASS' if success3 else 'FAIL'}\n")

# TEST 4: Chinese semicolon handling
print("TEST 4: Chinese semicolon handling")
print("-" * 40)
val_cn = f"{cats[0]}；{cats[1]}"
normalized_cn = utils.normalize_category_value(val_cn, config)
expected_cn = f"{cats[0]};{cats[1]}"
print(f"  Input (Chinese;): {val_cn}")
print(f"  Output: {normalized_cn}")
print(f"  Expect: {expected_cn}")
success4 = normalized_cn == expected_cn
print(f"  Result: {'PASS' if success4 else 'FAIL'}\n")

# TEST 5: Max category limit
print("TEST 5: Max category limit enforcement")
print("-" * 40)
max_allowed = int(config.settings['database'].get('max_categories_per_paper', 4))
all_cats = [c['unique_name'] for c in config.get_active_categories()]
big_val = ";".join(all_cats[:10])
normalized_limited = utils.normalize_category_value(big_val, config)
actual_count = len([c for c in normalized_limited.split(';') if c])
print(f"  Max allowed: {max_allowed}")
print(f"  Input count: 10")
print(f"  Output count: {actual_count}")
success5 = actual_count <= max_allowed
print(f"  Result: {'PASS' if success5 else 'FAIL'}\n")

# TEST 6: Empty/None handling
print("TEST 6: Empty and None value handling")
print("-" * 40)
test_vals = ["", "   ", None]
results6 = []
for val in test_vals:
    normalized = utils.normalize_category_value(val, config)
    is_empty = normalized == ""
    results6.append(is_empty)
    print(f"  Input: {repr(val):10} -> Output: {repr(normalized):10} ({'OK' if is_empty else 'FAIL'})")
success6 = all(results6)
print(f"  Result: {'PASS' if success6 else 'FAIL'}\n")

# TEST 7: Paper uniqueness (same paper, different categories)
print("TEST 7: Paper uniqueness check")
print("-" * 40)
from src.core.database_model import is_same_identity
paper_a = Paper(
    doi="10.1234/unique.9999",
    title="Same Paper",
    category=cats[0],
    authors="A",
    date="2024-01-01",
    paper_url="https://example.com"
)
paper_b = Paper(
    doi="10.1234/unique.9999",
    title="Same Paper",
    category=cats[1],  # Different category
    authors="A",
    date="2024-01-01",
    paper_url="https://example.com"
)
is_same = is_same_identity(paper_a, paper_b)
print(f"  Paper A: DOI={paper_a.doi}, Category={paper_a.category}")
print(f"  Paper B: DOI={paper_b.doi}, Category={paper_b.category}")
print(f"  Same identity: {is_same}")
success7 = is_same  # Should be same (DOI matches)
print(f"  Result: {'PASS' if success7 else 'FAIL'}\n")

# SUMMARY
print("="*60)
print("TEST SUMMARY")
print("="*60)
all_tests = [
    ("Normalization", success1),
    ("Deduplication", success2),
    ("Multi-category validation", success3),
    ("Chinese semicolon handling", success4),
    ("Max category limit", success5),
    ("Empty/None handling", success6),
    ("Paper uniqueness", success7),
]

passed = sum(1 for _, result in all_tests if result)
total = len(all_tests)

for name, result in all_tests:
    status = "PASS" if result else "FAIL"
    print(f"  [{status}] {name}")

print(f"\nTotal: {passed}/{total} tests passed")
print("="*60)

if passed == total:
    print("\n[SUCCESS] All multi-category features working correctly!")
    sys.exit(0)
else:
    print(f"\n[WARNING] {total - passed} test(s) failed")
    sys.exit(1)
