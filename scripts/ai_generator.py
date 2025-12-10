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

from .core.config_loader import config_loader
from .core.database_model import Paper


class AIGenerator:
    """AI内容生成器"""
    
    def __init__(self):
        self.config = config_loader
        self.settings = config_loader.settings
        self.enabled = self.settings['ai'].get('enable_ai_generation', 'true').lower() == 'true'
        self.api_key = self._get_api_key()
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.max_retries = 3
        self.retry_delay = 2
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥"""
        # 首先尝试从环境变量获取
        api_key = os.environ.get('DEEPSEEK_API', '')
        if api_key:
            return api_key
        
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
        return self.enabled and self.api_key is not None
    
    def generate_title_translation(self, title: str, abstract: str = "") -> str:
        """生成标题翻译"""
        if not self.is_available():
            return ""
        
        prompt = f"""请将以下学术论文标题翻译成中文：

英文标题: {title}

请提供准确、专业的中文翻译，保持学术风格。"""
        
        if abstract:
            prompt += f"\n\n论文摘要（供参考）:\n{abstract}"
        
        response = self._call_api(prompt, max_tokens=100)
        if response:
            return f"[AI generated] {response.strip()}"
        return ""
    
    def generate_analogy_summary(self, title: str, abstract: str, category: str) -> str:
        """生成类比总结"""
        if not self.is_available():
            return ""
        
        category_name = self._get_category_name(category)
        
        prompt = f"""请为以下论文生成一个简洁的类比总结（一句话）：

论文标题: {title}
论文分类: {category_name}
论文摘要: {abstract}

要求：
1. 用一句话概括论文的核心贡献
2. 可以适当使用比喻或类比
3. 保持学术性但易懂
4. 长度控制在30-50字

请直接给出总结，不要添加额外说明。"""
        
        response = self._call_api(prompt, max_tokens=100)
        if response:
            return f"[AI generated] {response.strip()}"
        return ""
    
    def generate_summary_fields(self, paper: Paper) -> Dict[str, str]:
        """生成一句话总结的各个字段"""
        if not self.is_available():
            return {}
        
        # 准备论文信息
        paper_info = f"""
论文标题: {paper.title}
论文分类: {self._get_category_name(paper.category)}
论文摘要: {paper.abstract}
"""
        
        # 生成各个字段
        fields = {}
        
        # 1. 目标/动机
        motivation_prompt = f"""{paper_info}

请总结这篇论文的研究目标或动机（50字以内）："""
        motivation = self._call_api(motivation_prompt, max_tokens=80)
        if motivation:
            fields['summary_motivation'] = f"[AI generated] {motivation.strip()}"
        
        # 2. 创新点
        innovation_prompt = f"""{paper_info}

请总结这篇论文的主要创新点（50字以内）："""
        innovation = self._call_api(innovation_prompt, max_tokens=80)
        if innovation:
            fields['summary_innovation'] = f"[AI generated] {innovation.strip()}"
        
        # 3. 方法精炼
        method_prompt = f"""{paper_info}

请精炼总结这篇论文的核心方法（50字以内）："""
        method = self._call_api(method_prompt, max_tokens=80)
        if method:
            fields['summary_method'] = f"[AI generated] {method.strip()}"
        
        # 4. 简要结论
        conclusion_prompt = f"""{paper_info}

请总结这篇论文的主要结论或成果（50字以内）："""
        conclusion = self._call_api(conclusion_prompt, max_tokens=80)
        if conclusion:
            fields['summary_conclusion'] = f"[AI generated] {conclusion.strip()}"
        
        # 5. 重要局限/展望
        limitation_prompt = f"""{paper_info}

请指出这篇论文的重要局限性或未来工作展望（50字以内）："""
        limitation = self._call_api(limitation_prompt, max_tokens=80)
        if limitation:
            fields['summary_limitation'] = f"[AI generated] {limitation.strip()}"
        
        return fields
    
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
        
        # 1. 生成标题翻译（如果为空）
        if not enhanced_paper.title_translation or enhanced_paper.title_translation.startswith("[AI generated]"):
            translation = self.generate_title_translation(enhanced_paper.title, enhanced_paper.abstract)
            if translation:
                enhanced_paper.title_translation = translation
        
        # 2. 生成类比总结（如果为空）
        if not enhanced_paper.analogy_summary or enhanced_paper.analogy_summary.startswith("[AI generated]"):
            summary = self.generate_analogy_summary(
                enhanced_paper.title,
                enhanced_paper.abstract,
                enhanced_paper.category
            )
            if summary:
                enhanced_paper.analogy_summary = summary
        
        # 3. 生成一句话总结字段（如果为空）
        summary_fields = self.generate_summary_fields(enhanced_paper)
        for field, value in summary_fields.items():
            current_value = getattr(enhanced_paper, field, "")
            if not current_value or current_value.startswith("[AI generated]"):
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