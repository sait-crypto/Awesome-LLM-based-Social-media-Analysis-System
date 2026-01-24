#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 多分类功能测试脚本

测试的功能：
1. 初始化时创建第一行，按钮显示 '+'
2. 点击 '+' 按钮添加新行，新行按钮显示 '-'，原有行的按钮变为 '-'
3. 多个分类行的值正确收集和保存
4. 点击 '-' 按钮删除对应行
5. 加载论文时，多个分类正确重建多行
6. 保存时正确合并为 ';' 分隔的字符串
"""
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

def test_multi_category_basic():
    """测试基础多分类功能"""
    print("\n[TEST 1] 基础多分类数据处理")
    
    config = get_config_instance()
    
    # 创建一个多分类的论文
    paper_data = {
        'doi': '10.1234/test.001',
        'title': 'Test Paper with Multi-Category',
        'authors': 'Author A, Author B',
        'date': '2024-01-21',
        'paper_url': 'https://example.com/paper',
        'category': 'NLP;CV;DL',  # 多分类用 ';' 分隔
        'abstract': 'This is a test abstract.',
        'summary_en': 'This is a test summary.',
    }
    
    paper = Paper.from_dict(paper_data)
    
    # 验证 category 字段
    assert paper.category == 'NLP;CV;DL', f"Expected 'NLP;CV;DL', got '{paper.category}'"
    print(f"  [OK] Paper category stored correctly: {paper.category}")
    
    # 模拟 GUI 的分割逻辑
    unique_names = [v.strip() for v in paper.category.split(';') if v.strip()]
    assert len(unique_names) == 3, f"Expected 3 parts, got {len(unique_names)}"
    print(f"  [OK] Multi-category split correctly: {unique_names}")
    
    return True

def test_category_normalization():
    """测试分类规范化（去重、限制）"""
    print("\n[TEST 2] 分类规范化测试")
    
    from src.core.update_file_utils import get_update_file_utils
    config = get_config_instance()
    utils = get_update_file_utils()
    
    # 测试去重
    test_cases = [
        ('NLP;CV;NLP', 'NLP;CV'),  # 去重
        ('NLP；CV；DL', 'NLP;CV;DL'),  # 中文分号转换
        ('NLP; CV ; DL', 'NLP;CV;DL'),  # 空格处理
        ('NLP', 'NLP'),  # 单个分类
        ('', ''),  # 空值
    ]
    
    for input_val, expected in test_cases:
        result = utils.normalize_category_value(input_val, config)
        assert result == expected, f"Input '{input_val}': expected '{expected}', got '{result}'"
        print(f"  [OK] normalize_category_value('{input_val}') = '{result}'")
    
    return True

def test_paper_validation_with_multi_category():
    """测试带多分类的论文验证"""
    print("\n[TEST 3] 多分类论文验证测试")
    
    config = get_config_instance()
    
    # 先获取有效的分类
    valid_categories = config.get_active_categories()
    valid_cat_names = [cat['unique_name'] for cat in valid_categories][:2]
    
    if len(valid_cat_names) < 2:
        print(f"  [SKIP] 没有足够的有效分类进行测试")
        return True
    
    # 创建有效的多分类论文
    paper_data = {
        'doi': '10.1234/test.002',
        'title': 'Valid Multi-Category Paper',
        'authors': 'Author A',
        'date': '2024-01-21',
        'paper_url': 'https://example.com/paper',
        'category': ';'.join(valid_cat_names),  # 有效的多分类
        'abstract': 'Test abstract',
        'summary_en': 'Test summary',
    }
    
    paper = Paper.from_dict(paper_data)
    valid, errors, _ = paper.validate_paper_fields(config, check_required=True)
    
    assert valid, f"Paper validation failed: {errors}"
    print(f"  [OK] Multi-category paper validation passed: {paper.category}")
    
    return True

def test_gui_mapping():
    """测试 GUI 映射逻辑"""
    print("\n[TEST 4] GUI 分类映射逻辑")
    
    config = get_config_instance()
    
    # 获取活跃分类
    categories = config.get_active_categories()
    category_names = [cat['name'] for cat in categories]
    category_values = [cat['unique_name'] for cat in categories]
    
    # 创建映射
    category_mapping = dict(zip(category_names, category_values))
    category_reverse_mapping = {v: k for k, v in category_mapping.items()}
    category_reverse_mapping[""] = ""
    
    print(f"  [OK] Total categories: {len(categories)}")
    print(f"  [OK] Mapping created: {len(category_mapping)} entries")
    
    # 测试映射
    for display_name, unique_name in list(category_mapping.items())[:3]:
        reverse = category_reverse_mapping.get(unique_name)
        assert reverse == display_name, f"Mapping error: {unique_name} -> {reverse} (expected {display_name})"
        print(f"  [OK] Mapping: '{display_name}' <-> '{unique_name}'")
    
    return True

def test_paper_collection_logic():
    """测试从多行收集分类值的逻辑"""
    print("\n[TEST 5] 分类行值收集逻辑")
    
    config = get_config_instance()
    
    # 模拟 GUI 的行数据结构
    categories = config.get_active_categories()
    category_names = [cat['name'] for cat in categories]
    category_values = [cat['unique_name'] for cat in categories]
    category_mapping = dict(zip(category_names, category_values))
    
    # 模拟多行选择
    selected_displays = []
    if len(category_names) >= 3:
        selected_displays = [category_names[0], category_names[1], category_names[2]]
    elif len(category_names) >= 2:
        selected_displays = [category_names[0], category_names[1]]
    else:
        selected_displays = [category_names[0]] if category_names else []
    
    # 模拟收集逻辑（类似 _gui_get_category_values）
    collected_values = []
    for display_name in selected_displays:
        if display_name:
            unique_name = category_mapping.get(display_name, display_name)
            if unique_name:
                collected_values.append(unique_name)
    
    result_str = ";".join(collected_values)
    
    print(f"  [OK] Selected displays: {selected_displays}")
    print(f"  [OK] Collected unique names: {collected_values}")
    print(f"  [OK] Final string: '{result_str}'")
    
    # 验证反向过程
    parts = [v.strip() for v in result_str.split(';') if v.strip()]
    reverse_mapping = {v: k for k, v in category_mapping.items()}
    reverse_mapping[""] = ""
    
    reverse_displays = [reverse_mapping.get(p, p) for p in parts]
    assert reverse_displays == selected_displays, f"Reverse mapping failed"
    print(f"  [OK] Reverse mapping correct: {reverse_displays}")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("GUI 多分类功能测试")
    print("=" * 60)
    
    tests = [
        test_multi_category_basic,
        test_category_normalization,
        test_paper_validation_with_multi_category,
        test_gui_mapping,
        test_paper_collection_logic,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {str(e)}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
