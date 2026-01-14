"""
AI生成器
使用DeepSeek API生成论文摘要、翻译等内容
"""
import os
import json
import requests
from typing import Dict, List, Optional, Any
import time
from dataclasses import asdict
from src.core.update_file_utils import get_update_file_utils
from src.core.config_loader import get_config_instance
from src.core.database_model import Paper


class AIGenerator:
    """AI内容生成器"""
    
    def __init__(self):
        self.config = get_config_instance()
        self.settings = get_config_instance().settings
        self.update_utils = get_update_file_utils()

        self.ai_generate_mark=self.settings['ai']['ai_generate_mark']
        self.translation_separator=self.settings['database']['translation_separator']
        self.value_deprecation_mark=self.settings['database']['value_deprecation_mark']

        # 兼容配置项为 bool 或 str 的情况；确保得到布尔值
        enable_val = self.settings['ai'].get('enable_ai_generation', 'true')
        try:
            self.enabled = str(enable_val).lower() == 'true'
        except Exception:
            self.enabled = bool(enable_val)
            
        self.api_key = self._get_api_key()
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.max_retries = 3
        self.retry_delay = 2

        
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥"""
        # 首先尝试从环境变量获取
        api_key = os.environ.get('DEEPSEEK_API')
        if api_key:
            return str(api_key).strip()
        
        # 尝试从本地文件获取
        api_key_path = self.settings['ai'].get('deepseek_api_key_path', '')
        if api_key_path and os.path.exists(api_key_path):
            try:
                with open(api_key_path, 'r', encoding='utf-8') as f:
                    api_key = f.read().strip()
                    return api_key
            except Exception as e:
                print(f"读取API密钥文件失败: {e}")
        
        return None
    
    def is_available(self) -> bool:
        """检查AI生成是否可用"""
        # api_key 需要为非空字符串才能视为可用
        return bool(self.enabled) and bool(self.api_key)
    
    def generate_title_translation(self, paper: Paper) -> str:
        """生成标题翻译"""
        if not self.is_available():
            return ""
        category_name = self._get_category_name(paper.category)
        prompt = f"""请将以下学术论文标题翻译成中文：

英文标题: {paper.title}
论文分类（供参考）: {category_name}
请提供准确、专业的中文翻译，保持学术风格。"""
        
        if paper.abstract:
            prompt += f"\n论文摘要（供参考）:\n{paper.abstract}"
        if paper.summary_motivation and (not str(paper.summary_motivation).startswith(self.ai_generate_mark)):
            prompt += f"\n论文动机（供参考）:\n{paper.summary_motivation}"
        if paper.summary_innovation and (not str(paper.summary_innovation).startswith(self.ai_generate_mark)):
            prompt += f"\n论文创新点（供参考）:\n{paper.summary_innovation}"
        if paper.summary_method and (not str(paper.summary_method).startswith(self.ai_generate_mark)):
            prompt += f"\n论文方法（供参考）:\n{paper.summary_method}"
        if paper.summary_conclusion and (not str(paper.summary_conclusion).startswith(self.ai_generate_mark)):
            prompt += f"\n论文结论（供参考）:\n{paper.summary_conclusion}"
        if paper.summary_limitation and (not str(paper.summary_limitation).startswith(self.ai_generate_mark)):
            prompt += f"\n论文局限性（供参考）:\n{paper.summary_limitation}"
        response = self._call_api(prompt, max_tokens=100)
        if response:
            return f"{self.ai_generate_mark} {response.strip()}"
        return ""
    
    def generate_analogy_summary(self, paper: Paper) -> str:
        """生成类比总结"""
        if not self.is_available():
            return ""
        
        category_name = self._get_category_name(paper.category)
        
        prompt = f"""请为以下论文生成一个简洁的类比总结（一句话）：

论文标题: {paper.title}
论文分类: {category_name}

要求：
1. 用一句话概括方法的核心
2. 适当使用比喻或类比
3. 保持学术性但易懂
4. 长度控制在35字以内，能短尽量短
5. 提示词中前面标有{self.ai_generate_mark}的字段表示由AI生成，未经人类审核，请谨慎参考
6. 不能出现'|'字符
7.生成中英双语，先英文再中文，使用{self.translation_separator}字符串分割

