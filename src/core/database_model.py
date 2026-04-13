"""
数据库模型
定义论文数据模型
"""
from dataclasses import dataclass, field, asdict, fields
from typing import Dict, List, Optional, Union, Any, Tuple
from datetime import datetime
import sys
import os
import re


# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

# 导入工具函数
from src.utils import (
    validate_url, validate_doi, clean_doi, format_authors,
    validate_authors, validate_date, validate_invalid_fields
)

from src.core.config_loader import get_config_instance


@dataclass
class Paper:
    """论文数据模型"""

    # 唯一资源标识符 (New)
    uid: str = ""

    # 基础信息
    doi: str = ""
    title: str = ""
    citation_key: str = ""
    authors: str = ""
    date: str = ""
    category: str = ""

    # 总结信息
    summary_motivation: str = ""
    summary_innovation: str = ""
    summary_method: str = ""
    summary_conclusion: str = ""
    summary_limitation: str = ""
    summary_citable_paragraph: str = ""

    # 链接信息
    paper_url: str = ""
    project_url: str = ""

    # 其他信息
    conference: str = ""
    title_translation: str = ""
    analogy_summary: str = ""
    pipeline_image: str = ""
    paper_file: str = ""

    abstract: str = ""
    # Zotero 唯一定位引用，格式建议为 "libraryID:key"（例如 1:ABCD1234）
    zotero_item_ref: str = ""
    contributor: str = ""
    related_papers: str = ""
    notes: str = ""

    # 系统字段
    show_in_readme: bool = True
    status: str = ""  # "" "unread" "reading" "done" "adopted"
    submission_time: str = ""
    conflict_marker: bool = False
    # 验证相关字段：记录不规范字段的 variable 列表（| 分隔）
    invalid_fields: str = ""
    is_placeholder: bool = False  # 占位符标记，用于表示存在但填写不完整的论文条目

    def __post_init__(self):
        """初始化后处理"""
        # 获取配置实例
        from src.core.config_loader import get_config_instance
        config = get_config_instance()
        conflict_marker = config.settings['database'].get('conflict_marker', '[💥冲突]')

        # 规范化字段
        self.doi = clean_doi(self.doi, conflict_marker) if self.doi else ""
        self.authors = format_authors(self.authors) if self.authors else ""

        # 规范化 Date (Publish Date)
        if self.date:
            _, normalized_date = validate_date(self.date)
            self.date = normalized_date

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Paper':
        """从字典创建Paper对象"""
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    def get_key(self) -> tuple[str, str]:
        """
        获取论文的唯一键，用于论文唯一标识和匹配
        注意返回格式: tuple : doi,title,均保持小写，注意不要写回
        """
        # 收集已处理论文的 Key (全小写，与读取时保持一致)
        _p_doi = str(self.doi).strip() if self.doi else ""
        _, normalized_doi = validate_doi(str(_p_doi), check_format=False)
        p_doi = normalized_doi.lower()

        p_title = str(self.title).strip().lower() if self.title else ""
        return p_doi, p_title

    # 统一的论文字段验证函数，流程：统一规范化->验证
    def validate_paper_fields(
        self,
        config_instance,
        check_required: bool = True,
        check_non_empty: bool = True,
        variable: Optional[str] = None,
        no_normalize: bool = False
    ) -> Tuple[bool, List[str], List[str]]:
        """
        统一的论文字段验证函数
        流程：统一规范化->验证

        参数:
            config_instance: 配置实例
            check_required: 是否检查必填字段
            check_non_empty: 是否检查非空字段（包括类型验证和validation字段验证）
            variable: 指定只验证该字段（变量名）。若为None，则验证所有字段。
            no_normalize: 若为True，则仅进行验证，不更新对象的属性值（不规范化）。

        返回:
            (是否有效, 错误信息列表, 验证未通过的字段变量名列表)
        """
        errors = []
        invalid_vars = set()

        # 获取配置
        conflict_marker = config_instance.settings['database'].get('conflict_marker')
        required_tags = config_instance.get_required_tags() if check_required else []
        active_tags = config_instance.get_active_tags()
        project_root = config_instance.project_root

        # 0. 辅助函数：判断是否需要验证当前字段
        def should_check(var_name):
            if variable is not None and variable != var_name:
                return False
            return True

        # 规范化 category 字段：支持多分类（用 ; 或 中文； 分隔），去重并限制最大数量
        # 注意：如果 no_normalize=True，我们不应该修改 self.category。
        # 但验证逻辑可能依赖规范化后的形式（例如查重），这里为了验证逻辑统一，
        # 若 no_normalize=True，使用临时变量进行检查。
        temp_category = getattr(self, 'category', "")

        if should_check('category'):
            try:
                from src.core.update_file_utils import get_update_file_utils
                ufu = get_update_file_utils()
                normalized_cat = ufu.normalize_category_value(str(temp_category), config_instance)
                if not no_normalize:
                    self.category = normalized_cat
                else:
                    temp_category = normalized_cat
            except Exception:
                pass

        # === 资源字段统一验证 + 规范化 (Assets) ===
        target_asset_fields = [
            f for f in ['pipeline_image', 'paper_file']
            if should_check(f)
        ]
        if target_asset_fields:
            from src.core.update_file_utils import get_update_file_utils
            ufu = get_update_file_utils()

            asset_valid, asset_errors = ufu.validate_and_normalize_asset_fields(
                self,
                target_asset_fields,
                normalize=(not no_normalize),
                strict=True,
            )
            if not asset_valid:
                errors.extend(asset_errors)
                for msg in asset_errors:
                    for asset_field in target_asset_fields:
                        if msg.startswith(f"{asset_field} "):
                            invalid_vars.add(asset_field)

        # 1. 特殊字段验证

        # 验证 invalid_fields 字段格式
        if should_check('invalid_fields'):
            if self.invalid_fields:
                allowed_vars = {
                    str(tag.get('variable')).strip()
                    for tag in active_tags
                    if tag.get('variable')
                }
                invalid_fields_valid, invalid_fields_error = validate_invalid_fields(
                    self.invalid_fields,
                    allowed_variables=allowed_vars,
                )
                if not invalid_fields_valid:
                    errors.append(f"invalid_fields 字段格式无效: {invalid_fields_error}")
                    invalid_vars.add('invalid_fields')

        # DOI验证
        if should_check('doi'):
            if self.doi:
                doi_valid, cleaned_doi = validate_doi(self.doi, check_format=True, conflict_marker=conflict_marker)
                if not doi_valid and check_non_empty:
                    errors.append(f"DOI格式无效: {self.doi}")
                    invalid_vars.add('doi')
                # 即使 check_format 失败，validate_doi 也会返回尝试 clean 后的值
                # 只有当 no_normalize=False 时才写回
                if not no_normalize:
                    self.doi = cleaned_doi

        # 作者验证
        if should_check('authors'):
            if self.authors:
                authors_valid, formatted_authors = validate_authors(self.authors)
                if not authors_valid and check_non_empty:
                    errors.append("作者格式无效")
                    invalid_vars.add('authors')
                elif not no_normalize:
                    self.authors = formatted_authors

        # 日期验证
        if should_check('date'):
            if self.date:
                date_valid, formatted_date = validate_date(self.date)
                if not date_valid and check_non_empty:
                    errors.append(f"日期格式无效: {self.date} (应为 YYYY-MM-DD)")
                    invalid_vars.add('date')
                elif not no_normalize:
                    self.date = formatted_date

        # URL 验证
        for url_field in ['paper_url', 'project_url']:
            if should_check(url_field):
                val = getattr(self, url_field, "")
                if val and not validate_url(val) and check_non_empty:
                    errors.append(f"{url_field} 格式无效")
                    invalid_vars.add(url_field)

        # === 必填与非空检查 ===
        current_cat_val = temp_category if no_normalize else self.category

        # 2. 必填字段检查
        if check_required:
            for tag in required_tags:
                var_name = tag.get('variable')
                if not var_name:
                    continue
                if not should_check(var_name):
                    continue

                display_name = tag.get('display_name', var_name)
                # 使用 self 中的值 (注意 category 可能在 temp_category 中)
                value = current_cat_val if var_name == 'category' else getattr(self, var_name, "")

                # 在验证前忽略 conflict_marker
                try:
                    if isinstance(value, str) and conflict_marker:
                        value = value.replace(conflict_marker, '').strip()
                except Exception:
                    pass

                if not value or str(value).strip() == "":
                    errors.append(f"必填字段为空: {display_name} ({var_name})")
                    invalid_vars.add(var_name)

        # 3. 非空字段检查（类型验证和validation字段验证）
        if check_non_empty:
            for tag in active_tags:
                var_name = tag.get('variable')
                if not var_name:
                    continue
                if not should_check(var_name):
                    continue

                display_name = tag.get('display_name', var_name)
                tag_type = tag.get('type', 'string')
                validation_pattern = tag.get('validation')

                value = current_cat_val if var_name == 'category' else getattr(self, var_name, "")

                # 跳过空值（除非是必填字段，已经在上面检查过了）
                try:
                    if isinstance(value, str) and conflict_marker:
                        value = value.replace(conflict_marker, '').strip()
                except Exception:
                    pass

                if not value or str(value).strip() == "":
                    continue

                # 类型验证
                if tag_type == 'bool':
                    if str(value).lower() not in ['true', 'false', 'yes', 'no', '1', '0', 'y', 'n']:
                        errors.append(f"字段类型不匹配: {display_name} 应为布尔值")
                        invalid_vars.add(var_name)
                elif (str(tag_type).startswith('enum')) and var_name == 'category':
                    # 支持多分类，按 '|' 分割
                    val_str = str(value)
                    try:
                        parts = [p.strip() for p in val_str.split('|') if p.strip()]
                    except Exception:
                        parts = [val_str.strip()]

                    valid_categories = {cat['unique_name'] for cat in config_instance.get_active_categories()}

                    # 检查重复（原始输入是否包含重复项）
                    if len(parts) != len(list(dict.fromkeys(parts))):
                        errors.append(f"分类包含重复项: {value}")
                        invalid_vars.add(var_name)

                    # 检查每一项是否合法
                    for p in parts:
                        if p not in valid_categories:
                            errors.append(f"分类无效: {p}，分类须为categories_config.py中已启用的分类")
                            invalid_vars.add(var_name)

                    # 检查数量不超过配置限制
                    try:
                        max_allowed = int(config_instance.settings['database'].get('max_categories_per_paper', 4))
                    except Exception:
                        max_allowed = 4
                    if len(parts) > max_allowed:
                        errors.append(f"分类数量超过限制: 最多允许 {max_allowed} 个分类")
                        invalid_vars.add(var_name)
                elif tag_type == 'int':
                    try:
                        int(value)
                    except ValueError:
                        errors.append(f"字段类型不匹配: {display_name} 应为整数")
                        invalid_vars.add(var_name)
                elif tag_type == 'float':
                    try:
                        float(value)
                    except ValueError:
                        errors.append(f"字段类型不匹配: {display_name} 应为浮点数")
                        invalid_vars.add(var_name)

                # validation字段验证（正则表达式）
                if validation_pattern:
                    try:
                        if not re.match(validation_pattern, str(value)):
                            errors.append(f"字段格式无效: {display_name} 不符合验证规则")
                            invalid_vars.add(var_name)
                    except re.error:
                        # 如果正则表达式有问题，跳过验证
                        pass

        # 处理 invalid_fields 字段更新
        # 仅当 no_normalize=False (即允许更新对象状态) 时，才更新 self.invalid_fields
        if not no_normalize:
            # 准备映射：按配置顺序的变量列表
            ordered_vars = []
            for tag in active_tags:
                var = tag.get('variable')
                if var:
                    ordered_vars.append(str(var).strip())
            valid_var_set = set(ordered_vars)

            # 解析当前的 invalid_fields（仅保留已知 variable）
            current_invalid_vars = set()
            if self.invalid_fields:
                parts = [p.strip() for p in str(self.invalid_fields).split('|') if p.strip()]
                for p in parts:
                    if p in valid_var_set:
                        current_invalid_vars.add(p)

            if variable is None:
                # 全量验证模式：重置 invalid_fields 为当前 invalid_vars 对应的 variable
                vars_out = [v for v in ordered_vars if v in invalid_vars]
                self.invalid_fields = '|'.join(vars_out)
            else:
                # 单字段验证模式：更新当前字段的状态
                target_var = str(variable).strip() if variable else ''
                if target_var and target_var in valid_var_set:
                    if variable in invalid_vars:
                        # 验证失败，添加 variable
                        current_invalid_vars.add(target_var)
                    else:
                        # 验证通过，移除 variable
                        if target_var in current_invalid_vars:
                            current_invalid_vars.remove(target_var)

                    # 重新生成字符串，保持与配置顺序一致
                    sorted_vars = [v for v in ordered_vars if v in current_invalid_vars]
                    self.invalid_fields = '|'.join(sorted_vars)

        return (len(errors) == 0, errors, list(invalid_vars))

    # 检查时，注意看看和这个函数有没有必要存在
    def is_valid(self, config_instance=None) -> List[str]:
        """
        兼容性方法，validate_paper_fields套壳，调用新的验证函数
        """
        if not config_instance:
            from src.core.config_loader import get_config_instance
            config_instance = get_config_instance()

        valid, errors, _ = self.validate_paper_fields(
            config_instance,
            check_required=True,
            check_non_empty=True,
            no_normalize=False  # 默认保持原行为，更新对象
        )
        return errors


