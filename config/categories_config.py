"""
分类配置文件

重要说明：
1. unique_name字段是分类的唯一标识符，不可重复，用于内部存储和系统处理
2. order字段决定分类在Excel和README中的显示顺序，必须唯一
3. enabled=false的分类会被系统忽略，相关论文不会出现在该分类下
4. primary_category字段用于表示二级分类所属的一级分类，一级分类的primary_category应为None。
   注意：`primary_category` 应使用父类的 `unique_name` 字符串进行引用，**不要使用 `order` 作为标识**。order 仅用于显示排序，可随时修改。
5. name字段用于README中的显示，可与其他分类重复。系统支持按name查询分类但会输出警告（建议使用unique_name）
6. 请勿随意修改已有分类的unique_name和order，以免影响已有数据

类别标识规则：
- name 和 unique_name 都可用于表示一个分类，但建议统一使用 unique_name
- 使用 name 进行查询时，系统会返回第一个匹配的分类，并输出 DeprecationWarning
- 内部存储始终使用 unique_name 作为标识（在paper_database、submit_gui、更新文件等处）
- 仅在 README 生成时使用 name 作为显示名称
"""

# =========================================类别变更列表=========================================
"""
因为分类需要频繁调整和优化，且已有论文数据需要保持一致性，因此需要一个自动化的类别变更处理机制
CATEGORIES_CHANGE_LIST用于自动处理类变更，
如果发生了：
    1.论文分类集体变更
    2.分类unique_name变更
建议在此列表中添加变更记录项，交由系统自动处理，将旧 unique_name 替换为新 unique_name，而非手动处理
(变更逻辑在normalize_category_value() 函数中)

列表元素格式：
    {
        "old_unique_name": "旧unique_name",   # 旧的唯一标识符（被替换）
        "new_unique_name": "新unique_name",   # 新的唯一标识符（替换目标）
    }

所有相关文件（更新文件Excel/JSON、database等）进行修改时会自动应用这些变更
"""

CATEGORIES_CHANGE_LIST = [
    # 在这里添加分类变更记录
    # 格式示例：
    # {
    #     "old_unique_name": "Base Techniques",
    #     "new_unique_name": "Hate Speech Analysis",
    # },
    {
        "old_unique_name": "Social Content Generation",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Comment Generation",   # 新的唯一标识符（替换目标）
    },
    {
        "old_unique_name": "Malicious Bot Detection",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Malicious User Detection",   # 新的唯一标识符（替换目标）
    }
]