"
示例：
推测决策：边等边猜，猜对血赚，猜错不亏
群体智慧：决策小组模式
一个封闭的新闻传播仿真ABM系统，扮演四种角色，模拟假新闻形成过程

请直接给出总结，不要添加额外说明。"""
        if paper.abstract:
            prompt += f"\n论文摘要:\n{paper.abstract}"
        if paper.summary_motivation and (not str(paper.summary_motivation).startswith(self.ai_generate_mark)):
            prompt += f"\n论文动机:\n{paper.summary_motivation}"
        if paper.summary_innovation and (not str(paper.summary_innovation).startswith(self.ai_generate_mark)):
            prompt += f"\n论文创新点:\n{paper.summary_innovation}"
        if paper.summary_method and (not str(paper.summary_method).startswith(self.ai_generate_mark)):
            prompt += f"\n论文方法:\n{paper.summary_method}"
        if paper.summary_conclusion and (not str(paper.summary_conclusion).startswith(self.ai_generate_mark)):
            prompt += f"\n论文结论:\n{paper.summary_conclusion}"
        if paper.summary_limitation and (not str(paper.summary_limitation).startswith(self.ai_generate_mark)):
            prompt += f"\n论文局限性:\n{paper.summary_limitation}"
        
        response = self._call_api(prompt, max_tokens=100)
        if response:
            return f"{self.ai_generate_mark} {response.strip()}"
        return ""
    
    def generate_summary_fields(self, paper: Paper, field: str) -> str:
        """生成一句话总结的各个字段"""
        if not self.is_available():
            return ""
        
        category_name = self._get_category_name(paper.category)
        # 准备论文信息
        preprompt = f"""
我在为综述写作收集论文，你需要朝着可供综述直接引用的方向，生成精悍的具体内容
要求：
1. 你只是总结分工的一部分，直接给出所要求内容，不要添加任何多余信息，它们由其他人生成
2. 提示词中前面标有{self.ai_generate_mark}的字段表示由AI生成，未经人类审核，请谨慎参考
3. 不能出现'|'字符
4. 生成中英双语，先英文再中文，使用{self.translation_separator}字符串分割


示例：
以往研究没有考虑到假新闻存在一个形成过程（如果要求你给出动机）
将参数优化过程迁移到自然语言空间，利用自然语言的强大能力（如果要求你给出创新点）
蒸馏教师模型的知识到学生模型中；使用强化学习强化情感分类能力（如果要求你给出方法）
获得了52%的识别准确率增幅（如果要求你给出结论）
整个框架所有环节都依赖LLM的固有能力（如果要求你给出局限）

论文标题: {paper.title}
论文分类: {category_name}
"""
        if paper.abstract:
            preprompt += f"\n论文摘要:\n{paper.abstract}"
        if paper.summary_motivation and (not str(paper.summary_motivation).startswith(self.ai_generate_mark)):
            preprompt += f"\n论文动机:\n{paper.summary_motivation}"
        if paper.summary_innovation and (not str(paper.summary_innovation).startswith(self.ai_generate_mark)):
            preprompt += f"\n论文创新点:\n{paper.summary_innovation}"
        if paper.summary_method and (not str(paper.summary_method).startswith(self.ai_generate_mark)):
            preprompt += f"\n论文方法:\n{paper.summary_method}"
        if paper.summary_conclusion and (not str(paper.summary_conclusion).startswith(self.ai_generate_mark)):
            preprompt += f"\n论文结论:\n{paper.summary_conclusion}"
        if paper.summary_limitation and (not str(paper.summary_limitation).startswith(self.ai_generate_mark)):
            preprompt += f"\n论文局限性:\n{paper.summary_limitation}"

        # 生成各个字段
        fields = {}
        
        # 1. 目标/动机
        motivation_prompt = f"""{preprompt}

你的分工：请总结并直接给出这篇论文的研究目标或动机（45字以内，能短尽量短）："""
        if  field == 'summary_motivation':
            motivation = self._call_api(motivation_prompt, max_tokens=80)
            if motivation:
                return f"{self.ai_generate_mark} {motivation.strip()}"
        
        # 2. 创新点
        innovation_prompt = f"""{preprompt}

