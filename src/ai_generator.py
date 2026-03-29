import os
import json
import requests
import time
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import asdict
from src.core.config_loader import get_config_instance
from src.core.database_model import Paper

# 统一的 Provider 配置数据结构
PROVIDER_CONFIGS = [
    {
        "provider": "deepseek",
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]
    },
    {
        "provider": "gemini",
        "api_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "models": ["gemini-3-flash-preview", "gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"]
    },
    {
        "provider": "openai_compatible",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
    }
]

# 全局系统提示：在所有 AI 请求中注入此提示，作为系统角色指令
SYSTEM_PROMPT = (
    "The task is to complete a review of AI + social media analysis in the computer field, "
    "act as a academic assistant."
)

class AIGenerator:
    """AI内容生成器 (支持 DeepSeek, Gemini, OpenAI-Compatible)"""
    
    def __init__(self):
        self.config_loader = get_config_instance()
        self.settings = self.config_loader.settings
        
        self.ai_generate_mark = self.settings['ai'].get('ai_generate_mark', '[AI generated]')
        self.translation_separator = self.settings['database'].get('translation_separator', '[翻译]')
        self.value_deprecation_mark = self.settings['database'].get('value_deprecation_mark', '[Deprecated]')
        
        enable_val = self.settings['ai'].get('enable_ai_generation', 'true')
        self.enabled = str(enable_val).lower() == 'true'

        # 加载配置的 Profiles (已在 ConfigLoader 中解析)
        self.profiles = self._load_profiles_from_settings()
        self.active_profile_name = self.settings['ai'].get('active_profile', 'default_deepseek')
        self.active_profile = self.get_profile(self.active_profile_name)
        self.user_prompts = self.config_loader.load_user_prompts()

    def get_user_prompts(self) -> Dict[str, Any]:
        """获取用户 Prompt 配置。"""
        return dict(self.user_prompts or {})

    def save_user_prompts(self, prompts_payload: Dict[str, Any]) -> None:
        """保存用户 Prompt 配置。"""
        self.config_loader.save_user_prompts(prompts_payload)
        self.user_prompts = self.config_loader.load_user_prompts()

    def _load_profiles_from_settings(self) -> Dict[str, Dict]:
        """从 settings 中转换 Profiles 列表为字典"""
        profiles_list = self.settings['ai'].get('profiles', [])
        profiles_dict = {}
        # 同时保存 list 以便确定索引
        self.profiles_list = profiles_list 
        for p in profiles_list:
            if 'name' in p:
                profiles_dict[p['name']] = p
        return profiles_dict

    def get_profile_index(self, name: str) -> int:
        """获取 Profile 在列表中的索引"""
        for i, p in enumerate(self.profiles_list):
            if p.get('name') == name:
                return i
        return 0

    def get_profile(self, name: str) -> Optional[Dict]:
        return self.profiles.get(name)
        
    def get_all_profiles(self) -> List[Dict]:
        return list(self.profiles.values())

    def is_available(self) -> bool:
        """检查当前激活的 Profile 是否可用（能解析出 Key）"""
        # 注意：这里不再检查 self.enabled，因为 GUI 强制调用时忽略全局开关
        if not self.active_profile:
            return False
        # 检查是否能解析 Key
        idx = self.get_profile_index(self.active_profile_name)
        # 优先使用配置中直接填写的 key (api_key_source 现复用为直接 key 存储)
        direct_key = self.active_profile.get('api_key_source')
        if direct_key and len(direct_key) > 20 and ' ' not in direct_key:
             return True
        
        # 否则尝试从全局池解析
        return bool(self.config_loader.resolve_api_key(idx, direct_key))

    def get_provider_defaults(self, provider: str) -> Dict[str, Union[str, List[str]]]:
        """UI 辅助：获取 Provider 的默认值和模型列表"""
        for config in PROVIDER_CONFIGS:
            if config["provider"] == provider:
                return {
                    "api_url": config["api_url"],
                    "models": config["models"]
                }
        return {"api_url": "", "models": []}

    def save_profiles(self, profiles_list: List[Dict], enable_ai: bool, active_profile_name: str, key_path: Optional[str] = None):
        """保存配置 (代理到 ConfigLoader)"""
        self.config_loader.save_ai_settings(enable_ai, active_profile_name, profiles_list, key_path)
        # 刷新自身状态
        self.__init__()

    def read_paper_file(self, file_path: str) -> str:
        """读取论文PDF内容"""
        if not file_path or not os.path.exists(file_path):
            return ""
        
        try:
            import pypdf
        except ImportError:
            return "[Error: pypdf not installed. Cannot read PDF.]"
            
        try:
            text = ""
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                # 只读前几页和最后几页以节省token，涵盖摘要、引言和结论
                num_pages = len(reader.pages)
                pages_to_read = list(range(min(15, num_pages))) # 前15页
                if num_pages > 10:
                    pages_to_read.extend(list(range(max(10, num_pages-10), num_pages))) # 后10页
                
                for i in sorted(list(set(pages_to_read))):
                    text += reader.pages[i].extract_text() + "\n"
            return text[:20000] # 截断防止过长
        except Exception as e:
            return f"[Error reading PDF: {str(e)}]"

    def generate_category(self, paper: Paper, paper_text: str = "") -> Tuple[str, str]:
        """生成分类建议。返回 (category_unique_name, reasoning/raw_response)"""
        if not self.is_available():
            return "", "AI Not Available"

        # 构建分类树 Prompt
        categories = self.config_loader.get_active_categories()
        cat_prompt = "Available Categories:\n"
        for cat in categories:
            desc = cat.get('description', '')
            cat_prompt += f"- Name: {cat['name']} (ID: {cat['unique_name']}). {desc}\n"

        prompt = f"""Task: Classify the following academic paper into ONE or MORE of the provided categories.
If the paper fits multiple categories, separate IDs with ';'.
If it fits none, reply 'Uncategorized' and explain why.
If the taxonomy needs modification (new category needed), output 'NEW: <suggestion>' and explain.
If an item can be classified down to the secondary category, there is no need to fill in its corresponding primary category additionally.
The classification hierarchy must be consistent: each child must conceptually fall under all of its ancestors without conflict.
The paper must be highly consistent with its corresponding category, and the number of multiple categories should be as few as possible.
最后翻译所有输出为中文

{cat_prompt}

Paper Title: {paper.title}
Abstract: {paper.abstract}
Context: {paper_text[:20000]}

Response Format:
ID1|ID2
Reasoning: ...
"""
        response = self._call_api(prompt, max_tokens=300)
        if not response:
            return "", "API Error"
            
        # 简单解析
        lines = response.strip().split('\n')
        suggested_cat = lines[0].strip()
        reasoning = "\n".join(lines[1:])
        
        # 验证分类是否存在（兼容分隔符/名称/中英标点）
        valid_ids = [str(c.get('unique_name', '')).strip() for c in categories if str(c.get('unique_name', '')).strip()]
        name_to_id = {
            str(c.get('name', '')).strip().lower(): str(c.get('unique_name', '')).strip()
            for c in categories
            if str(c.get('name', '')).strip() and str(c.get('unique_name', '')).strip()
        }

        normalized_text = suggested_cat
        normalized_text = normalized_text.replace('；', ';').replace('，', ',').replace('、', ',').replace('\n', ',')
        normalized_text = normalized_text.replace('ID:', '').replace('id:', '').replace('ID', '').replace('id', '')
        for sep in [';', ',', '|']:
            normalized_text = normalized_text.replace(sep, '|')

        parts = [p.strip().strip('"\'') for p in normalized_text.split('|') if p.strip()]
        clean_parts = []
        for p in parts:
            if p in valid_ids:
                clean_parts.append(p)
                continue
            mapped = name_to_id.get(p.lower())
            if mapped:
                clean_parts.append(mapped)
        
        final_cat = "|".join(dict.fromkeys(clean_parts))
        if not final_cat and "Uncategorized" not in suggested_cat and "NEW:" not in suggested_cat:
             # 如果解析失败，把整个回复当做 reasoning
             return "", response
        
        return final_cat, response

    def _build_user_prompt_block(self, current_user_idea: str = "") -> str:
        """拼接用户侧 Prompt 上下文。"""
        prompts = self.get_user_prompts()
        vibe_papers = prompts.get('vibe_papers', []) if isinstance(prompts.get('vibe_papers', []), list) else []
        writing_ctx = str(prompts.get('writing_paper_context', '') or '').strip()
        other_prompt = str(prompts.get('other_user_prompt', '') or '').strip()
        user_idea = str(current_user_idea or '').strip()

        lines = [
            "User Prompt Context (must be faithfully integrated):",
        ]

        lines.extend([
            "Role Boundary (strict):",
            "- Current paper (the one being processed now) is the ONLY source of factual content.",
            "- Vibe papers are ONLY for language style imitation and sentence-level expression patterns.",
            "- Writing paper context is ONLY for focus selection 、discourse and sentence-level organization.",
            "- Never mix facts, methods, results, or claims from vibe/writing papers into the current paper summary.",
        ])

        if vibe_papers:
            lines.append("- Vibe papers (imitate writing style only, do not copy content):")
            for idx, item in enumerate(vibe_papers, start=1):
                lines.append(f"  {idx}. {item}")
        else:
            lines.append("- Vibe papers: (none)")

        lines.append(f"- Writing paper context: {writing_ctx if writing_ctx else '(none)'}")
        lines.append(f"- Other user prompt: {other_prompt if other_prompt else '(none)'}")
        lines.append(f"- User idea for this generation: {user_idea if user_idea else '(none)'}")
        return "\n".join(lines)

    def _build_question_current_paper_context(self, paper: Paper, paper_text: str = "") -> str:
        """构建提问时当前论文的分层上下文，显式区分事实来源优先级。"""
        paper_dict = asdict(paper)
        summary_fields = {
            'category': paper_dict.get('category', ''),
            'summary_motivation': paper_dict.get('summary_motivation', ''),
            'summary_innovation': paper_dict.get('summary_innovation', ''),
            'summary_method': paper_dict.get('summary_method', ''),
            'summary_conclusion': paper_dict.get('summary_conclusion', ''),
            'summary_limitation': paper_dict.get('summary_limitation', ''),
            'summary_citable_paragraph': paper_dict.get('summary_citable_paragraph', ''),
            'analogy_summary': paper_dict.get('analogy_summary', ''),
            'title_translation': paper_dict.get('title_translation', ''),
            'notes': paper_dict.get('notes', ''),
        }

        meta_fields = {
            'uid': paper_dict.get('uid', ''),
            'doi': paper_dict.get('doi', ''),
            'title': paper_dict.get('title', ''),
            'authors': paper_dict.get('authors', ''),
            'date': paper_dict.get('date', ''),
            'conference': paper_dict.get('conference', ''),
            'paper_url': paper_dict.get('paper_url', ''),
            'project_url': paper_dict.get('project_url', ''),
            'contributor': paper_dict.get('contributor', ''),
            'status': paper_dict.get('status', ''),
            'related_papers': paper_dict.get('related_papers', ''),
            'pipeline_image': paper_dict.get('pipeline_image', ''),
            'paper_file': paper_dict.get('paper_file', ''),
            'zotero_item_ref': paper_dict.get('zotero_item_ref', ''),
        }

        context_lines = [
            "[Current Paper Context | Source Priority]",
            "P0-FACT (highest): Abstract and Paper Full Text.",
            "P1-FACT (supporting): Metadata fields.",
            "P2-REFERENCE (lowest): Summary/analogy fields may contain paraphrase distortion and must be verified against P0.",
            "",
            "[P0-FACT: Abstract]",
            str(paper_dict.get('abstract', '') or '').strip(),
            "",
            "[P0-FACT: Paper Full Text Excerpt]",
            str(paper_text or '').strip(),
            "",
            "[P1-FACT: Metadata JSON]",
            json.dumps(meta_fields, ensure_ascii=False, indent=2),
            "",
            "[P2-REFERENCE: Summary Fields JSON]",
            json.dumps(summary_fields, ensure_ascii=False, indent=2),
        ]
        return "\n".join(context_lines)

    def _build_question_workspace_context(self, papers: List[Paper], current_uid: str = "") -> str:
        """构建跨论文提问上下文，显式区分当前论文与数据库其余条目。"""
        rows: List[Dict[str, Any]] = []
        for idx, p in enumerate(papers):
            payload = asdict(p)
            row = {
                'workspace_index': idx,
                'is_current_paper': bool(current_uid and payload.get('uid', '') == current_uid),
                'paper_item': payload,
            }
            rows.append(row)

        context_lines = [
            "[Workspace Database Context | For Cross-Paper Reasoning]",
            "The following entries are workspace papers, separated from the current-paper context above.",
            "Do not confuse current paper with database peer papers.",
            json.dumps(rows, ensure_ascii=False, indent=2),
        ]
        return "\n".join(context_lines)

    def _build_question_related_papers_context(self, papers: List[Paper], current_uid: str = "") -> str:
        """构建当前论文 related_papers 对应论文上下文。"""
        rows: List[Dict[str, Any]] = []
        for idx, p in enumerate(papers):
            payload = asdict(p)
            rows.append({
                'related_index': idx,
                'is_current_paper': bool(current_uid and payload.get('uid', '') == current_uid),
                'related_paper_item': payload,
            })

        context_lines = [
            "[Related Papers Context | Linked from Current Paper]",
            "The following papers are linked by the current paper's related_papers field.",
            "Use them as additional references only; do not confuse them with the current paper.",
            json.dumps(rows, ensure_ascii=False, indent=2),
        ]
        return "\n".join(context_lines)

    def answer_question_with_paper_context(
        self,
        paper: Paper,
        question: str,
        paper_text: str = "",
        workspace_papers: Optional[List[Paper]] = None,
        related_context_papers: Optional[List[Paper]] = None,
    ) -> str:
        """使用当前论文 item 上下文回答问题，可选附带整个工作区数据库上下文。"""
        if not self.is_available():
            return ""

        q = str(question or '').strip()
        if not q:
            return ""

        current_context = self._build_question_current_paper_context(paper, paper_text)
        workspace_context = ""
        if workspace_papers:
            workspace_context = self._build_question_workspace_context(workspace_papers, current_uid=paper.uid)

        related_context = ""
        if related_context_papers:
            related_context = self._build_question_related_papers_context(related_context_papers, current_uid=paper.uid)

        prompt_parts = [
            "Task: Answer the user's question about the current paper accurately.",
            "Language: Chinese.",
            "",
            "Hard Rules:",
            "1) Treat P0-FACT (abstract + paper full text) as the primary truth source.",
            "2) If summary/analogy fields conflict with P0-FACT, explicitly point out the conflict and trust P0-FACT.",
            "3) When using workspace database context, clearly distinguish current paper vs other papers.",
            "4) Do not fabricate facts not grounded in provided context.",
            "5) If evidence is insufficient, say what is uncertain.",
            "",
            "Output format:",
            "- 回答: <direct answer>",
            "- 依据: <which part(s) support the answer: Abstract / Paper Full Text / Metadata / Summary / Workspace DB>",
            "- 一致性检查: <whether summary-like fields are faithful to facts, if asked>",
            "- 不确定性: <what cannot be confirmed>",
            "",
            f"User Question: {q}",
            "",
            current_context,
        ]

        if workspace_context:
            prompt_parts.extend(["", workspace_context])
        if related_context:
            prompt_parts.extend(["", related_context])

        prompt = "\n".join(prompt_parts)
        resp = self._call_api(prompt, max_tokens=900)
        return resp.strip() if resp else ""

    def generate_field(self, paper: Paper, field: str, paper_text: str = "", current_user_idea: str = "") -> str:
        """通用单字段生成"""
        if not self.is_available(): return ""
        
        category_name = self.config_loader.get_category_field(paper.category.split('|')[0], 'name') if paper.category else "General"
        
        user_prompt_block = self._build_user_prompt_block(current_user_idea)

        base_prompt = f"""Paper: {paper.title}
Category: {category_name}
Abstract: {paper.abstract}
Context: {paper_text[:20000]}

Req: Generate content for field '{field}'.
Constraint: 
1. Bilingual (English then Chinese), separated by '{self.translation_separator}'.
2. The output will be lightly edited and directly used as final manuscript sentences in an AI survey paper.
3. Follow AI academic survey writing conventions: concise, factual, and precise.
4. Do not copy original text; prioritize faithful facts over rhetorical interpretation.
5. Prefer short, citation-ready expressions that can be freely combined into the survey text.
6. If uncertain or inconsistent, correct it before output.
7. Concise (under 100 words).
8. Fields marked with {self.ai_generate_mark} in the prompt are AI-generated and unreviewed by humans, please refer to them cautiously.
9. Strict boundary:
   - Factual content MUST be grounded only in the current paper shown above (title/abstract/context).
   - Vibe papers and writing-paper context MUST NOT contribute factual claims.
   - Vibe papers and writing-paper context are allowed ONLY to guide writing style, focus, and organization.

    {user_prompt_block}
"""
        # 针对特定字段优化 Prompt
        if field == 'title_translation':
            prompt = f"Translate title '{paper.title}' to Chinese. Output ONLY the Chinese translation."
        elif field == 'analogy_summary':
            prompt = f"""{base_prompt}\nProvide a one-sentence analogy summary (TL;DR). 
            E.g., Speculative decision-making: Guess while waiting, great gain if correct, no loss if wrong {self.translation_separator} 推测决策：边等边猜，猜对血赚，猜错不亏
            ;Wisdom of the crowd: Decision-making team model {self.translation_separator} 群体智慧：决策小组模式
            ;A closed ABM simulation system for news dissemination, simulates fake news formation with four role-playing elements {self.translation_separator} 一个封闭的新闻传播仿真 ABM 系统，扮演四种角色，模拟假新闻形成过程"""
        elif field == 'summary_citable_paragraph':
            prompt = f"""{base_prompt}
Generate a compact citation-ready paragraph exactly in the style used when citing a main paper in survey/related-work body text.
Length constraint is strict: one concise sentence per language (EN + ZH), each no more than 45 English words / 60 Chinese characters.
Do NOT write long explanation, bullet points, or background expansion.
It must still cover: motivation, innovation, method, conclusion/effect, and limitation/future outlook (can be compressed into short clauses).
Write as if it will be pasted directly as a main-body citation sentence in a survey.
If one element is missing from the paper, mention uncertainty briefly instead of fabricating.
"""
        else:
            # 通过 ConfigLoader 在运行时获取该字段的描述（避免直接导入配置模块）
            try:
                field_desc = self.config_loader.get_tag_field(field, 'description') or ""
            except Exception:
                field_desc = ""
            prompt = (
                f"{base_prompt}\nSummarize the {field.replace('summary_', '')}.\n"
                f"Field Description: {field_desc}"
            )

        resp = self._call_api(prompt, max_tokens=200)
        if resp:
            # 特殊处理 title_translation 不需要标记
            if field == 'title_translation':
                 return f"{self.ai_generate_mark} {resp.strip()}"
            return f"{self.ai_generate_mark} {resp.strip()}"
        return ""

    def _call_api(self, prompt: str, max_tokens: int = 200) -> Optional[str]:
        if not self.active_profile: return None
        
        # 优先使用配置中直接填写的 key (如果它是像Key的字符串)
        source = self.active_profile.get('api_key_source', '')
        idx = self.get_profile_index(self.active_profile_name)
        
        # 1. 尝试通过 ConfigLoader 解析 (支持索引KeyPool, 环境变量, 路径)
        api_key = self.config_loader.resolve_api_key(idx, source)
        
        # 2. 如果 ConfigLoader 没解析出来，且 source 看起来像直接的 Key (非空，无空格，不含路径符)
        if not api_key and source and len(source) > 10 and os.sep not in source:
            api_key = source

        if not api_key:
            print(f"Error: No API Key found for profile '{self.active_profile_name}'")
            return None

        provider = self.active_profile.get('provider', 'deepseek')
        url = self.active_profile.get('api_url')
        model = self.active_profile.get('model')
        
        if provider == 'deepseek' or provider == 'openai_compatible':
            return self._call_openai_style(api_key, url, model, prompt, max_tokens)
        elif provider == 'gemini':
            return self._call_gemini(api_key, model, prompt, max_tokens)
        return None

    def _call_openai_style(self, api_key, url, model, prompt, max_tokens):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # 在 messages 中注入系统提示（system role），再附带用户提示
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        try:
            # 兼容 DeepSeek 和其他 OpenAI 格式
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"API Error ({model}): {e}")
            return None

    def _call_gemini(self, api_key, model, prompt, max_tokens):
        # Gemini REST API 构建
        # URL 示例: https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=KEY
        base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        final_url = f"{base_url}/{model}:generateContent?key={api_key}"
        # 将系统提示与用户 prompt 合并，保证 Gemini 也能接收到系统级说明
        prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            resp = requests.post(final_url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # 安全获取
            if 'candidates' in data and data['candidates']:
                return data['candidates'][0]['content']['parts'][0]['text']
            return None
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return None

    def enhance_paper_with_ai(
        self,
        paper: Paper,
        paper_text: str = "",
        fields_to_gen: Optional[List[str]] = None,
        field_user_ideas: Optional[Dict[str, str]] = None
    ) -> Tuple[Paper, bool]:
        is_enhanced = False
        new_paper = Paper.from_dict(asdict(paper))
        
        all_ai_fields = ['title_translation', 'analogy_summary', 'summary_motivation', 
                  'summary_innovation', 'summary_method', 'summary_conclusion', 'summary_limitation',
                  'summary_citable_paragraph']
        
        target_fields = fields_to_gen if fields_to_gen else all_ai_fields
        
        for f in target_fields:
            # 如果指定了字段，强制生成；否则仅生成空的或Deprecated的
            curr = getattr(new_paper, f)
            if fields_to_gen or (not curr or self.value_deprecation_mark in str(curr)):
                user_idea = ''
                if isinstance(field_user_ideas, dict):
                    user_idea = str(field_user_ideas.get(f, '') or '').strip()
                val = self.generate_field(new_paper, f, paper_text, current_user_idea=user_idea)
                if val:
                    setattr(new_paper, f, val)
                    is_enhanced = True
        return new_paper, is_enhanced

    def batch_enhance_papers(self, papers: List[Paper]) -> Tuple[List[Paper],bool]:
        """批量增强论文信息 (兼容旧接口)"""
        if not self.is_available():
            return papers, False
        is_enhanced = False
        enhanced_papers = []
        for i, paper in enumerate(papers):
            print(f"AI处理论文 {i+1}/{len(papers)}: {paper.title[:50]}...")
            enhanced_paper, _is_enhanced = self.enhance_paper_with_ai(paper)
            if _is_enhanced:
                is_enhanced = True
            enhanced_papers.append(enhanced_paper)
            time.sleep(1)
        return enhanced_papers, is_enhanced