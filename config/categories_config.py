"""
分类配置文件

重要说明：
1. unique_name字段是分类的唯一标识符，不可重复
2. order字段决定分类在Excel和README中的显示顺序，必须唯一
3. enabled=false的分类会被系统忽略，相关论文不会出现在该分类下
"""

CATEGORIES_CONFIG = {
    "config_version": "2.0",
    "last_updated": "2026-01-14",
    
    # 分类列表，按order排序
    "categories": [
        {
            "unique_name": "Uncategorized",
            "order": 0,                     # 排序顺序，0为第一个
            "name": "Uncategorized",  # 显示名称
            "enabled": True,                # 是否启用该分类
        },
        {
            "unique_name": "Hate Speech Analysis",
            "order": 1,                     
            "name": "Hate Speech Analysis",  # 显示名称
            "enabled": True,                # 是否启用该分类
        },
        {
            "unique_name": "Sentiment Analysis",
            "order": 2,
            "name": "Sentiment Analysis",
            "enabled": True,
        },
        {
            "unique_name": "Misinformation Analysis",
            "order": 3,
            "name": "Misinformation Analysis",
            "enabled": True,
        },
        {
            "unique_name": "Multimodal Analysis",
            "order": 4,
            "name": "Meme Analysis",
            "enabled": True,
        },
        {
            "unique_name": "Steganography Detection",
            "order": 5,
            "name": "Steganography Detection",
            "enabled": True,
        },
        {
            "unique_name": "Event Extraction",
            "order": 6,
            "name": "Event Extraction",
            "enabled": True,
        },
        {
            "unique_name": "Topic Modeling",
            "order": 7,
            "name": "Topic Modeling",
            "enabled": True,
        },
        {
            "unique_name": "User Opinion Mining",
            "order": 8,
            "name": "User Opinion Mining",
            "enabled": True,
        },
        {
            "unique_name": "User Profiling",
            "order": 9,
            "name": "User Profiling",
            "enabled": True,
        },
        {
            "unique_name": "User Behavior Prediction",
            "order": 10,
            "name": "User Behavior Prediction",
            "enabled": True,
        },
        {
            "unique_name": "Social Content Generation",
            "order": 11,
            "name": "Social Content Generation",
            "enabled": True,
        },
        {
            "unique_name": "Information Diffusion Analysis",
            "order": 12,
            "name": "Information Diffusion Analysis",
            "enabled": True,
        },
        {
            "unique_name": "Macrosocial Phenomena Analysis",
            "order": 13,
            "name": "Macrosocial Phenomena Analysis",
            "enabled": True,
        },
        {
            "unique_name": "Social Simulation",
            "order": 14,
            "name": "Social Simulation",
            "enabled": True,
        },
        {
            "unique_name": "Malicious Bot Detection",
            "order": 15,
            "name": "Malicious Bot Detection",
            "enabled": True,
        },
        {
            "unique_name": "Community Detection",
            "order": 16,
            "name": "Community Detection",
            "enabled": True,
        },
        {
            "unique_name": "Dynamic Community Analysis",
            "order": 17,
            "name": "Dynamic Community Analysis",
            "enabled": True,
        },
        {
            "unique_name": "Other",
            "order": 100,
            "name": "Other",
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