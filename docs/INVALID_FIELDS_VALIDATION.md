## invalid_fields 字段验证说明

### 概述
`invalid_fields` 是一个系统字段，用于记录论文中哪些字段存在验证问题。

- 语义：保存 **tag 的 variable 名称列表**（不是 order/id）
- 存储：
  - JSON：`string[]`（数组）
  - CSV：`|` 分隔字符串

### 验证规则
`invalid_fields` 字段的验证应包括以下规则：

1. **允许为空**：空字符串、None 或仅包含空格的字符串都是有效的
2. **分隔符**：字符串格式仅使用 `|` 作为分隔符
3. **每项必须是合法 variable**：满足 Python 变量命名规则（字母/数字/下划线，且不能以数字开头）
4. **每项必须存在于当前 tag 配置中**（即在 `config/tag_config.py` 的 `variable` 集合内）

示例：
- ✓ 有效：`"doi"`, `"doi|title|authors"`
- ✗ 无效：`"doi,title"`（旧格式）
- ✗ 无效：`"0|1"`（旧 order/id）
- ✗ 无效：`"bad-name"`（非法变量名）
- ✗ 无效：`"unknown_field"`（不在当前 tag 配置中）

### 实现细节

#### 验证函数
在 `src/utils.py` 中添加了 `validate_invalid_fields()` 函数：

```python
def validate_invalid_fields(invalid_fields: str, allowed_variables=None) -> Tuple[bool, str]:
    """
    验证 invalid_fields 字段
    返回: (是否有效, 错误信息)
    """
```

该函数会：
1. 处理空值（返回有效）
2. 按 `|` 分割字符串（或直接处理列表）
3. 过滤空字符串部分
4. 验证每个部分是否是合法 variable
5. 若提供 `allowed_variables`，校验每项都存在于允许集合

#### 集成到验证流程
在 `src/core/database_model.py` 的 `Paper.validate_paper_fields()` 方法中集成了验证：
- 当 `invalid_fields` 不为空时，调用验证函数
- 如果验证失败，将错误信息添加到验证错误列表中
- 同时将 `invalid_fields` 本身标记为无效字段

### 测试用例

所有测试用例都位于 `tests/test_invalid_fields_validation.py` 和 `tests/test_paper_invalid_fields_integration.py`

运行测试：
```bash
python tests/test_invalid_fields_validation.py          # 单元测试
python tests/test_paper_invalid_fields_integration.py   # 集成测试
```

### 使用场景

1. **导入数据时的验证**：当从 JSON 或 Excel 导入论文数据时，验证 `invalid_fields` 的格式
2. **数据库保存前验证**：防止无效的 `invalid_fields` 值被保存到数据库
3. **用户输入验证**：在 GUI 中编辑论文时，验证用户输入的 `invalid_fields`
4. **迁移旧数据**：使用 `scripts/migrate_array_fields_format.py` 将旧 order/id 形式迁移为 variable 形式

### 错误信息示例

当验证失败时，会显示具体的错误信息：
- `"invalid_fields 中含有非法字段名: 'bad-name'（应为合法 variable）"`
- `"invalid_fields 中字段不存在于当前 tag 配置: 'unknown_field'"`
