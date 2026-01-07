"""
标签配置文件

重要说明：
1. variable字段是标签的唯一标识符，一旦设置不可更改
2. order字段决定标签在Excel中的列位置，必须唯一且不可更改
3. immutable=true的标签是不可更改的，即使enabled=false也会被强制启用，他们往往有独特的处理方式
4. 修改此文件后需要重启系统才能生效
5. show_in_readme=false的标签不会出现在README的论文表格中
6. required=True的标签是提交论文时必须填写的
"""

TAGS_CONFIG = {
    "config_version": "1.0",
    "last_updated": "2025-01-01",
    
    # 标签列表，按order排序
    "tags": [
        # ==================== 不可禁用标签 (immutable=true) ====================
        {
            "variable": "doi",
            "order": 0,                     # 不可更改，必须是0
            "table_name": "doi",            # 在Excel中的列名，可更改
            "display_name": "DOI",          # 在README中显示的列名，可更改
            "description": "论文的唯一DOI标识符，系统会自动清理格式",
            "type": "string",
            "validation":None,           # r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$",  # DOI正则表达式
            "show_in_readme": True,         # 是否在README中显示
            "enabled": True,                # 对于immutable标签，此设置被忽略
            "immutable": True,              # 不可禁用，必填项
            "required": True,               # 必须填写
            "system_var": False,            #控制字段，为真时只在数据库中显示               
        },
        #以下3个标签在readme列表中共用一列，使用"title&authors&date"作为列名，使用"[display_name]"分割5个字段
        {
            "variable": "title",            # 不可更改
            "order": 1,                     # 不可更改，必须是1
            "table_name": "title",
            "display_name": "标题",         #3个标签在readme列表中共用一列，使用[display_name]分割3个字段
            "description": "论文的完整标题",
            "type": "string",
            "validation": None,             # 无特殊验证规则
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": True,               # 必须填写
            "system_var": False,            #控制字段，为真时只在数据库中显示               
        },
        {
            "variable": "authors",          # 不可更改
            "order": 2,                     # 不可更改，必须是2
            "table_name": "authors",
            "display_name": "authors",         #3个标签在readme列表中共用一列，使用[display_name]分割3个字段
            "description": "作者列表，多个作者用逗号分隔",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": True,               # 必须填写
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "date",          # 不可更改
            "order": 3,                     # 不可更改，必须是3
            "table_name": "publish date",
            "display_name": "publish date",         #3个标签在readme列表中共用一列，使用[display_name]分割3个字段
            "description": "论文发布时间",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": True,               # 必须填写
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "category",         # 不可更改
            "order": 4,                     # 不可更改，必须是4
            "table_name": "category",
            "display_name": "category",
            "description": "论文的分类",
            "type": "enum",                 #具体取值在categories_config.py中
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": True,               # 必须填写
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        #以下5个标签在readme列表中共用一列，它们5个是写综述时直接引用的一句话总结。使用"summary"作为列名，使用"[display_name]"分割5个字段
        {
            "variable": "summary_motivation",
            "order": 5,
            "table_name": "summary motivation",
            "display_name": "motivation",          #5个标签在readme列表中共用一列，使用[display_name]分割5个字段
            "description": "论文的研究目标或动机",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": False,              
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "summary_innovation",
            "order": 6,
            "table_name": "summary innovation",
            "display_name": "innovation",             #5个标签在readme列表中共用一列，使用[display_name]分割5个字段
            "description": "论文的主要创新点",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": False,              
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "summary_method",
            "order": 7, 
            "table_name": "summary method",
            "display_name": "method",           #5个标签在readme列表中共用一列，使用[display_name]分割5个字段
            "description": "核心方法总结",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": False,              
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "summary_conclusion",
            "order": 8,
            "table_name": "summary conclusion",
            "display_name": "conclusion/contribution",      #5个标签在readme列表中共用一列，使用[display_name]分割5个字段
            "description": "论文的主要结论/贡献",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": False,            
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "summary_limitation",
            "order": 9,
            "table_name": "summary limitation",
            "display_name": "limitation/future",      #5个标签在readme列表中共用一列，使用[display_name]分割5个字段
            "description": "论文的局限性或未来工作",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": False,              
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        #以下2个标签在readme列表中共用一列，使用"links"作为列名，使用"[display_name]"分割2个字段
        {
            "variable": "paper_url",        
            "order": 10,
            "table_name": "paper url",
            "display_name": "paper link",     #2个标签在readme列表中共用一列，使用[display_name]分割2个字段
            "description": "论文的arXiv或其他网址链接",
            "type": "string",
            "validation": r"^https?://",    # 必须是以http://或https://开头
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,
            "required": True,               # 必须填写
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "project_url",
            "order": 11,
            "table_name": "project url",
            "display_name": "project url",      #2个标签在readme列表中共用一列，使用[display_name]分割2个字段
            "description": "项目链接",
            "type": "string",
            "validation": r"^https?://",    # 必须是以http://或https://开头
            "show_in_readme": True,
            "enabled": True,
            "immutable": True,             
            "required": False,              
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "conference",
            "order": 12,
            "table_name": "conference",
            "display_name": "conference",
            "description": "发表的会议或期刊名称",
            "type": "string",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": True,
            "required": False,           
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
    # ==================== 可禁用标签 (immutable=false) ====================
        {
            "variable": "title_translation",
            "order": 13,
            "table_name": "title translation",
            "display_name": "标题翻译",
            "description": "可以忽略，中文标题翻译",
            "type": "string",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": False,
            "required": False,         
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "analogy_summary",
            "order": 14,
            "table_name": "analogy summary",
            "display_name": "类比总结",
            "description": "一句话类比总结",
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": False,
            "required": False,            
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
         #直接在readme的论文列表中根据路径显示图片
        {
            "variable": "pipeline_image",
            "order": 15,
            "table_name": "pipeline figure",
            "display_name": "Pipeline图",
            "description": "请将Pipeline图片放到figures文件夹下，在此填写图片全名或相对路径",  #直接在readme的论文列表中根据路径显示图片
            "type": "string",
            "validation": None,
            "show_in_readme": True,
            "enabled": True,
            "immutable": False,
            "required": False,       
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "abstract",
            "order": 16,
            "table_name": "abstract",
            "display_name": "摘要",
            "description": "将论文摘要粘贴至此",
            "type": "text",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": True,
            "required": True,         
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "contributor",
            "order": 17,
            "table_name": "contributor",
            "display_name": "提供者",
            "description": "提交论文的组员标识符",
            "type": "string",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": False,
            "required": False,             
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "notes",
            "order": 18,
            "table_name": "notes",
            "display_name": "notes",
            "description": "其他备注信息",
            "type": "text",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": False,
            "required": False,              
            "system_var": False,            #控制字段，为真时只在数据库中显示               

        },
        # ==================== 数据库内部控制标签，不供提交时手动填写 ====================
        {
            "variable": "show_in_readme",
            "order": 19,
            "table_name": "show in readme",
            "display_name": "显示控制",
            "description": "控制论文是否在README中显示",
            "type": "bool",
            "validation": None,
            "show_in_readme": False,      # 这个标签本身不在README中显示
            "enabled": True,
            "immutable": True,
            "required": False,             
            "system_var": True,            #控制字段，为真时只在数据库中显示               

        },
        {
            "variable": "status",
            "order": 20,
            "table_name": "status",
            "display_name": "阅读状态",
            "description": "论文的阅读状态", #unread，reading、done、adopted
            "type": "enum",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": False,
            "required": False,              
            "system_var": True,            #控制字段，为真时只在数据库中显示               

        },

        {
            "variable": "submission_time",
            "order": 21,
            "table_name": "submission time",
            "display_name": "submission time",
            "description": "论文提交时间",
            "type": "string",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": False,
            "required": False,     
            "system_var": True,            #控制字段，为真时只在数据库中显示           
        },
        {
            "variable": "conflict_marker",
            "order": 21,
            "table_name": "conflict marker",
            "display_name": "conflict marker",
            "description": "冲突标记",
            "type": "bool",
            "validation": None,
            "show_in_readme": False,
            "enabled": True,
            "immutable": True,
            "required": False,     
            "system_var": True,            #控制字段，为真时只在数据库中显示           
        },
    ]
}

required_variables = ['doi', 'title', 'authors', 'category', 'paper_url', 'abstract', 'date']
# 验证函数
def validate_tags_config():
    """
    验证标签配置的有效性
    
    返回: (是否有效, 错误信息列表)
    """
    errors = []
    
    # 检查必填标签
    for req_var in required_variables:
        found = False
        for tag in TAGS_CONFIG["tags"]:
            if tag["variable"] == req_var:
                found = True
                if not tag.get("required", False):
                    errors.append(f"必填标签 {req_var} 必须设置 required=true")
                if not tag.get("immutable", False):
                    errors.append(f"必填标签 {req_var} 必须设置 immutable=true")
                break
        
        if not found:
            errors.append(f"缺少必填标签: {req_var}")
    
    # 检查order唯一性
    orders = {}
    for tag in TAGS_CONFIG["tags"]:
        order = tag.get("order")
        if order is None:
            errors.append(f"标签 {tag.get('variable')} 缺少order字段")
            continue
            
        if order in orders:
            errors.append(f"order {order} 重复: {orders[order]} 和 {tag['variable']}")
        else:
            orders[order] = tag["variable"]
    
    # 检查order连续性
    max_order = max(orders.keys()) if orders else -1
    for i in range(max_order + 1):
        if i not in orders:
            errors.append(f"order {i} 缺失")
    
    # 检查variable唯一性
    variables = {}
    for tag in TAGS_CONFIG["tags"]:
        var = tag.get("variable")
        if var is None:
            errors.append(f"标签缺少variable字段: {tag}")
            continue
            
        if var in variables:
            errors.append(f"variable {var} 重复")
        else:
            variables[var] = True
    
    # 检查immutable标签的enabled设置
    for tag in TAGS_CONFIG["tags"]:
        if tag.get("immutable", False) and not tag.get("enabled", True):
            errors.append(f"不可变标签 {tag['variable']} 不能设置 enabled=false")
    
    # 检查required字段一致性
    required_count = 0
    for tag in TAGS_CONFIG["tags"]:
        if tag.get("required", False):
            required_count += 1
            if not tag.get("immutable", False):
                errors.append(f"required=true的标签 {tag['variable']} 必须设置 immutable=true")
    
    if required_count != len(required_variables):
        errors.append(f"应该只有{len(required_variables)}个required=true的标签，当前有{required_count}个，请检查")
    
    return len(errors) == 0, errors

# 配置验证
if __name__ == "__main__":
    is_valid, error_list = validate_tags_config()
    if is_valid:
        print("✅ 标签配置验证通过")
        print(f"   - 共配置 {len(TAGS_CONFIG['tags'])} 个标签")
        print(f"   - 必填标签:{required_variables}")
        print(f"   - order范围: 0-{len(TAGS_CONFIG['tags'])-1}")
    else:
        print("❌ 标签配置验证失败:")
        for error in error_list:
            print(f"   - {error}")
        exit(1)