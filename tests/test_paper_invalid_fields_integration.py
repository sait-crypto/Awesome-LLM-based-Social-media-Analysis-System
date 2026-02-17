#!/usr/bin/env python3
"""
集成测试：验证 Paper 对象中的 invalid_fields 验证
"""
import sys
sys.path.insert(0, '.')

from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

def test_paper_invalid_fields_validation():
    """测试 Paper 对象的 invalid_fields 验证"""
    
    config = get_config_instance()
    
    test_cases = [
        {
            "name": "有效的 invalid_fields（多个variable）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35804",
                title="Test Paper",
                authors="Author One",
                date="2025-01-01",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields="doi|title|authors"
            ),
            "expect_valid": True
        },
        {
            "name": "有效的 invalid_fields（带空格）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35805",
                title="Test Paper 2",
                authors="Author Two",
                date="2025-01-02",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields="doi | title | authors"
            ),
            "expect_valid": True
        },
        {
            "name": "无效的 invalid_fields（旧ID格式）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35806",
                title="Test Paper 3",
                authors="Author Three",
                date="2025-01-03",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields="0|1|2"
            ),
            "expect_valid": False
        },
        {
            "name": "无效的 invalid_fields（旧逗号格式）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35807",
                title="Test Paper 4",
                authors="Author Four",
                date="2025-01-04",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields="doi,title"
            ),
            "expect_valid": False
        },
        {
            "name": "无效的 invalid_fields（包含不存在variable）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35808",
                title="Test Paper 5",
                authors="Author Five",
                date="2025-01-05",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields="doi|unknown_field|authors"
            ),
            "expect_valid": False
        },
        {
            "name": "无效的 invalid_fields（非法变量名）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35809",
                title="Test Paper 6",
                authors="Author Six",
                date="2025-01-06",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields="bad-name|doi"
            ),
            "expect_valid": False
        },
        {
            "name": "有效的 invalid_fields（空字符串）",
            "paper": Paper(
                doi="10.1609/icwsm.v19i1.35810",
                title="Test Paper 7",
                authors="Author Seven",
                date="2025-01-07",
                category="Test",
                paper_url="https://example.com/paper",
                abstract="Abstract",
                invalid_fields=""
            ),
            "expect_valid": True
        },
    ]
    
    print("=" * 80)
    print("集成测试：Paper 对象的 invalid_fields 验证")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        paper = test_case["paper"]
        expect_valid = test_case["expect_valid"]
        
        # 验证论文
        valid, errors, _ = paper.validate_paper_fields(
            config,
            check_required=True,
            check_non_empty=True
        )
        
        # 检查 invalid_fields 相关的错误
        invalid_fields_error_found = any('invalid_fields' in str(e) for e in errors)
        
        # 如果期望无效且包含 invalid_fields 错误，或者期望有效且没有 invalid_fields 错误，就是通过
        if expect_valid:
            # 期望有效：不应该有 invalid_fields 相关的错误
            test_passed = not invalid_fields_error_found
        else:
            # 期望无效：应该有 invalid_fields 相关的错误
            test_passed = invalid_fields_error_found
        
        status = "✓ PASS" if test_passed else "✗ FAIL"
        if test_passed:
            passed += 1
        else:
            failed += 1
        
        print(f"\n{status}")
        print(f"  测试名称: {test_case['name']}")
        print(f"  invalid_fields: {repr(paper.invalid_fields)}")
        print(f"  期望有效: {expect_valid}")
        print(f"  实际有效: {valid}")
        print(f"  包含 invalid_fields 错误: {invalid_fields_error_found}")
        if errors:
            print(f"  错误信息:")
            for error in errors:
                print(f"    - {error}")
    
    print("\n" + "=" * 80)
    print(f"测试结果: 通过 {passed}/{len(test_cases)}, 失败 {failed}/{len(test_cases)}")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = test_paper_invalid_fields_validation()
    sys.exit(0 if success else 1)
