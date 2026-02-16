"""
更新文件工具模块
统一处理数据文件（CSV和JSON）的读取、写入
提供资源规范化（Assets）功能
完全移除 Pandas 和 Excel 依赖，使用 Python 原生 csv/json 模块
"""
import os
import json
import csv
import shutil
import re
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import asdict

from src.core.config_loader import get_config_instance
from src.core.database_model import Paper, is_same_identity
from src.utils import ensure_directory, backup_file, get_current_timestamp, generate_paper_uid

class UpdateFileUtils:
    """更新文件工具类 (CSV/JSON/Assets)"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        # 路径配置
        self.backup_dir = self.settings['paths']['backup_dir']
        self.assets_dir = self.settings['paths'].get('assets_dir', 'assets/')
        
        # 废弃 figures_dir 和 paper_dir 的直接写入，只用于向后兼容读取解析
        self.legacy_figure_dir = self.settings['paths'].get('figure_dir', 'figures/')
        self.legacy_paper_dir = self.settings['paths'].get('paper_dir', 'papers/')
        
        self.project_root = self.config.project_root

    # ================= 统一 IO 接口 =================

    def read_data(self, filepath: str) -> Tuple[bool, List[Paper]]:
        """
        统一读取入口
        根据后缀自动判断 CSV 或 JSON
        """
        if not filepath or not os.path.exists(filepath):
            return False, []
        
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.json':
            return self.load_papers_from_json(filepath)
        elif ext == '.csv':
            return self.load_papers_from_csv(filepath)
        else:
            print(f"不支持的文件格式: {filepath}")
            return False, []

    def write_data(self, filepath: str, papers: List[Paper]) -> bool:
        """
        统一写入入口
        根据后缀自动判断 CSV 或 JSON
        注意：此操作会自动规范化文件结构（重写表头/Meta）
        """
        if not filepath:
            return False
        
        ensure_directory(os.path.dirname(filepath))
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext == '.json':
            return self.save_papers_to_json(filepath, papers)
        elif ext == '.csv':
            return self.save_papers_to_csv(filepath, papers)
        else:
            print(f"不支持的写入格式: {filepath}")
            return False

    # ================= CSV 处理 (核心逻辑) =================

    def load_papers_from_csv(self, filepath: str) -> Tuple[bool, List[Paper]]:
        """
        读取 CSV 文件
        格式规范：
        第1行: Human Readable Header (Table Name) - 忽略，仅供人类阅读
        第2行: System Variables (tag variable) - 核心，用于映射列数据
        第3行+: Data
        """
        papers = []

        # 尝试多种常见编码，先 utf-8-sig（兼容 BOM），再尝试常见回退编码
        encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'cp1252', 'latin-1']
        last_exc = None

        for enc in encodings_to_try:
            try:
                with open(filepath, 'r', encoding=enc, errors='strict') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                    if len(rows) < 2:
                        return False, []

                    header_ids = [h.strip() for h in rows[1]]

                    for row_data in rows[2:]:
                        if not any(row_data):
                            continue

                        if len(row_data) < len(header_ids):
                            row_data += [''] * (len(header_ids) - len(row_data))

                        paper_dict = {}
                        for i, tag_id in enumerate(header_ids):
                            if not tag_id: continue
                            paper_dict[tag_id] = row_data[i]

                        if paper_dict:
                            papers.append(self._dict_to_paper(paper_dict))

                # 成功读取则跳出循环
                return True, papers
            except Exception as e:
                last_exc = e
                # 尝试下一个编码
                continue

        # 如果所有编码都失败，打印最后一个异常并返回失败
        print(f"读取 CSV 失败 {filepath}: {last_exc}")
        return False, []

    def save_papers_to_csv(self, filepath: str, papers: List[Paper]) -> bool:
        """
        保存为 CSV 文件
        写入逻辑（规范化结构）：
        1. 获取所有 Active Tags，按 Order 排序
        2. Row 1: Table Name (Display Name)
        3. Row 2: Tag Variable (System Key)
        4. Row 3+: Data
        """
        # 获取排序后的激活 Tag
        tags = self.config.get_active_tags()
        tags.sort(key=lambda x: x.get('order', 0))
        
        # 准备表头
        display_names = [t.get('table_name', t.get('variable', '')) for t in tags]
        tag_ids = [t.get('variable') for t in tags if t.get('variable')]
        
        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                
                # 1. 写入显示名称 (Row 1)
                writer.writerow(display_names)
                # 2. 写入系统ID (Row 2)
                writer.writerow(tag_ids)
                
                # 3. 写入数据 (Row 3+)
                for paper in papers:
                    paper_dict = self._paper_to_dict(paper)
                    row = []
                    for tid in tag_ids:
                        # 获取值并转字符串
                        val = paper_dict.get(tid, "")
                        if val is None: val = ""
                        
                        # 处理列表/字典等复杂类型转JSON字符串
                        if isinstance(val, (list, dict)):
                            val = json.dumps(val, ensure_ascii=False)
                        
                        # 简单的布尔值处理
                        if isinstance(val, bool):
                            val = str(val).lower()
                            
                        row.append(str(val))
                    writer.writerow(row)
            return True
        except Exception as e:
            print(f"写入 CSV 失败 {filepath}: {e}")
            return False

    # ================= JSON 处理 (核心逻辑) =================

    def load_papers_from_json(self, filepath: str) -> Tuple[bool, List[Paper]]:
        """
        读取 JSON
        支持新结构: {"meta": {"column_ids": [...]}, "papers": [...]}
        兼容旧结构: {"papers": [...]} 或 [...]
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            raw_list = []
            
            if isinstance(data, dict):
                # 尝试从 meta 中读取列顺序信息（如有必要可校验）
                # meta_ids = data.get('meta', {}).get('column_ids', [])
                
                if 'papers' in data: 
                    raw_list = data['papers']
                # 兼容旧格式单对象
                elif 'title' in data: 
                    raw_list = [data]
            elif isinstance(data, list):
                raw_list = data
            
            return True, [self._dict_to_paper(p) for p in raw_list]
        except Exception as e:
            print(f"读取 JSON 失败 {filepath}: {e}")
            return False, []

    def save_papers_to_json(self, filepath: str, papers: List[Paper]) -> bool:
        """
        保存 JSON
        结构规范化：
        {
          "meta": {
             "generated_at": "...",
             "column_ids": ["uid", "doi", ...]  <-- 记录当前Tag配置的ID顺序
          },
          "papers": [
             { "uid": "...", "doi": "...", ... }, <-- 键顺序与 column_ids 尽量保持一致（虽JSON无序，但便于阅读）
             ...
          ]
        }
        """
        try:
            # 获取排序后的 tag variable 列表
            tags = self.config.get_active_tags()
            tags.sort(key=lambda x: x.get('order', 0))
            ordered_ids = [t.get('variable') for t in tags if t.get('variable')]

            # 1. 准备 Meta
            existing_meta = {}
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                        if isinstance(d, dict) and 'meta' in d:
                            existing_meta = d['meta']
                except: pass
            
            existing_meta['generated_at'] = get_current_timestamp()
            existing_meta['column_ids'] = ordered_ids # 显式记录ID逻辑

            # 2. 准备 Papers 数据 (尽量保证字典键序)
            serialized_papers = []
            for paper in papers:
                raw_dict = self._paper_to_dict(paper)
                ordered_dict = {}
                for tid in ordered_ids:
                    # 确保所有 Active Tag 都在字典中，缺失补空
                    val = raw_dict.get(tid, "")
                    ordered_dict[tid] = val if val is not None else ""
                
                serialized_papers.append(ordered_dict)
            
            output = {
                "meta": existing_meta,
                "papers": serialized_papers
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"写入 JSON 失败 {filepath}: {e}")
            return False

    # ================= 资源管理 (Assets) =================

    def normalize_assets(self, paper: Paper) -> Paper:
        """
        规范化论文资源路径
        1. 检查是否有资源 (pipeline_image, paper_file)
        2. 如果有资源但无 UID，生成 UID
        3. 确保 assets/{uid} 目录存在
        4. 将文件移动/复制到 assets/{uid}/ 并更新字段为相对路径
        """
        has_assets = bool(paper.pipeline_image or paper.paper_file)
        
        # 如果没有资源且没有UID，不需要做任何事
        # (如果业务逻辑要求所有论文必须有UID，可以在这里强制生成)
        if not has_assets and not paper.uid:
            return paper

        # 1. 确保 UID 存在（基于 title+doi 的稳定 hash）
        if not paper.uid:
            paper.uid = generate_paper_uid(getattr(paper, 'title', ''), getattr(paper, 'doi', ''))
        
        # 目标目录: assets/{uid}/
        paper_asset_dir = os.path.join(self.project_root, self.assets_dir, paper.uid)
        ensure_directory(paper_asset_dir)
        
        # 2. 处理 Pipeline Image
        if paper.pipeline_image:
            new_paths = []
            # 支持多图
            for raw_path in re.split(r'[;；]', paper.pipeline_image):
                clean_path = raw_path.strip()
                if not clean_path: continue
                
                # 尝试定位源文件 (可能是旧路径 figures/xxx 或绝对路径)
                src_path = self._resolve_source_path(clean_path, self.legacy_figure_dir)
                
                if src_path and os.path.exists(src_path):
                    filename = os.path.basename(src_path)
                    dest_path = os.path.join(paper_asset_dir, filename)
                    
                    # 如果目标位置没有文件，或者与源文件不同，则复制
                    try:
                        if not os.path.exists(dest_path) or not os.path.samefile(src_path, dest_path):
                            shutil.copy2(src_path, dest_path)
                    except Exception as e:
                        print(f"复制资源失败 {src_path} -> {dest_path}: {e}")

                    # 使用相对于 project_root 的相对路径，保证保存为相对路径（如 assets/uid/filename）
                    try:
                        rel_path = os.path.relpath(dest_path, self.project_root).replace('\\', '/')
                    except Exception:
                        # 兜底为传统拼接
                        rel_path = os.path.join(self.assets_dir, paper.uid, filename).replace('\\', '/')
                    new_paths.append(rel_path)
                else:
                    # 如果找不到源文件，可能是已经是规范路径了，或者文件丢失
                    # 保留原值，交给验证环节报错
                    # 尝试标准化斜杠
                    norm_clean = clean_path.replace('\\', '/')
                    assets_prefix = os.path.join(self.assets_dir, paper.uid, '').replace('\\', '/')
                    if assets_prefix and assets_prefix in norm_clean:
                        new_paths.append(norm_clean)
                    else:
                        print(f"警告: 找不到资源文件 {clean_path}")
                        new_paths.append(clean_path)
            
            paper.pipeline_image = ";".join(new_paths)

        # 3. 处理 Paper File (PDF)
        if paper.paper_file:
            clean_path = paper.paper_file.strip()
            if clean_path:
                src_path = self._resolve_source_path(clean_path, self.legacy_paper_dir)
                
                if src_path and os.path.exists(src_path):
                    filename = os.path.basename(src_path)
                    dest_path = os.path.join(paper_asset_dir, filename)
                    
                    try:
                        if not os.path.exists(dest_path) or not os.path.samefile(src_path, dest_path):
                            shutil.copy2(src_path, dest_path)
                    except Exception as e:
                        print(f"复制资源失败 {src_path} -> {dest_path}: {e}")
                    try:
                        paper.paper_file = os.path.relpath(dest_path, self.project_root).replace('\\', '/')
                    except Exception:
                        paper.paper_file = os.path.join(self.assets_dir, paper.uid, filename).replace('\\', '/')
                else:
                    # 检查是否已经是正确路径
                    norm_clean = clean_path.replace('\\', '/')
                    assets_prefix = os.path.join(self.assets_dir, paper.uid, '').replace('\\', '/')
                    if assets_prefix and assets_prefix in norm_clean:
                        paper.paper_file = norm_clean
                    else:
                        print(f"警告: 找不到论文文件 {clean_path}")
        
        return paper

    def _resolve_source_path(self, path_str: str, legacy_dir_rel: str) -> Optional[str]:
        """尝试解析文件绝对路径"""
        # 1. 绝对路径
        if os.path.isabs(path_str):
            return path_str
        
        # 2. 相对项目根目录 (最优先)
        p1 = os.path.join(self.project_root, path_str)
        if os.path.exists(p1): return p1
        
        # 3. 相对旧目录 (兼容 figures/xxx 这种写法)
        # 如果 path_str 已经包含 legacy_dir_rel (e.g. figures/a.png), p1 已经覆盖
        # 如果 path_str 只是文件名 (a.png) 且 legacy_dir 存在
        p2 = os.path.join(self.project_root, legacy_dir_rel, os.path.basename(path_str))
        if os.path.exists(p2): return p2

        return None

    # ================= 辅助转换 =================

    def _dict_to_paper(self, data: Dict) -> Paper:
        """字典转 Paper，处理类型转换"""
        # 提取已知字段
        valid_keys = Paper.__dataclass_fields__.keys()
        clean_data = {}
        tags_map = {t.get('variable'): t for t in self.config.get_active_tags() if t.get('variable')}
        
        for k, v in data.items():
            if k in valid_keys:
                # 类型转换
                tag_cfg = tags_map.get(k)
                if tag_cfg:
                    target_type = tag_cfg.get('type', 'string')
                    clean_data[k] = self._convert_type(v, target_type)
                else:
                    clean_data[k] = v
        
        return Paper(**clean_data)

    def _paper_to_dict(self, paper: Paper) -> Dict:
        """Paper 转字典"""
        return asdict(paper)

    def _convert_type(self, value: Any, target_type: str) -> Any:
        if value is None: return ""
        s_val = str(value).strip()
        
        if target_type == 'bool':
            return s_val.lower() in ('true', 'yes', '1', 'on')
        elif target_type == 'int':
            try: return int(float(s_val)) if s_val else 0
            except: return 0
        elif target_type == 'float':
            try: return float(s_val) if s_val else 0.0
            except: return 0.0
        # string, text, enum...
        return s_val

    # ================= 兼容旧接口 (逻辑适配) =================
    # 保留这些方法签名，因为上层逻辑（update.py, submit_logic.py）可能在调用
    # 但内部实现已切换到新的读写逻辑

    def normalize_category_value(self, raw_val: Any, config_instance) -> str:
        """规范化 Category (逻辑不变)"""
        if raw_val is None: return ""
        s = str(raw_val).strip()
        if not s: return ""

        parts = [p.strip() for p in re.split(r'[;；]', s) if p.strip()]
        if not parts: return ""

        try:
            max_allowed = int(config_instance.settings['database'].get('max_categories_per_paper', 4))
        except: max_allowed = 4

        out = []
        seen = set()
        change_list = config_instance.get_categories_change_list()

        for val in parts:
            # 应用变更
            for rule in change_list:
                if rule.get('old_unique_name') == val:
                    val = rule.get('new_unique_name')
                    break
            
            # 查找定义 (优先匹配 unique_name)
            cat = config_instance.get_category_by_name_or_unique_name(val)
            uname = cat.get('unique_name', val) if cat else val
            
            if uname and uname not in seen:
                seen.add(uname)
                out.append(uname)
            if len(out) >= max_allowed: break
            
        return ";".join(out)
    
    def persist_ai_generated_to_update_files(self, papers: List[Paper], file_path: str):
        """回写 AI 数据到文件"""
        # 读取 -> 更新 -> 写入
        success, existing = self.read_data(file_path)
        if not success or not existing: return
        
        updated_count = 0
        ai_fields = ['title_translation', 'analogy_summary',
                    'summary_motivation', 'summary_innovation',
                    'summary_method', 'summary_conclusion', 'summary_limitation']

        for new_p in papers:
            for old_p in existing:
                if is_same_identity(new_p, old_p):
                    # 更新字段
                    changed = False
                    for f in ai_fields:
                        val = getattr(new_p, f, "")
                        # 仅当旧值为空或明显需要更新时覆盖? 
                        # 原逻辑是: if new_value: setattr
                        # 这里保持原逻辑：如果有新值，则覆盖
                        if val and val != getattr(old_p, f, ""):
                            setattr(old_p, f, val)
                            changed = True
                    if changed: updated_count += 1
                    break
        
        if updated_count > 0:
            backup_file(file_path, self.backup_dir)
            self.write_data(file_path, existing)


# 创建全局单例
_update_file_utils_instance = None

def get_update_file_utils():
    """获取更新文件工具单例"""
    global _update_file_utils_instance
    if _update_file_utils_instance is None:
        _update_file_utils_instance = UpdateFileUtils()
    return _update_file_utils_instance