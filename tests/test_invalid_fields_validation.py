#!/usr/bin/env python3
"""
测试 invalid_fields 字段验证功能
"""
import sys
sys.path.insert(0, '.')

from src.utils import validate_invalid_fields

def test_cases():
    """测试各种情况"""
    allowed_vars = [
        'doi', 'title', 'authors', 'date', 'category', 'paper_url',
        'abstract', 'invalid_fields', 'pipeline_image', 'paper_file'
    ]
    test_data = [
        # (输入, 期望有效, 描述)
        ("", True, "空字符串应该有效"),
        ("   ", True, "只有空格应该有效"),
        (None, True, "None 应该有效"),
        ("doi", True, "单个 variable 应该有效"),
        ("doi|title", True, "| 分隔 variable 应该有效"),
        ("doi| title |authors", True, "带空格的 variable 列表应该有效"),
        ("doi||title", True, "空项会被过滤"),
        ("doi,title", False, "旧逗号分隔格式应无效"),
        ("0|1", False, "数字ID格式应无效"),
        ("unknown_field", False, "不存在的 variable 应无效"),
        ("doi|unknown_field", False, "包含不存在 variable 应无效"),
        ("bad-name", False, "非法变量命名应无效"),
    ]
    
    print("=" * 70)
    print("测试 validate_invalid_fields 函数")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for input_val, expected_valid, description in test_data:
        valid, error = validate_invalid_fields(input_val, allowed_variables=allowed_vars)
        
        status = "✓ PASS" if valid == expected_valid else "✗ FAIL"
        if valid == expected_valid:
            passed += 1
        else:
            failed += 1
        
        print(f"\n{status}")
        print(f"  输入: {repr(input_val)}")
        print(f"  描述: {description}")
        print(f"  期望有效: {expected_valid}")
        print(f"  实际有效: {valid}")
        if error:
            print(f"  错误信息: {error}")
    
    print("\n" + "=" * 70)
    print(f"测试结果: 通过 {passed}/{len(test_data)}, 失败 {failed}/{len(test_data)}")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = test_cases()
    sys.exit(0 if success else 1)
