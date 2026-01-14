"""
配置文件加载器
"""
import os
import re
import configparser
from typing import Dict, List, Any, Optional
import sys
import json
from pathlib import Path


# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

# 导入配置文件
from config import tag_config, categories_config


class ConfigLoader:
    """配置加载器，读取所有配置文件"""
    INLINE_COMMENT_PREFIXES = ('//', ';', '#')  # 配置文件注释前缀，为健壮性，除#外，也支持 //和; 作为行注释前缀
    def __init__(self):
        # 以模块位置上溯两级作为项目根（保证以项目根为基准解析所有相对路径）
        self.project_root = Path(__file__).resolve().parents[2]
        # config 目录在项目根下的 config 子目录
        self.config_path = (self.project_root / 'config').resolve()

        # 读取配置（_load_settings 会使用 self.project_root 来解析相对路径）
        self.settings = self._load_settings()
        self.tags_config = self._load_tags_config()
        self.categories_config = self._load_categories_config()

        # 便于其他模块直接使用绝对路径
        self.paths = self.settings.get('paths', {})
    
    def _load_settings(self) -> Dict[str, Any]:
        """加载config.ini文件"""
        # 为健壮性，除#外，也支持 //和; 作为注释
        # ConfigParser函数支持=和;作为键值对分隔符，因此配置文件中使用:也可，出于习惯，推荐=
        config = configparser.ConfigParser(inline_comment_prefixes=self.INLINE_COMMENT_PREFIXES)
        settings_path = (self.config_path / 'config.ini').resolve()

        if not settings_path.exists():
            return self._create_default_settings()

        config.read(str(settings_path), encoding='utf-8')
        settings: Dict[str, Any] = {}
        for section in config.sections():
            settings[section] = dict(config.items(section))

        # 处理 paths：统一使用 self.project_root 作为相对路径基准，并规范化为绝对路径字符串
        if 'paths' in settings:
            paths = settings['paths'] or {}
            normalized: Dict[str, Any] = {}
            # 保证有默认项
            paths.setdefault('update_json', 'submit_template.json')
            
            # 特殊处理 extra_update_file 列表
            extra_files_list = []
            
            for k, v in paths.items():
                if not v:
                    normalized[k] = None
                    continue
                
                # 处理 extra_update_file (逗号分割的列表)
                if k == 'extra_update_file':
                    raw_paths = [p.strip() for p in v.split(',') if p.strip()]
                    for raw_p in raw_paths:
                        p_obj = Path(raw_p)
                        try:
                            if not p_obj.is_absolute():
                                abs_path = str((self.project_root / p_obj).resolve())
                            else:
                                abs_path = str(p_obj.resolve())
                            extra_files_list.append(abs_path)
                        except Exception:
                            extra_files_list.append(str(raw_p))
                    # 保存原始字符串
                    normalized[k] = v
                    continue

                # 处理普通路径
                p = Path(v)
                try:
                    if not p.is_absolute():
                        normalized[k] = str((self.project_root / p).resolve())
                    else:
                        normalized[k] = str(p.resolve())
                except Exception:
                    # 回退到原始字符串（避免抛出）
                    normalized[k] = str(p)
            
            settings['paths'] = normalized
            # 将解析后的额外文件列表单独存入
            settings['paths']['extra_update_files_list'] = extra_files_list

        return settings

    def _create_default_settings(self) -> Dict[str, Any]:
        """创建默认设置"""
        # 以 project_root 为基准生成默认路径
        root_dir = getattr(self, 'project_root', Path(__file__).resolve().parents[2])
        default_settings = {
            'paths': {
                'core_excel': str((root_dir / 'master' / 'paper_database.xlsx').resolve()),
                'update_excel': str((root_dir / 'submit_template.xlsx').resolve()),
                'update_json': str((root_dir / 'submit_template.json').resolve()),
                'my_update_excel': str((root_dir / 'my_submit.xlsx').resolve()),
                'my_update_json': str((root_dir / 'my_submit.json').resolve()),
                'extra_update_file': '', # 默认为空
                'backup_dir': str((root_dir / 'master' / 'backups').resolve()),
            },
            'ai': {
                'enable_ai_generation': 'true',
                'deepseek_api_key_path': 'key.txt',
                'api_key_github_secret_name': 'DEEPSEEK_API',
                'ai_generate_mark':'[AI generated]'
            },
            # Excel / 表格样式配置（可通过 config.ini 动态修改）
            # 颜色均使用不带#的16进制 RGB 值
            'excel': {
                'header_fill_color': 'BDD7EE',          # 表头默认浅蓝
                'required_header_color': '366092',      # 必填字段表头深蓝
                'required_column_fill': 'DDEBF7',       # 必填列单元格浅蓝
                'conflict_fill_color': 'FFCCCC',        # 冲突行红色（优先级高）
                'header_font_color': 'FFFFFF',          # 表头字体颜色
                'password_path': 'key.txt',
                'excel_key_github_secret_name': 'EXCEL_KEY',
            },
            'database': {
                'default_contributor': 'anonymous',
                'conflict_marker': '[冲突]',
                'translation_separator':'[翻译]',
                'value_deprecation_mark':'[Deprecated]'
            },
            'readme': {
                'truncate_translation':'true',
                'max_title_length': '100',
                'max_authors_length': '150',
                'date_format': 'YYYY-MM-DD',
                'enable_markdown':'false'
            }
        }
        
        # 保存默认设置
        self._save_default_settings(default_settings)
        return default_settings
    
    def _save_default_settings(self, settings: Dict[str, Any]):
        """保存默认设置到文件"""
        config = configparser.ConfigParser()
        
        for section, section_data in settings.items():
            config[section] = section_data
        
        settings_path = os.path.join(self.config_path, 'config.ini')
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        with open(settings_path, 'w', encoding='utf-8') as f:
            config.write(f)
        
        print(f"已创建默认配置文件: {settings_path}")
    
    def _load_tags_config(self) -> Dict[str, Any]:
        """加载标签配置"""
        # 直接从tag_config模块导入配置
        return tag_config.TAGS_CONFIG
    
    def _load_categories_config(self) -> Dict[str, Any]:
        """加载分类配置"""
        # 直接从categories_config模块导入配置
        return categories_config.CATEGORIES_CONFIG
    
    def get_active_tags(self) -> List[Dict[str, Any]]:
        """获取所有启用的标签（包括immutable标签）"""
        active_tags = []
        for tag in self.tags_config.get('tags', []):
            if tag.get('immutable', False) or tag.get('enabled', False):
                active_tags.append(tag)
        return active_tags
    
    def get_active_categories(self) -> List[Dict[str, Any]]:
        """获取所有启用的分类"""
        active_categories = []
        for category in self.categories_config.get('categories', []):
            if category.get('enabled', True):
                active_categories.append(category)
        return active_categories
    
    def get_tag_by_variable(self, variable: str) -> Optional[Dict[str, Any]]:
        """根据变量名获取标签配置"""
        for tag in self.tags_config.get('tags', []):
            if tag.get('variable') == variable:
                return tag
        return None
    def get_tag_field(self, variable: str,field_name:str) -> str:
        """根据变量名和tag域名获取具体tag的具体字段值"""
        for tag in self.tags_config.get('tags', []):
            if tag.get('variable') == variable:
                return tag.get(field_name,"")

        return ''
    def get_category_by_unique_name(self, unique_name: str) -> Optional[Dict[str, Any]]:
        """根据唯一标识名获取分类配置"""
        for category in self.categories_config.get('categories', []):
            if category.get('unique_name') == unique_name:
                return category
        return None
    def get_category_field(self, unique_name: str,field_name:str) -> str:
        """根据唯一标识名和category域名获取具体category的具体字段值"""
        for category in self.categories_config.get('categories', []):
            if category.get('unique_name') == unique_name:
                return category.get(field_name,"")

        return ''
    def get_required_tags(self) -> List[Dict[str, Any]]:
        """获取所有必填标签"""
        required_tags = []
        for tag in self.get_active_tags():
            if tag.get('required', False):
                required_tags.append(tag)
        return required_tags
    
    def get_non_system_tags(self) -> List[Dict[str, Any]]:
        """获取所有非系统字段标签（system_var=False）,不包括禁用的tag！"""
        non_system_tags = []
        for tag in self.get_active_tags():
            # 从配置中读取system_var字段，默认为False
            if not tag.get('system_var', False):
                non_system_tags.append(tag)
        return non_system_tags
    def get_system_tags(self) -> List[Dict[str, Any]]:
        """获取所有系统字段标签（system_var=True）"""
        system_tags = []
        for tag in self.get_active_tags():
            # 从配置中读取system_var字段，默认为False
            if tag.get('system_var', False):
                system_tags.append(tag)
        return system_tags
    
    def validate_value(self, tag: Dict[str, Any], value: Any) -> bool:
        """验证值是否符合标签的验证规则"""
        # 处理空值：必填项为空则验证失败，非必填为空则通过
        if value is None or value == "":
            return not tag.get('required', False)
        
        # 从标签中获取可能的正则验证规则
        validation_pattern = tag.get('validation')
        
        try:
            t = tag.get('type')
            if t == 'string':
                # 如果有正则规则则用之验证；没有规则则认为合法
                if validation_pattern:
                    return bool(re.match(validation_pattern, str(value)))
                return True
            elif t == 'bool':
                return str(value).lower() in ['true', 'false', 'yes', 'no', '1', '0']
            elif t == 'enum':
                # 枚举类型由UI层或其它逻辑保证合法性
                return True
            else:
                return True
        except Exception:
            # 出现异常则认为验证失败
            return False


# 创建全局配置加载器单例
_config_instance=None
def get_config_instance():
    """获取全局配置加载器单例"""
    global _config_instance
    _config_instance = ConfigLoader() if _config_instance is None else _config_instance
    return _config_instance