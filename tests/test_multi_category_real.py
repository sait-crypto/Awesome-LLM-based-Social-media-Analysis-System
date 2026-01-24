#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多分类功能真实场景测试
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

from src.core.update_file_utils import UpdateFileUtils
from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

config = get_config_instance()
utils = UpdateFileUtils()

# 获取真实的分类列表
active_cats = config.get_active_categories()
cat_names = [c['unique_name'] for c in active_cats][:5]

print("[OK] 所有模块导入成功\n")
print(f"可用分类列表（前5个）: {cat_names}\n")

# 测试1：使用真实分类的多分类验证
print("=== 测试1：使用真实分类的多分类验证 ===")
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
    valid, errors , _= paper.validate_paper_fields(config, check_required=True, check_non_empty=True)
    print(f"输入分类: {multi_cat}")
    print(f"验证结果: {'✓ 通过' if valid else '✗ 失败'}")
    if not valid:
        print(f"错误: {errors}")
    else:
        print(f"规范化后: {paper.category}")
    print()

# 测试2：混合的分隔符处理
print("=== 测试2：混合的分隔符处理 ===")
if len(cat_names) >= 3:
    test_val = f"{cat_names[0]}；{cat_names[1]};{cat_names[2]}"
    normalized = utils.normalize_category_value(test_val, config)
    print(f"输入（混合英文和中文分号）: {test_val}")
    print(f"规范化后: {normalized}")
    parts = [p for p in normalized.split(';') if p]
    print(f"分类数: {len(parts)}\n")

# 测试3：空值和边界情况
print("=== 测试3：边界情况处理 ===")
test_cases = [
    "",
    "   ",
    None,
]
for i, test_val in enumerate(test_cases):
    normalized = utils.normalize_category_value(test_val, config)
    print(f"输入 #{i+1}: {repr(test_val)} -> {repr(normalized)}")
print()

# 测试4：README多分类行生成（模拟）
print("=== 测试4：README多分类行生成模拟 ===")
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
    
    # 模拟multi-category行生成
    parts = [p.strip() for p in paper.category.split(';') if p.strip()]
    if len(parts) > 1:
        links = []
        for uname in parts:
            display = config.get_category_field(uname, 'name') or uname
            # 模拟_slug
            anchor = display.lower().replace(' ', '-')
            links.append(f"[{display}](#{anchor})")
        multi_line = f"multi-category：{', '.join(links)}"
        print(f"论文: {paper.title}")
        print(f"分类: {paper.category}")
        print(f"多分类行: {multi_line}\n")

# 测试5：GUI模型 - 多分类字符串到list的转换
print("=== 测试5：GUI模型 - 多分类收集 ===")
if len(cat_names) >= 2:
    # 模拟GUI中收集多个category下拉框的值
    gui_selections = [cat_names[0], cat_names[1]]  # 模拟GUI中选择的值
    category_str = ";".join(gui_selections)
    print(f"GUI选择: {gui_selections}")
    print(f"收集后的字符串: {category_str}")
    
    # 验证反向转换
    reverse = [p for p in category_str.split(';') if p]
    print(f"反向转换: {reverse}")
    print(f"一致性检查: {'✓ 通过' if reverse == gui_selections else '✗ 失败'}\n")

# 测试6：Paper间的唯一性检查
print("=== 测试6：Paper唯一性检查（同一论文不同分类） ===")
paper1 = Paper(
    doi="10.1234/unique.9999",
    title="Unique Paper A",
    authors="Author",
    date="2024-01-01",
    category=cat_names[0] if cat_names else "test",
    paper_url="https://example.com"
)
paper2 = Paper(
    doi="10.1234/unique.9999",  # 相同DOI，不同分类
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
print(f"是否为同一论文: {'✓ 是' if result else '✗ 否'}")
print("（注：多分类不影响唯一性判断，仅基于DOI和Title）\n")

print("✓ 所有实际场景测试完成！")
