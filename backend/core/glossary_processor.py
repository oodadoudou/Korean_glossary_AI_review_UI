import pandas as pd
import json
import re
import os
import concurrent.futures
from backend.core.ai_service import AIService
from backend.config_manager import load_config

class GlossaryProcessor:
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
        self.config = load_config()

    def load_data(self, glossary_path, reference_path):
        glossary_df = pd.read_excel(glossary_path, engine='openpyxl')
        original_cols = glossary_df.columns.tolist()
        rename_map = {original_cols[0]: 'src', original_cols[1]: 'dst'}
        glossary_df = glossary_df.rename(columns=rename_map)
        
        # Ensure src and dst are strings, but leave other columns (like count) as is
        glossary_df['src'] = glossary_df['src'].fillna('').astype(str)
        glossary_df['dst'] = glossary_df['dst'].fillna('').astype(str)

        with open(reference_path, 'r', encoding='utf-8') as f:
            content = f.read().replace('\r\n', '\n').replace('\r', '\n')
        
        blocks = content.split('原文：')[1:]
        reference_dict = {}
        for block in blocks:
            match = re.search(r'^(?P<korean_term>.*?)\n.*?(?P<context>.*)', block, re.DOTALL)
            if match:
                korean_term = match.group('korean_term').strip()
                context = match.group('context').strip().replace("※", "")
                reference_dict[korean_term] = context
        
        return glossary_df, reference_dict, original_cols

    def process_batch(self, batch_df, novel_background, reference_dict, log_callback=None):
        batch_list = []
        character_keywords = ['角色', '神祇/传说人物', '男性角色', '女性角色']
        for _, row in batch_df.iterrows():
            korean_term = row['src'].strip()
            batch_list.append({
                "korean_term": korean_term,
                "chinese_translation": row['dst'].strip(),
                "is_character": any(keyword in row.get('info', '') for keyword in character_keywords),
                "context": reference_dict.get(korean_term, f"未在参考文件中找到术语 '{korean_term}' 的上下文。")
            })
        
        prompt = self._get_batch_prompt(novel_background, batch_list)
        response = self.ai_service.call_api(prompt, log_callback=log_callback)
        return self._parse_json_response(response)

    def _get_batch_prompt(self, novel_background, batch_list):
        user_prompt = self.config.get("prompts", {}).get("batch_review", "")
        if not user_prompt:
             # Fallback default if config is empty
             user_prompt = """角色：专业小说翻译家 (V3 - 批处理模式)

身份与使命:
你是一位顶级的韩中翻译复审专家。你的任务是接收一批术语，并对其中的每一条进行独立的、精确的审查。

核心行为准则:
- 绝对忠于“小说背景设定”和“术语所在原文参考”，这是你判断的最高依据。
- 对于专有名词（人名、地名、组织等），你的首要任务是确保其“一致性”，在没有明显错误的情况下不轻易修改。
- 对于普通词汇，你的任务是“精简”，大胆地删除不必要的通用词、动词和描述性短语，只保留核心名词。


任务：批量术语审查
请根据“小说背景设定”和每个术语各自的“术语所在原文参考”，独立判断列表中的每一个术语是否有翻译问题。
审查标准如下：
1. 是否为多义词？（建议删除）
2. 翻译是否准确？
3. 是否为通用词（即没有歧义的日常词汇，如“床单”、“水壶”）？（建议删除）
4. 是否为形容词、动词或描述性短语？（建议删除）
5. 如果是角色术语，人名、性别、一致性是否正确？如果不是角色，是否应删除？"""

        # Fixed part that handles formatting and examples
        fixed_suffix = f"""
小说背景设定:
{novel_background}

请严格按照我给出的 JSON 格式返回一个包含所有术语审查结果的 JSON 列表。列表的顺序必须与输入列表的顺序完全一致。

下面是一个处理范例：
---
[范例输入]
[
  {{ "korean_term": "침대 시트", "chinese_translation": "床单", "is_character": false, "context": "그는 침대 시트를 갈았다. (他换了床单。)" }},
  {{ "korean_term": "현재웅", "chinese_translation": "玄在雄", "is_character": true, "context": "현재웅은 말했다. (玄在雄说道。)" }}
]

[范例输出]
[
  {{
    "korean_term": "침대 시트",
    "original_translation": "床单",
    "recommended_translation": "床单",
    "should_delete": true,
    "deletion_reason": "通用词",
    "judgment_emoji": "🗑️",
    "justification": "该术语为通用词（日常词汇），无特殊含义，建议在最终术语表中删除。"
  }},
  {{
    "korean_term": "현재웅",
    "original_translation": "玄在雄",
    "recommended_translation": "玄在雄",
    "should_delete": false,
    "deletion_reason": null,
    "judgment_emoji": "✅",
    "justification": "角色名翻译准确，与背景一致。"
  }}
]
---

现在，请处理以下术语列表：
{json.dumps(batch_list, ensure_ascii=False, indent=2)}

输出格式 (Output Format):
[
  {{
    "korean_term": "[术语原文]",
    "original_translation": "[原始译文]",
    "recommended_translation": "[你的首选建议]",
    "should_delete": "[true/false]",
    "deletion_reason": "[通用词/动词/形容词/描述性短语/非角色/其他/null]",
    "judgment_emoji": "[✅/⚠️/❌/🗑️]",
    "justification": "[简洁、精确的核心理由]"
  }}
]
"""
        return user_prompt + "\n" + fixed_suffix

    def _parse_json_response(self, response_text):
        if not response_text: return None
        clean_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Simple fallback for list extraction
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
            return None
