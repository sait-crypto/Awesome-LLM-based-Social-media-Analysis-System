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
    USER_PROMPTS_FILE = 'user_prompts.json'
    def __init__(self):
        if getattr(sys, 'frozen', False):
            # 如果是打包后的可执行文件，使用可执行文件所在目录作为项目根
            self.project_root = Path(sys.executable).resolve().parents[0]
        else:
            # 以模块位置上溯两级作为项目根（保证以项目根为基准解析所有相对路径）
            # src/core -> src -> root (2 levels up from src, so 3 levels from here)
            self.project_root = Path(__file__).resolve().parents[2]
        # config 目录在项目根下的 config 子目录
        self.config_path = (self.project_root / 'config').resolve()

        # 读取配置（_load_settings 会使用 self.project_root 来解析相对路径）
        self.settings = self._load_settings()
        self.tags_config = self._load_tags_config()
        self.categories_config = self._load_categories_config()

        # 便于其他模块直接使用绝对路径
        self.paths = self.settings.get('paths', {})
        
        # 加载全局 API Key 池
        self.api_keys = self._load_global_api_keys()
    
    def _load_settings(self) -> Dict[str, Any]:
        """加载config.ini文件，优先加载默认配置，再覆盖用户配置"""
        # 为健壮性，除#外，也支持 //和; 作为注释
        config = configparser.ConfigParser(inline_comment_prefixes=self.INLINE_COMMENT_PREFIXES)
        
        default_path = (self.config_path / 'config_default.ini').resolve()
        user_path = (self.config_path / 'config.ini').resolve()

        # 1. 读取默认配置
        if default_path.exists():
            config.read(str(default_path), encoding='utf-8')

        # 2. 读取用户配置（覆盖默认）
        if user_path.exists():
            config.read(str(user_path), encoding='utf-8')

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

        # 处理 AI 配置的 Profiles JSON 解析
        if 'ai' in settings:
            settings['ai']['profiles'] = self._process_ai_profiles(settings['ai'])

        return settings

    def _load_global_api_keys(self) -> List[str]:
        """从文件或环境变量加载全局 API Keys 列表"""
        keys = []
        
        # 1. 尝试从环境变量获取 (GitHub Secrets: AI_API_KEY)
        env_keys = os.environ.get('AI_API_KEY', '')
        if env_keys:
            if '\n' in env_keys:
                keys.extend([k.strip() for k in env_keys.split('\n') if k.strip()])
            else:
                keys.extend([k.strip() for k in env_keys.split(',') if k.strip()])
            if keys: return keys

        # 2. 尝试从本地文件获取 (key_path)
        key_path = self.settings.get('ai', {}).get('key_path', '')
        if key_path:
            try:
                p = Path(key_path)
                if not p.is_absolute():
                    p = self.project_root / p
                
                if p.exists() and p.is_file():
                    with open(p, 'r', encoding='utf-8') as f:
                        content = f.read()
                        keys.extend([line.strip() for line in content.splitlines() if line.strip()])
            except Exception as e:
                print(f"读取 API Key 文件失败: {e}")

        return keys

    def _process_ai_profiles(self, ai_settings: Dict[str, Any]) -> List[Dict]:
        """处理AI Profiles：解析JSON"""
        raw_profiles = ai_settings.get('profiles_json', '[]')
        profiles = []
        try:
            profiles = json.loads(raw_profiles)
        except Exception:
            profiles = []
        
        if not isinstance(profiles, list):
            profiles = []

        # 转换为字典以便去重/查找
        profiles_dict = {p.get('name'): p for p in profiles if 'name' in p}

        # 确保有默认
        if not profiles_dict:
            # 尝试迁移旧字段 (仅作内存兼容，不回写，除非用户保存)
            path_val = ai_settings.get('deepseek_api_key_path', '')
            env_val = ai_settings.get('api_key_github_secret_name', 'DEEPSEEK_API')
            source = path_val if path_val else env_val
            
            profiles_dict['default_deepseek'] = {
                "name": "default_deepseek",
                "provider": "deepseek",
                "api_key_source": source,
                "api_url": "https://api.deepseek.com/v1/chat/completions",
                "model": "deepseek-chat"
            }
        
        return list(profiles_dict.values())

    def resolve_api_key(self, profile_index: int = 0, source_override: Optional[str] = None) -> Optional[str]:
        """
        解析 API Key
        逻辑：
        1. 如果提供了 source_override (Profile 中特定的 Key/Path/Env)，尝试解析它。
        2. 否则，从全局 Key 池中按索引获取。
        """
        # 1. 特定覆盖
        if source_override:
            clean_source = str(source_override).strip()
            # 可能是直接的 Key (简单启发式：看起来像Key且不是文件路径)
            if len(clean_source) > 20 and ' ' not in clean_source and os.sep not in clean_source and '.' not in clean_source:
                 return clean_source

            # 尝试环境变量
            env = os.environ.get(clean_source)
            if env: return env.strip()
            # 尝试文件
            try:
                p = Path(clean_source)
                if not p.is_absolute(): p = self.project_root / p
                if p.exists():
                    with open(p, 'r', encoding='utf-8') as f: return f.read().strip()
            except: pass

        # 2. 全局 Key 池
        if self.api_keys:
            if 0 <= profile_index < len(self.api_keys):
                return self.api_keys[profile_index]
            elif len(self.api_keys) > 0:
                return self.api_keys[0] # Fallback to first
        
        return None

    def save_ai_settings(self, enable_ai: bool, active_profile_name: str, profiles_list: List[Dict], key_path: Optional[str] = None):
        """保存 AI 设置到 config.ini"""
        config = configparser.ConfigParser()
        user_path = self.config_path / 'config.ini'
        
        if user_path.exists():
            config.read(str(user_path), encoding='utf-8')
        
        if 'ai' not in config:
            config['ai'] = {}
            
        config['ai']['enable_ai_generation'] = str(enable_ai).lower()
        config['ai']['active_profile'] = active_profile_name
        config['ai']['profiles_json'] = json.dumps(profiles_list)
        
        # 只有当显式传入 key_path 时才保存，否则保留原值
        if key_path is not None:
            config['ai']['key_path'] = key_path
        
        # 清理旧字段
        for old_key in ['deepseek_api_key_path', 'api_key_github_secret_name']:
            if old_key in config['ai']:
                del config['ai'][old_key]
        
        with open(user_path, 'w', encoding='utf-8') as f:
            config.write(f)
        
        # 刷新
        self.settings = self._load_settings()
        self.api_keys = self._load_global_api_keys()

    def get_ai_provider_defaults(self, provider: str) -> Dict[str, str]:
        """获取 Provider 的默认值"""
        # (此处由 AIGenerator.get_provider_defaults 实现，保持空实现避免循环)
        return {} 

    def _default_user_prompts_payload(self) -> Dict[str, Any]:
        """默认用户 Prompt 配置。"""
        return {
            'vibe_papers': [],
            'writing_paper_context': '',
            'other_user_prompt': ''
        }

    def get_user_prompts_file_path(self) -> Path:
        """用户 Prompt 配置文件路径。"""
        return (self.config_path / self.USER_PROMPTS_FILE).resolve()

    def load_user_prompts(self) -> Dict[str, Any]:
        """读取用户 Prompt 配置；缺失或损坏时返回默认值。"""
        default_payload = self._default_user_prompts_payload()
        file_path = self.get_user_prompts_file_path()
        if not file_path.exists():
            return dict(default_payload)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception:
            return dict(default_payload)

        if not isinstance(payload, dict):
            return dict(default_payload)

        vibe_raw = payload.get('vibe_papers', [])
        if isinstance(vibe_raw, list):
            vibe_papers = [str(item).strip() for item in vibe_raw if str(item).strip()]
        else:
            vibe_papers = []

        return {
            'vibe_papers': vibe_papers,
            'writing_paper_context': str(payload.get('writing_paper_context', '') or '').strip(),
            'other_user_prompt': str(payload.get('other_user_prompt', '') or '').strip(),
        }

    def save_user_prompts(self, prompts_payload: Dict[str, Any]) -> None:
        """保存用户 Prompt 配置到 config 目录下 JSON 文件。"""
        payload = self._default_user_prompts_payload()
        payload.update(prompts_payload or {})

        vibe_raw = payload.get('vibe_papers', [])
        if isinstance(vibe_raw, list):
            vibe_papers = [str(item).strip() for item in vibe_raw if str(item).strip()]
        else:
            vibe_papers = []

        normalized = {
            'vibe_papers': vibe_papers,
            'writing_paper_context': str(payload.get('writing_paper_context', '') or '').strip(),
            'other_user_prompt': str(payload.get('other_user_prompt', '') or '').strip(),
        }

        file_path = self.get_user_prompts_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
    
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
        # 返回按 order 排序的启用分类。当 order 值重复时，保持配置中出现的原始顺序。
        raw = self.categories_config.get('categories', []) or []
        active_categories = []
        for idx, category in enumerate(raw):
            if category.get('enabled', True):
                # 附加原始索引，便于稳定排序时作为次级键
                cat = dict(category)
                cat['_original_index'] = idx
                active_categories.append(cat)

        # 使用 tuple(key_order, original_index) 进行排序，保证当 order 相同时保持原始出现顺序
        active_categories.sort(key=lambda c: (c.get('order', 0), c.get('_original_index', 0)))

        # 在返回前移除内部使用的临时字段
        for c in active_categories:
            if '_original_index' in c:
                del c['_original_index']

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
    
    def get_categories_change_list(self) -> List[Dict[str, str]]:
        """获取分类变更列表"""
        return self.categories_config.get('categories_change_list', [])
    
    def get_category_by_name_or_unique_name(self, identifier: str) -> Optional[Dict[str, Any]]:
        """根据 unique_name 或 name 获取分类配置"""
        # 首先按 unique_name 匹配
        for category in self.categories_config.get('categories', []):
            if category.get('unique_name') == identifier:
                return category
        
        # 如果按 unique_name 未找到，则按 name 匹配
        for category in self.categories_config.get('categories', []):
            if category.get('name') == identifier:
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
        if value is None or value == "":
            return not tag.get('required', False)
        
        validation_pattern = tag.get('validation')
        
        try:
            t = tag.get('type')
            if t == 'string':
                if validation_pattern:
                    return bool(re.match(validation_pattern, str(value)))
                return True
            elif t == 'bool':
                return str(value).lower() in ['true', 'false', 'yes', 'no', '1', '0']
            elif t == 'enum':
                return True
            else:
                return True
        except Exception:
            return False


# 创建全局配置加载器单例
_config_instance = None
def get_config_instance():
    """获取全局配置加载器单例"""
    global _config_instance
    _config_instance = ConfigLoader() if _config_instance is None else _config_instance
    return _config_instance