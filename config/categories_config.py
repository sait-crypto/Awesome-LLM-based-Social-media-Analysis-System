"""
分类配置文件

重要说明：
1. unique_name字段是分类的唯一标识符，不可重复
2. order字段决定分类在Excel和README中的显示顺序，必须唯一
3. enabled=false的分类会被系统忽略，相关论文不会出现在该分类下
"""

CATEGORIES_CONFIG = {
    "config_version": "1.0",
    "last_updated": "2025-01-01",
    
    # 分类列表，按order排序
    "categories": [
        {
            "unique_name": "make_cot_short",
            "order": 0,                     # 排序顺序，0为第一个
            "name": "Make Long CoT Short",  # 显示名称
            "enabled": True,                # 是否启用该分类
        },
        {
            "unique_name": "make_cot_strong",
            "order": 1,
            "name": "Build SLM with Strong Reasoning Ability",
            "enabled": True,
        },
        {
            "unique_name": "efficient_decoding",
            "order": 2,
            "name": "Let Decoding More Efficient",
            "enabled": True,
        },
        {
            "unique_name": "multimodal_reasoning",
            "order": 3,
            "name": "Efficient Multimodal Reasoning",
            "enabled": True,
        },
        {
            "unique_name": "agentic_reasoning",
            "order": 4,
            "name": "Efficient Agentic Reasoning",
            "enabled": True,
        },
        {
            "unique_name": "evaluation_benchmarks",
            "order": 5,
            "name": "Evaluation and Benchmarks",
            "enabled": True,
        },
        {
            "unique_name": "background_papers",
            "order": 6,
            "name": "Background Papers",
            "enabled": True,
        },
        {
            "unique_name": "competition",
            "order": 7,
            "name": "Competition",
            "enabled": True,
        },
    ]
}

# 验证函数
def validate_categories_config():
    """
    验证分类配置的有效性
    
    返回: (是否有效, 错误信息列表)
    """
    errors = []
    
    # 检查unique_name唯一性
    unique_names = {}
    for category in CATEGORIES_CONFIG["categories"]:
        unique_name = category.get("unique_name")
        if unique_name is None:
            errors.append(f"分类缺少unique_name字段: {category}")
            continue
            
        if unique_name in unique_names:
            errors.append(f"unique_name {unique_name} 重复")
        else:
            unique_names[unique_name] = True
    
    # 检查order唯一性
    orders = {}
    for category in CATEGORIES_CONFIG["categories"]:
        order = category.get("order")
        if order is None:
            errors.append(f"分类 {category.get('unique_name')} 缺少order字段")
            continue
            
        if order in orders:
            errors.append(f"order {order} 重复: {orders[order]} 和 {category['unique_name']}")
        else:
            orders[order] = category["unique_name"]
    
    # 检查name不为空
    for category in CATEGORIES_CONFIG["categories"]:
        name = category.get("name", "").strip()
        if not name:
            errors.append(f"分类 {category.get('unique_name')} 的name不能为空")
    
    return len(errors) == 0, errors

# 配置验证
if __name__ == "__main__":
    is_valid, error_list = validate_categories_config()
    if is_valid:
        print("✅ 分类配置验证通过")
    else:
        print("❌ 分类配置验证失败:")
        for error in error_list:
            print(f"   - {error}")
        exit(1)