# Paper对象间级方法
def is_same_identity(a: Union[Paper, Dict[str, Any]], b: Union[Paper, Dict[str, Any]]) -> bool:
    """
    判断 a 与b 是否表示同一篇论文（基于 DOI 和 title）
    """

    def extract_key(obj) -> Tuple[str, str]:
        if isinstance(obj, Paper):
            return obj.get_key()
        else:
            # 如果是字典，模拟 Paper.get_key 的逻辑
            raw_doi = obj.get('doi', "")
            raw_title = obj.get('title', "")

            # 使用 utils 中的函数进行与 Paper.get_key 一致的处理
            _, n_doi = validate_doi(str(raw_doi).strip(), check_format=False)
            n_title = str(raw_title).strip().lower()
            return n_doi.lower(), n_title

    key_a_doi, key_a_title = extract_key(a)
    key_b_doi, key_b_title = extract_key(b)

    if key_a_title and key_b_title and key_a_title == key_b_title:
        return True
    if key_a_doi and key_b_doi and key_a_doi == key_b_doi:
        return True

    return False


def _papers_fields_equal(new: Union[Paper, Dict[str, Any]], exist: Union[Paper, Dict[str, Any]],
                         complete_compare=False, ignore_fields: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    精确比较两个论文条目的字段（用于判定是否"完全相同"）。
    参数：
        new：新提交论文
        exist：用于比较的已存在论文
        complete_compare：bool，是否进行严格的所有字段比较
        ignore_fields：List，需要忽略的字段，默认值：系统字段
    complete_compare=False：除忽略ignore_fields外，需要特殊处理空字段：
        如果new的非空域集合是exist的子集，则只判断new中所有非空字段是否相同，相同返回True
        如果new的非空域集合非exist的子集（前者包含后者或无包含关系），则直接返回False
    complete_compare=True：除忽略ignore_fields外，比较全部字段

    比较 DOI 时会忽略 conflict_marker。
    """
    if ignore_fields is None:
        system_tags = get_config_instance().get_system_tags()
        ignore_fields = [
            t["variable"]
            for t in system_tags
            if isinstance(t.get("variable"), str) and t.get("variable")
        ]
    else:
        ignore_fields = list(ignore_fields)

    if isinstance(new, Paper):
        a_dict = new.to_dict()
    else:
        a_dict = dict(new)

    if isinstance(exist, Paper):
        b_dict = exist.to_dict()
    else:
        b_dict = dict(exist)

    # 规范化 DOI 比较：移除 conflict_marker 并清理
    _, a_doi = validate_doi(a_dict.get('doi', ""), check_format=False)
    _, b_doi = validate_doi(b_dict.get('doi', ""), check_format=False)

    a_dict['doi'] = a_doi
    b_dict['doi'] = b_doi

    def is_non_empty(value):
        """判断字段值是否为非空"""
        if value is None:
            return False
        if isinstance(value, (str, list, dict, set)):
            return bool(value)
        if isinstance(value, (int, float)):
            # 数字类型总是视为有值
            return True
        # 其他类型转为字符串判断
        return str(value).strip() != ""

    def get_non_empty_keys(dict_obj, ignore_keys):
        """获取字典中非空的键（排除忽略字段）"""
        return {
            k: dict_obj[k]
            for k in dict_obj
            if k not in ignore_keys and is_non_empty(dict_obj[k])
        }

    if not complete_compare:
        # 获取非空字段集合
        a_non_empty = get_non_empty_keys(a_dict, ignore_fields)
        b_non_empty = get_non_empty_keys(b_dict, ignore_fields)

        # 检查new的非空字段是否是exist的非空字段的子集
        a_keys_set = set(a_non_empty.keys())
        b_keys_set = set(b_non_empty.keys())

        if not a_keys_set.issubset(b_keys_set):
            # new的非空域集合不是exist的子集，直接返回False
            return False, '新论文集合更大'

        # 比较new中的所有非空字段
        for k in a_non_empty:
            if k in ignore_fields:
                continue

            va = a_non_empty[k]
            vb = b_dict.get(k, "")

            # 统一转换为字符串比较（保持 bool/int 的语义）
            if isinstance(va, bool) or isinstance(vb, bool):
                if bool(va) != bool(vb):
                    return False, k

            else:
                if str(va).strip() != str(vb).strip():
                    return False, k
        return True, ''

    else:
        # complete_compare=True：除忽略ignore_fields外，比较全部字段
        # 获取所有需要比较的键（排除忽略字段）
        all_keys = set(a_dict.keys()) | set(b_dict.keys())

        for k in all_keys:
            if k in ignore_fields:
                continue

            va = a_dict.get(k, "")
            vb = b_dict.get(k, "")

            # 统一转换为字符串比较（保持 bool/int 的语义）
            if isinstance(va, bool) or isinstance(vb, bool):
                if bool(va) != bool(vb):
                    return False, k
            else:
                if str(va).strip() != str(vb).strip():
                    return False, k
        return True, ''


def is_duplicate_paper(existing_papers: List[Paper], new_paper: Paper, ignore_fields: Optional[List[str]] = None, complete_compare=False) -> Tuple[bool, str]:
    """
    判断新提交是否为重复论文条目：
    - 在 existing_papers 中找出与 new_paper 表示相同论文（一致 identity）的条目集合；
    - 如果该集合中存在任一条目的所有字段都与 new_paper 完全一致（除忽略字段），则为重复paper，返回 True。
    """
    same_identity_entries = [p for p in existing_papers if is_same_identity(p, new_paper)]
    if not same_identity_entries:
        return False, ''
    first_conflict_field = ''
    for ex in same_identity_entries:
        # _papers_fields_equal 的签名为 (new, exist, ...)
        # 这里应将新提交的论文放在第一个参数，已有条目放在第二个参数
        equal, first_conflict_field = _papers_fields_equal(new_paper, ex, ignore_fields=ignore_fields, complete_compare=complete_compare)
        if equal:
            return True, ''
    return False, first_conflict_field