你的分工：请总结并直接给出这篇论文的主要创新点，即该论文有什么值得我引用到综述里的（45字以内，能短尽量短）："""
        if field == 'summary_innovation':
            innovation = self._call_api(innovation_prompt, max_tokens=80)
            if innovation:
                return f"{self.ai_generate_mark} {innovation.strip()}"
        
        # 3. 方法精炼
        method_prompt = f"""{preprompt}

你的分工：请精炼总结并直接给出这篇论文的核心方法（70字以内，能短尽量短）："""
        if field == 'summary_method':
            method = self._call_api(method_prompt, max_tokens=80)
            if method:
                return f"{self.ai_generate_mark} {method.strip()}"
        
        # 4. 简要结论
        conclusion_prompt = f"""{preprompt}

你的分工：请总结并直接给出这篇论文的主要结论或贡献（45字以内，能短尽量短）："""
        if field == 'summary_conclusion':
            conclusion = self._call_api(conclusion_prompt, max_tokens=80)
            if conclusion:
                return f"{self.ai_generate_mark} {conclusion.strip()}"
        
        # 5. 重要局限/展望
        limitation_prompt = f"""{preprompt}

你的分工：请总结并直接指出这篇论文的重要局限性或未来工作展望（45字以内，能短尽量短）："""
        if field == 'summary_limitation':
            limitation = self._call_api(limitation_prompt, max_tokens=80)
            if limitation:
                return f"{self.ai_generate_mark} {limitation.strip()}"
        
        return ""
    
    def _get_category_name(self, category_unique_name: str) -> str:
        """根据唯一标识名获取分类显示名"""
        categories = self.config.get_active_categories()
        for cat in categories:
            if cat['unique_name'] == category_unique_name:
                return cat['name']
        return category_unique_name
    
    def _call_api(self, prompt: str, max_tokens: int = 200) -> Optional[str]:
        """调用DeepSeek API"""
        if not self.api_key:
            return None
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个专业的学术助手，擅长总结和翻译学术论文。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(self.api_url, headers=headers, 
                                       json=payload, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                return data['choices'][0]['message']['content']
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                print(f"API调用失败: {e}")
                return None
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                print(f"API响应解析失败: {e}")
                return None
        
        return None
    
    def enhance_paper_with_ai(self, paper: Paper) -> Paper:
        """使用AI增强论文信息"""
        if not self.is_available():
            return paper
        
        enhanced_paper = Paper.from_dict(asdict(paper))

        # 仅在无翻译或有标记已弃用时才覆盖，避免覆盖用户手动填写和ai已经生成的满意总结
        # 1. 生成标题翻译
        if not enhanced_paper.title_translation or self.value_deprecation_mark in str(enhanced_paper.title_translation):
            translation = self.generate_title_translation(enhanced_paper)
            if translation:
                enhanced_paper.title_translation = translation
        
        # 2. 生成类比总结
        if not enhanced_paper.analogy_summary or self.value_deprecation_mark in str(enhanced_paper.analogy_summary):
            summary = self.generate_analogy_summary(
                enhanced_paper
            )
            if summary:
                enhanced_paper.analogy_summary = summary
        
        # 3. 生成一句话总结字段
        for field in ['summary_motivation', 'summary_innovation', 'summary_method',
                      'summary_conclusion', 'summary_limitation']:
            current_value = getattr(enhanced_paper, field, "")
            # 仅在字段为空或已由 AI 生成时才覆盖
            if not current_value or self.value_deprecation_mark in str(current_value):
                value = self.generate_summary_fields(enhanced_paper, field)

                setattr(enhanced_paper, field, value)
        
        return enhanced_paper
    
    def batch_enhance_papers(self, papers: List[Paper]) -> List[Paper]:
        """批量增强论文信息"""
        if not self.is_available():
            return papers
        
        enhanced_papers = []
        for i, paper in enumerate(papers):
            print(f"AI处理论文 {i+1}/{len(papers)}: {paper.title[:50]}...")
            enhanced_paper = self.enhance_paper_with_ai(paper)
            enhanced_papers.append(enhanced_paper)
            # 避免API频率限制
            time.sleep(1)
        
        return enhanced_papers