# =========================================分类配置=========================================
CATEGORIES_CONFIG = {
    "config_version": "2.0",
    "last_updated": "2026-01-14",
    
    # 分类列表，按order排序
    "categories": [

        # ============一级分类===============
        {
            "unique_name": "Uncategorized",
            "order": 0,                     # 排序顺序，0为第一个
            "name": "Uncategorized",  # 显示名称
            "primary_category": None,# 所属一级分类，None表示本身为一级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  未分类",
        },
        {
            "unique_name": "Base Techniques",
            "order": 99,                     # 排序顺序，0为第一个
            "name": "Base Techniques",  # 显示名称
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  基础技术",
        },
        {
            "unique_name": "Perception and Classification",
            "order": 100,                     # 排序顺序，0为第一个
            "name": "Perception and Classification",  # 显示名称
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  感知与分类",
        },
        {
            "unique_name": "Understanding",
            "order": 101,                     # 排序顺序，0为第一个
            "name": "Understanding",  # 显示名称
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  理解",
        },
        {
            "unique_name": "Generation",
            "order": 102,                     # 排序顺序，0为第一个
            "name": "Generation",  # 显示名称
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  生成",
        },
        {
            "unique_name": "Simulation and Deduction",
            "order": 103,                     # 排序顺序，0为第一个
            "name": "Simulation and Deduction",  # 显示名称
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  仿真与推理",
        },
        {
            "unique_name": "Social Media Security",
            "order": 104,                     # 排序顺序，0为第一个
            "name": "Social Media Security",  # 显示名称
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  社交媒体安全",
        },
        {
            "unique_name": "Other",
            "order": 200,
            "name": "Other",
            "primary_category": None,# None表示本身为1级分类
            "enabled": True,
            "description": "[一级分类] —  其他",
        },
        
        # ============二级分类===============
        {
            "unique_name": "Hate Speech Analysis",
            "order": 1,                     
            "name": "Hate Speech Analysis",  # 显示名称
            "primary_category": "Perception and Classification",# 所属一级分类，使用一级分类的 `unique_name` 表示
            "enabled": True,                # 是否启用该分类
            "description": "[二级分类]（Perception and Classification） —  仇恨言论分析",
        },
        {
            "unique_name": "Misinformation Analysis",
            "order": 2,
            "name": "Misinformation Analysis",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  虚假信息分析",
        },
        {
            "unique_name": "Controversy Analysis",
            "order": 3,
            "name": "Controversy Analysis",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  争议内容分析",
        },
        {
            "unique_name": "Sentiment Analysis",
            "order": 4,
            "name": "Sentiment Analysis",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  情感分析",
        },

        {
            "unique_name": "Multimodal Analysis",
            "order": 5,
            "name": "Meme Analysis",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  模因/多模态分析",
        },
        {
            "unique_name": "Steganography Detection",
            "order": 6,
            "name": "Steganography Detection",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  隐写检测",
        },
        {
            "unique_name": "User Stance Detection",
            "order": 7,
            "name": "User Stance Detection",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  用户立场检测",
        },
        {
            "unique_name": "Malicious User Detection",
            "order": 8,
            "name": "Malicious User Detection",
            "primary_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  恶意用户检测",
        },
        {
            "unique_name": "Event Extraction",
            "order": 9,
            "name": "Event Extraction",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  事件抽取",
        },
        {
            "unique_name": "Topic Modeling",
            "order": 10,
            "name": "Topic Modeling",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  主题建模",
        },
        {
            "unique_name": "Social Psychological Phenomena Analysis",
            "order": 11,
            "name": "Social Psychological Phenomena Analysis",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  社会心理现象分析",
        },
        {
            "unique_name": "Social Popularity Prediction",
            "order": 12,
            "name": "Social Popularity Prediction",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  社交流行度预测",
        },
        {
            "unique_name": "Community Detection",
            "order": 13,
            "name": "User Identity Understanding",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  用户身份理解（Community Detection）",
        },
        {
            "unique_name": "User Profiling",
            "order": 14,
            "name": "User Profiling",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  用户画像",
        },
        {
            "unique_name": "User Behavior Prediction",
            "order": 15,
            "name": "User Behavior Prediction",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  用户行为预测",
        },
        {
            "unique_name": "Dynamic Community Analysis",
            "order": 16,
            "name": "Dynamic Community Analysis",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  动态社区分析",
        },
        {
            "unique_name": "Information Diffusion Analysis",
            "order": 17,
            "name": "Information Diffusion Analysis",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  信息扩散分析",
        },
        {
            "unique_name": "Recommender System",
            "order": 18,
            "name": "Recommender System",
            "primary_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  推荐系统",
        },
        {
            "unique_name": "Comment Generation",
            "order": 19,
            "name": "Comment Generation",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  评论生成",
        },
        {
            "unique_name": "Debate Generation",
            "order": 20,
            "name": "Debate Generation",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  辩论生成",
        },

        {
            "unique_name": "Rumor Refutation Generation",
            "order": 21,
            "name": "Rumor Refutation Generation",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  谣言反驳生成",
        },
        {
            "unique_name": "Psychological Healing",
            "order": 22,
            "name": "Psychological Healing",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  心理疗愈/心理干预",
        },
        {
            "unique_name": "Misinformation Generation",
            "order": 23,
            "name": "Misinformation Generation",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  虚假信息生成",
        },
        {
            "unique_name": "Humor Generation",
            "order": 24,
            "name": "Humor Generation",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  幽默信息生成",
        },
        {
            "unique_name": "Social Bots",
            "order": 25,
            "name": "Social Bots",
            "primary_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  社交机器人",
        },
        {
            "unique_name": "Social Simulation",
            "order": 26,
            "name": "Social Simulation",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  社会仿真",
        },
        {
            "unique_name": "Social Network Simulation",
            "order": 27,
            "name": "Social Network Simulation",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  社会网络仿真",
        },
        {
            "unique_name": "Town/Community Simulation",
            "order": 28,
            "name": "Town/Community Simulation",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  城镇/社区仿真",
        },
        {
            "unique_name": "Game Simulation",
            "order": 29,
            "name": "Game Simulation",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  游戏仿真",
        },
        {
            "unique_name": "Family Simulation",
            "order": 30,
            "name": "Family Simulation",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  家庭仿真",
        },
        {
            "unique_name": "Macrosocial Phenomena Analysis",
            "order": 31,
            "name": "Macrosocial Phenomena Analysis",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  宏观社会现象分析",
        },
        {
            "unique_name": "Frontier Applications",
            "order": 32,
            "name": "Frontier Applications",
            "primary_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  前沿应用",
        },



    ],
    
    # ============= 分类变更列表 =============
    # 用于自动处理旧 unique_name 向新 unique_name 的转换
    # 当分类的 unique_name 发生变更时，在此列表中添加映射关系
    # normalize_category_value 会自动应用这些变更规则
    "categories_change_list": CATEGORIES_CHANGE_LIST,
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
    
    # 检查order唯一性，并建立order->category映射
    orders = {}
    categories_by_order = {}
    for category in CATEGORIES_CONFIG["categories"]:
        order = category.get("order")
        if order is None:
            errors.append(f"分类 {category.get('unique_name')} 缺少order字段")
            continue
            
        if order in orders:
            errors.append(f"order {order} 重复: {orders[order]} 和 {category['unique_name']}")
        else:
            orders[order] = category["unique_name"]
            categories_by_order[order] = category
    
    # 检查 primary_category 合法性：
    # - 一级分类（primary_category 为 None）应为 None
    # - 二级分类（primary_category 非 None）必须引用存在的一级分类（用 unique_name 表示），且被引用的分类的 primary_category 必须为 None
    # 为便于查找，建立 unique_name -> category 映射
    categories_by_unique = {c.get('unique_name'): c for c in CATEGORIES_CONFIG['categories']}
    for category in CATEGORIES_CONFIG["categories"]:
        pc = category.get("primary_category", None)
        if pc is None:
            continue
        # 如果 primary_category 非 None，则应为字符串并且存在于 categories_by_unique
        if not isinstance(pc, str):
            errors.append(f"分类 {category.get('unique_name')} 的 primary_category 应为父分类的 unique_name(str)，当前为 {pc!r}")
            continue
        if pc not in categories_by_unique:
            errors.append(f"分类 {category.get('unique_name')} 的 primary_category '{pc}' 不存在")
            continue
        parent = categories_by_unique[pc]
        if parent.get('primary_category') is not None:
            errors.append(f"分类 {category.get('unique_name')} 的 primary_category '{pc}' 指向的不是一级分类 ({parent.get('unique_name')})")

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