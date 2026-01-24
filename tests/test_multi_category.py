#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多分类功能测试脚本
"""
from src.core.update_file_utils import UpdateFileUtils
from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

print("✓ 所有模块导入成功\n")

# 测试1：单分类规范化
config = get_config_instance()
utils = UpdateFileUtils()

print("=== 测试1：单分类规范化 ===")
test_val = "NLP"
normalized = utils.normalize_category_value(test_val, config)
print(f"输入: {test_val}")
print(f"输出: {normalized}\n")

# 测试2：多分类规范化
print("=== 测试2：多分类规范化（分号分隔） ===")
test_val = "NLP;CV"
normalized = utils.normalize_category_value(test_val, config)
print(f"输入: {test_val}")
print(f"输出: {normalized}")
print(f"分类数量: {len([c for c in normalized.split(';') if c])}\n")

# 测试3：多分类去重
print("=== 测试3：多分类去重 ===")
test_val = "NLP;CV;NLP"
normalized = utils.normalize_category_value(test_val, config)
print(f"输入（包含重复）: {test_val}")
print(f"输出（去重后）: {normalized}\n")

# 测试4：中文分号分隔
print("=== 测试4：中文分号分隔 ===")
test_val = "NLP；CV"
normalized = utils.normalize_category_value(test_val, config)
print(f"输入: {test_val}")
print(f"输出: {normalized}\n")

# 测试5：Paper对象多分类验证
print("=== 测试5：Paper对象多分类验证 ===")
paper = Paper(
    doi="10.xxxx/test",
    title="Test Paper",
    authors="Author 1; Author 2",
    date="2024-01-01",
    category="NLP;CV",
    paper_url="https://example.com",
    summary_motivation="test",
    summary_innovation="test",
    summary_method="test",
    summary_conclusion="test"
)
valid, errors , _= paper.validate_paper_fields(config, check_required=True, check_non_empty=True)
print(f"验证结果: {'✓ 通过' if valid else '✗ 失败'}")
if errors:
    print(f"错误: {errors}")
else:
    print(f"Paper category 规范化后: {paper.category}\n")

# 测试6：超过最大分类数的限制
print("=== 测试6：超过最大分类数的限制 ===")
max_cat = int(config.settings['database'].get('max_categories_per_paper', 4))
print(f"配置最大分类数: {max_cat}")
# 使用真实存在的分类
active_cats = [c['unique_name'] for c in config.get_active_categories()][:10]
test_val = ";".join(active_cats)
normalized = utils.normalize_category_value(test_val, config)
actual_count = len([c for c in normalized.split(';') if c])
print(f"输入分类数: {len(active_cats)}")
print(f"实际输出分类数: {actual_count}")
print(f"限制生效: {'✓ 是' if actual_count <= max_cat else '✗ 否'}\n")

# 测试7：分类验证 - 包含无效分类
print("=== 测试7：分类验证 - 包含无效分类 ===")
paper_invalid = Paper(
    doi="10.xxxx/test2",
    title="Test Paper 2",
    authors="Author",
    date="2024-01-01",
    category="INVALID_CATEGORY",
    paper_url="https://example.com",
    summary_motivation="test",
    summary_innovation="test",
    summary_method="test",
    summary_conclusion="test"
)
valid, errors, _ = paper_invalid.validate_paper_fields(config, check_required=True, check_non_empty=True)
print(f"验证结果: {'✓ 通过' if valid else '✗ 失败（预期）'}")
if errors:
    print(f"错误信息: {errors[0]}\n")

# 测试8：分类验证 - 包含重复项
print("=== 测试8：分类验证 - 包含重复项检测 ===")
paper_dup = Paper(
    doi="10.xxxx/test3",
    title="Test Paper 3",
    authors="Author",
    date="2024-01-01",
    category="NLP;NLP;CV",
    paper_url="https://example.com",
    summary_motivation="test",
    summary_innovation="test",
    summary_method="test",
    summary_conclusion="test"
)
valid, errors, _ = paper_dup.validate_paper_fields(config, check_required=True, check_non_empty=True)
print(f"输入category（含重复）: NLP;NLP;CV")
print(f"验证结果: {'通过（去重后）' if valid else '失败'}")
print(f"规范化后: {paper_dup.category}")
if not valid and errors:
    print(f"错误: {errors}")
print()

print("✓ 所有测试完成！")
