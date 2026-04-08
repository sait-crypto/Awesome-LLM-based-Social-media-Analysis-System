"""
分类配置文件

重要说明：
1. unique_name字段是分类的唯一标识符，不可重复，用于内部存储和系统处理
2. order字段决定分类在Excel和README中的显示顺序，必须唯一
3. enabled=false的分类会被系统忽略，相关论文不会出现在该分类下
4. predecessor_category字段用于表示分类的直接上级分类，根分类的predecessor_category应为None，支持任意层级。
    注意：`predecessor_category` 应使用父类的 `unique_name` 字符串进行引用，**不要使用 `order` 作为标识**。order 仅用于显示排序，可随时修改。
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
    },
    {
        "old_unique_name": "Dynamic Community Analysis",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Community Detection and Analysis",   # 新的唯一标识符（替换目标）
    },
    {
        "old_unique_name": "User Participation Prediction",   # 旧的唯一标识符（被替换）
        "new_unique_name": "User Behavior Prediction",   # 新的唯一标识符（替换目标）
    },
    {
        "old_unique_name": "Town/Community Simulation",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Social Simulation",   # 新的唯一标识符（替换目标）
    },
    {
        "old_unique_name": "Community Detection",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Community Detection and Analysis",   # 新的唯一标识符（替换目标）
    },
    {
        "old_unique_name": "Multimodal Analysis",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Meme and Multimodal Understanding",   # 新的唯一标识符（替换目标）
    },
    {
        "old_unique_name": "Social Media Security",   # 旧的唯一标识符（被替换）
        "new_unique_name": "Ethics and Safety",   # 新的唯一标识符（替换目标）
    },
]

# =========================================分类配置=========================================
CATEGORIES_CONFIG = {
    "config_version": "2.0",
    "last_updated": "2026-01-14",
    
    # 分类列表，按order排序
    "categories": [

        # ============根分类===============
        {
            "unique_name": "Uncategorized",
            "order": 0,                     # 排序顺序，0为第一个
            "name": "Uncategorized",  # 显示名称
            "predecessor_category": None,# 直接上级分类，None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  未分类",
        },
        {
            "unique_name": "Base Techniques",
            "order": 99,                     # 排序顺序，0为第一个
            "name": "Base Techniques",  # 显示名称
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  基础技术",
        },
        {
            "unique_name": "Perception and Classification",
            "order": 100,                     # 排序顺序，0为第一个
            "name": "Perception and Classification",  # 显示名称
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  感知与分类",
        },
        {
            "unique_name": "Understanding",
            "order": 101,                     # 排序顺序，0为第一个
            "name": "Understanding",  # 显示名称
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  理解",
        },
        {
            "unique_name": "Generation",
            "order": 102,                     # 排序顺序，0为第一个
            "name": "Generation",  # 显示名称
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  生成",
        },
        {
            "unique_name": "Simulation and Deduction",
            "order": 103,                     # 排序顺序，0为第一个
            "name": "Simulation and Deduction",  # 显示名称
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  仿真与推理",
        },
        {
            "unique_name": "Ethics and Safety",
            "order": 104,                     # 排序顺序，0为第一个
            "name": "Ethics and Safety",  # 显示名称
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,                # 是否启用该分类
            "description": "[一级分类] —  伦理与安全",
        },
        {
            "unique_name": "Other",
            "order": 200,
            "name": "Other",
            "predecessor_category": None,# None表示本身为根分类
            "enabled": True,
            "description": "[一级分类] —  其他",
        },
        
        # ============非根分类===============
        {
            "unique_name": "Content-level Perception",
            "order": 1,                     
            "name": "Content-level Perception",  # 显示名称
            "predecessor_category": "Perception and Classification",# 直接上级分类，使用父分类的 `unique_name` 表示
            "enabled": True,                # 是否启用该分类
            "description": "[二级分类]（Perception and Classification） —  社交内容级别感知与分析",
        },
        {
            "unique_name": "Hate Speech Analysis",
            "order": 1,                     
            "name": "Hate Speech Analysis",  # 显示名称
            "predecessor_category": "Content-level Perception",# 直接上级分类，使用父分类的 `unique_name` 表示
            "enabled": True,                # 是否启用该分类
            "description": "[三级分类]（Content-level Perception） —  仇恨言论分析",
        },
        {
            "unique_name": "Misinformation Analysis",
            "order": 2,
            "name": "Misinformation Analysis",
            "predecessor_category": "Content-level Perception",
            "enabled": True,
            "description": "[三级分类]（Content-level Perception） —  虚假信息分析",
        },
        {
            "unique_name": "Controversy Analysis",
            "order": 3,
            "name": "Controversy Analysis",
            "predecessor_category": "Content-level Perception",
            "enabled": True,
            "description": "[三级分类]（Content-level Perception） — 争议内容分析",
        },
        {
            "unique_name": "Machine-generated Content Detection",
            "order": 4,
            "name": "Machine-generated Content Detection",
            "predecessor_category": "Content-level Perception",
            "enabled": True,
            "description": "[三级分类]（Content-level Perception） —  机器生成内容检测",
        },
        {
            "unique_name": "Sentiment Analysis",
            "order": 4,
            "name": "Sentiment Analysis",
            "predecessor_category": "Content-level Perception",
            "enabled": True,
            "description": "[三级分类]（Content-level Perception） —  情感分析",
        },
        {
            "unique_name": "Discourse and Pragmatic Analysis",
            "order": 6,
            "name": "Discourse and Pragmatic Analysis",
            "predecessor_category": "Content-level Perception",
            "enabled": True,
            "description": "[三级分类]（Content-level Perception） — 语篇与语用分析（包含幽默识别、委婉语识别、隐喻识别、吹牛识别等等）",
        },
        {
            "unique_name": "Sarcasm Detection",
            "order": 5,
            "name": "Sarcasm Detection",
            "predecessor_category": "Discourse and Pragmatic Analysis",
            "enabled": True,
            "description": "[四级分类]（Discourse and Pragmatic Analysis） —  讽刺检测",
        },
        {
            "unique_name": "Humor Recognition",
            "order": 6,
            "name": "Humor Recognition",
            "predecessor_category": "Discourse and Pragmatic Analysis",
            "enabled": True,
            "description": "[四级分类]（Discourse and Pragmatic Analysis） — 幽默识别",
        },
        {
            "unique_name": "Euphemism Recognition",
            "order": 6,
            "name": "Euphemism Recognition",
            "predecessor_category": "Discourse and Pragmatic Analysis",
            "enabled": True,
            "description": "[四级分类]（Discourse and Pragmatic Analysis） — 委婉语识别",
        },
        {
            "unique_name": "Metaphor Recognition",
            "order": 6,
            "name": "Metaphor Recognition",
            "predecessor_category": "Discourse and Pragmatic Analysis",
            "enabled": True,
            "description": "[四级分类]（Discourse and Pragmatic Analysis） — 隐喻识别",
        },
        {
            "unique_name": "Bragging Detection",
            "order": 6,
            "name": "Bragging Detection",
            "predecessor_category": "Discourse and Pragmatic Analysis",
            "enabled": True,
            "description": "[四级分类]（Discourse and Pragmatic Analysis） — 吹牛识别",
        },
        {
            "unique_name": "Macro-level Discourse Analysis",
            "order": 6,
            "name": "Macro-level Discourse Analysis",
            "predecessor_category": "Discourse and Pragmatic Analysis",
            "enabled": True,
            "description": "[四级分类]（Discourse and Pragmatic Analysis） — 宏观语篇分析",
        },
        {
            "unique_name": "User-level Perception",
            "order": 7,
            "name": "User-level Perception",
            "predecessor_category": "Perception and Classification",
            "enabled": True,
            "description": "[二级分类]（Perception and Classification） —  用户级别感知与分析",
        },
        {
            "unique_name": "User Stance Detection",
            "order": 7,
            "name": "User Stance Detection",
            "predecessor_category": "User-level Perception",
            "enabled": True,
            "description": "[三级分类]（User-level Perception） —  用户立场检测",
        },
        {#也许改为恶意与异常用户检测更合适？，因为可能有专注于检测异常而非恶意用户的论文
            "unique_name": "Malicious User Detection",
            "order": 8,
            "name": "Malicious User Detection",
            "predecessor_category": "User-level Perception",
            "enabled": True,
            "description": "[三级分类]（User-level Perception） — 恶意用户检测",
        },


        {
            "unique_name": "Meme and Multimodal Understanding",
            "order": 9,
            "name": "Meme and Multimodal Understanding",
            "predecessor_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） — 模因与多模态理解",
        },
        {
            "unique_name": "Structural and Discourse Modeling",
            "order": 9,
            "name": "Structural and Discourse Modeling",
            "predecessor_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） — 结构与语篇建模",
        },
        {
            "unique_name": "Event Extraction",
            "order": 10,
            "name": "Event Extraction",
            "predecessor_category": "Structural and Discourse Modeling",
            "enabled": True,
            "description": "[三级分类]（Structural and Discourse Modeling） —  事件抽取",
        },
        {
            "unique_name": "Topic Modeling",
            "order": 11,
            "name": "Topic Modeling",
            "predecessor_category": "Structural and Discourse Modeling",
            "enabled": True,
            "description": "[三级分类]（Structural and Discourse Modeling） —  主题建模",
        },
        {
            "unique_name": "Network Dynamics and Propagation Understanding",
            "order": 12,
            "name": "Network Dynamics and Propagation Understanding",
            "predecessor_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  网络动态与传播理解",
        },
        {
            "unique_name": "Social Popularity Prediction",
            "order": 13,
            "name": "Social Popularity Prediction",
            "predecessor_category": "Network Dynamics and Propagation Understanding",
            "enabled": True,
            "description": "[三级分类]（Network Dynamics and Propagation Understanding） —  社交流行度预测",
        },
        {
            "unique_name": "Information Diffusion Analysis",
            "order": 13,
            "name": "Information Diffusion Analysis",
            "predecessor_category": "Network Dynamics and Propagation Understanding",
            "enabled": True,
            "description": "[三级分类]（Network Dynamics and Propagation Understanding） —  信息扩散分析",
        },
        {
            "unique_name": "User-level Understanding",
            "order": 14,
            "name": "User-level Understanding",
            "predecessor_category": "Understanding",
            "enabled": True,
            "description": "[二级分类]（Understanding） —  用户级别理解任务",
        },
        {
            "unique_name": "User Profiling",
            "order": 15,
            "name": "User Profiling",
            "predecessor_category": "User-level Understanding",
            "enabled": True,
            "description": "[三级分类]（User-level Understanding） —  用户画像",
        },
        {
            "unique_name": "User Behavior Prediction",
            "order": 16,
            "name": "User Behavior Prediction",
            "predecessor_category": "User-level Understanding",
            "enabled": True,
            "description": "[三级分类]（User-level Understanding） - 用户行为预测（互动、参与、兴趣点关注）",
        },
        {
            "unique_name": "Social Psychological Phenomena Analysis",
            "order": 17,
            "name": "Social Psychological Phenomena Analysis",
            "predecessor_category": "User-level Understanding",
            "enabled": True,
            "description": "[三级分类]（User-level Understanding） —  社会心理现象分析",
        },
        {
            "unique_name": "Community Detection and Analysis",
            "order": 18,
            "name": "Community Detection and Analysis",
            "predecessor_category": "User-level Understanding",
            "enabled": True,
            "description": "[三级分类]（User-level Understanding） —  社区检测与分析",
        },

        {
            "unique_name": "Social Content Generation",
            "order": 21,
            "name": "Social Content Generation",
            "predecessor_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） — 社交内容生成",
        },
        {
            "unique_name": "Hashtag and Caption Generation",
            "order": 21,
            "name": "Hashtag and Caption Generation",
            "predecessor_category": "Social Content Generation",
            "enabled": True,
            "description": "[三级分类]（Social Content Generation） — 标签与标题生成",
        },
        {
            "unique_name": "Social Summarization",
            "order": 21,
            "name": "Social Summarization",
            "predecessor_category": "Social Content Generation",
            "enabled": True,
            "description": "[三级分类]（Social Content Generation） — 社交摘要生成",
        },
        {
            "unique_name": "Comment Generation",
            "order": 21,
            "name": "Comment Generation",
            "predecessor_category": "Social Content Generation",
            "enabled": True,
            "description": "[三级分类]（Social Content Generation） —  评论生成",
        },
        # {
        #     "unique_name": "Debate Generation",
        #     "order": 21,
        #     "name": "Debate Generation",
        #     "predecessor_category": "Social Content Generation",
        #     "enabled": True,
        #     "description": "[三级分类]（Social Content Generation） —  辩论生成",
        # },
        {
            "unique_name": "Dialogue and Conversational Systems",
            "order": 21,
            "name": "Dialogue and Conversational Systems",
            "predecessor_category": "Social Content Generation",
            "enabled": True,
            "description": "[三级分类]（Social Content Generation） — 对话与会话系统",
        },
        {
            "unique_name": "Humorous and Creative Content Generation",
            "order": 22,
            "name": "Humorous and Creative Content Generation",
            "predecessor_category": "Social Content Generation",
            "enabled": True,
            "description": "[三级分类]（Social Content Generation） — 幽默与创意内容生成",
        },
        {
            "unique_name": "Story Generation",
            "order": 22,
            "name": "Story Generation",
            "predecessor_category": "Humorous and Creative Content Generation",
            "enabled": True,
            "description": "[四级分类]（Humorous and Creative Content Generation） — 故事生成",
        },
        {
            "unique_name": "Humor Generation",
            "order": 22,
            "name": "Humor Generation",
            "predecessor_category": "Humorous and Creative Content Generation",
            "enabled": True,
            "description": "[四级分类]（Humorous and Creative Content Generation） —  幽默生成",
        },
        {
            "unique_name": "Social Impact and Intervention Generation",
            "order": 23,
            "name": "Social Impact and Intervention Generation",
            "predecessor_category": "Generation",
            "enabled": True,
            "description": "[二级分类]（Generation） —  社会影响与干预",
        },   
        {
            "unique_name": "Rumor Refutation Generation",
            "order": 24,
            "name": "Rumor Refutation Generation",
            "predecessor_category": "Social Impact and Intervention Generation",
            "enabled": True,
            "description": "[三级分类]（Social Impact and Intervention Generation） —  谣言反驳生成",
        },
        {
            "unique_name": "Misinformation Generation",
            "order": 25,
            "name": "Misinformation Generation",
            "predecessor_category": "Social Impact and Intervention Generation",
            "enabled": True,
            "description": "[三级分类]（Social Impact and Intervention Generation） —  虚假信息生成",
        },
        {
            "unique_name": "Counter-Hate Speech Generation",
            "order": 25,
            "name": "Counter-Hate Speech Generation",
            "predecessor_category": "Social Impact and Intervention Generation",
            "enabled": True,
            "description": "[三级分类]（Social Impact and Intervention Generation） —  反仇恨言论生成",
        },
        {
            "unique_name": "Text Detoxification and Moderation",
            "order": 25,
            "name": "Text Detoxification and Moderation",
            "predecessor_category": "Social Impact and Intervention Generation",
            "enabled": True,
            "description": "[三级分类]（Social Impact and Intervention Generation） —  文本净化与审查",
        },

        {
            "unique_name": "Social Simulation",
            "order": 28,
            "name": "Social Simulation",
            "predecessor_category": "Simulation and Deduction",
            "enabled": True,
            "description": "[二级分类]（Simulation and Deduction） —  社会仿真",
        },
        {
            "unique_name": "Micro Social Simulation",
            "order": 28,
            "name": "Micro Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度1-规模；微观社会仿真，关注个体行动决策、群体互动交互、整体信息传递与整体功能体现，如社区、网络结构",
        },
        {
            "unique_name": "Macro Social Simulation",
            "order": 28,
            "name": "Macro Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度1-规模；宏观社会仿真，社会级别，关注全局系统状态与整体涌现，如社会层面的全局特征、长期演化趋势、宏观规律",
        },
        {
            "unique_name": "Static Social Simulation",
            "order": 28,
            "name": "Static Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度2-时间动态；静态社会仿真，关注系统在特定时间点或时间段的状态、交互 和联系，而不研究或忽略系统随时间的演化过程",
        },
        {
            "unique_name": "Dynamic Social Simulation",
            "order": 28,
            "name": "Dynamic Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度2-时间动态；动态社会仿真，关注系统随时间演化的过程，如个体行为变化、群体互动模式/整体表现演变",

        },
        {
            "unique_name": "Mechanistic-model-based Social Simulation",
            "order": 28,
            "name": "Mechanistic-model-based Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度3-方法；describs collective behavior through explicit equations or procedural dynarmics such as discrete-event and system-dynamics",

        },
        {
            "unique_name": "Empirical-and-statistical-model-based Social Simulation",
            "order": 28,
            "name": "Empirical-and-statistical-model-based Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度3-方法；identifies diffusion regularities from data, including PSP and peak-based participattion dynamics",
        },
        {
            "unique_name": "Agent-based Social Simulation",
            "order": 28,
            "name": "Agent-based Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度3-方法；captures emergent phenomena from local interactions among heterogeneous agents(智能体)",
        },
        {
            "unique_name": "Other-based Social Simulation",
            "order": 28,
            "name": "Other-based Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度3-方法；基于其他方法的社会仿真，不属于以上三种方法的方法",
        },
        {
            "unique_name": "Individual-oriented Social Simulation",
            "order": 28,
            "name": "Individual-oriented Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度4-研究对象；以个体为研究对象的社会仿真，关注个体层面的属性、行为、决策、个体间的互动等",

        },
        {
            "unique_name": "Group-oriented Social Simulation",
            "order": 28,
            "name": "Group-oriented Social Simulation",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度4-研究对象；以群体为研究对象的社会仿真，关注群体层面特征和现象、群体间互动，包括研究由个体交互涌现出的整体特性的社会仿真",
        },        {
            "unique_name": "Social Simulation for Military",
            "order": 28,
            "name": "Social Simulation for Military",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；军事应用社会仿真：用于军事场景和需求的社会仿真",
        },
        {
            "unique_name": "Social Simulation for Economy",
            "order": 28,
            "name": "Social Simulation for Economy",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；经济学应用社会仿真：用于经济模拟和研究的社会仿真",
        },        {
            "unique_name": "Social Simulation for Education",
            "order": 28,
            "name": "Social Simulation for Education",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；教育应用社会仿真：用于教育场景和需求的社会仿真",
        },
        {
            "unique_name": "Social Simulation for Games",
            "order": 28,
            "name": "Social Simulation for Games",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；游戏应用社会仿真：用于游戏场景和需求的社会仿真",
        },        
        {
            "unique_name": "Social Simulation for Sociology",
            "order": 28,
            "name": "Social Simulation for Sociology",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；社会学应用社会仿真：用于社会学研究等需求的社会仿真",
        },
        {
            "unique_name": "Social Simulation for Social Media",
            "order": 28,
            "name": "Social Simulation for Social Media",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；社交媒体应用社会仿真：用于社交媒体模拟场景的社会仿真",
        },      
        {
            "unique_name": "Social Simulation for Other Fields",
            "order": 28,
            "name": "Social Simulation for Other Fields",
            "predecessor_category": "Social Simulation",
            "enabled": True,
            "description": "[三级分类]（Social Simulation） —  交叉分类-维度5-应用领域；不属于以上应用场景的用于下游应用的社会仿真",
        },


        {
            "unique_name": "Bias Analysis and Mitigation",
            "order":34,
            "name": "Bias Analysis and Mitigation",
            "predecessor_category": "Ethics and Safety",
            "enabled": True,
            "description": "[二级分类]（Ethics and Safety） — 偏见分析与缓解",
        },
        {
            "unique_name": "Data Privacy and Copyright",
            "order":34,
            "name": "Data Privacy and Copyright",
            "predecessor_category": "Ethics and Safety",
            "enabled": True,
            "description": "[二级分类]（Ethics and Safety） — 数据隐私与版权",

        },
        {
            "unique_name": "Value Alignment",
            "order":34,
            "name": "Value Alignment",
            "predecessor_category": "Ethics and Safety",
            "enabled": True,
            "description": "[二级分类]（Ethics and Safety） — 价值观对齐",
        },
        {
            "unique_name": "Robustness and Adversarial Attacks",
            "order":34,
            "name": "Robustness and Adversarial Attacks",
            "predecessor_category": "Ethics and Safety",
            "enabled": True,
            "description": "[二级分类]（Ethics and Safety） — 鲁棒性与对抗攻击",

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
    
    # 检查 predecessor_category 合法性：
    # - 根分类（predecessor_category 为 None）允许存在
    # - 非根分类（predecessor_category 非 None）必须引用存在的父分类（用 unique_name 表示）
    # - 不允许自指或循环引用，支持任意层级深度
    # 为便于查找，建立 unique_name -> category 映射
    categories_by_unique = {c.get('unique_name'): c for c in CATEGORIES_CONFIG['categories']}
    for category in CATEGORIES_CONFIG["categories"]:
        predecessor = category.get("predecessor_category", None)
        if predecessor is None:
            continue
        if not isinstance(predecessor, str):
            errors.append(f"分类 {category.get('unique_name')} 的 predecessor_category 应为父分类的 unique_name(str)，当前为 {predecessor!r}")
            continue
        if predecessor not in categories_by_unique:
            errors.append(f"分类 {category.get('unique_name')} 的 predecessor_category '{predecessor}' 不存在")
            continue
        if predecessor == category.get('unique_name'):
            errors.append(f"分类 {category.get('unique_name')} 的 predecessor_category 不能指向自己")

    for category in CATEGORIES_CONFIG["categories"]:
        chain_seen = set()
        current_name = category.get('unique_name')
        predecessor = category.get("predecessor_category")
        while predecessor is not None:
            if predecessor in chain_seen or predecessor == current_name:
                errors.append(f"分类 {current_name} 的 predecessor_category 存在循环引用")
                break
            chain_seen.add(predecessor)
            parent = categories_by_unique.get(predecessor)
            if not parent:
                break
            predecessor = parent.get("predecessor_category")

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