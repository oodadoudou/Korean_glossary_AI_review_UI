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
        
        reference_dict = {}
        
        # Strategy 1: Try parsing with "原文：" markers
        if '原文：' in content:
            blocks = content.split('原文：')[1:]
            for block in blocks:
                match = re.search(r'^(?P<korean_term>.*?)\n.*?(?P<context>.*)', block, re.DOTALL)
                if match:
                    korean_term = match.group('korean_term').strip()
                    ctx = match.group('context').strip().replace("※", "")
                    reference_dict[korean_term] = ctx

        # Strategy 2: Fallback to Raw Text Search if Strategy 1 found nothing or very few
        # (Or we can just do this for any missing term later, but pre-building is better for performance if possible)
        # Let's do a hybrid approach: Pre-build if markers exist, otherwise strict search on demand (or pre-build for all terms now)
        
        if not reference_dict:
            # Treat as raw novel text
            # For each term in glossary, find it in content
            lines = content.split('\n')
            for term in glossary_df['src'].unique():
                term = term.strip()
                if not term: continue
                
                # Simple search: find first occurrence of term and extract surrounding lines
                # To be more robust, we could find the line with the term
                found_ctx = []
                for i, line in enumerate(lines):
                    if term in line:
                        # Extract this line and maybe previous/next for context
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        ctx_block = "\n".join(lines[start:end]).strip()
                        found_ctx.append(ctx_block)
                        if len(found_ctx) >= 1: break # Just take the first meaningful occurrence
                
                if found_ctx:
                    reference_dict[term] = found_ctx[0]
        
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
             user_prompt = """角色：专业小说翻译家（V3·批处理模式）

身份与使命
你是一位顶级的韩中翻译复审专家。
你的任务是接收一批术语，并对其中的每一条进行独立、精确且基于上下文的一致性审查。

核心行为准则（强化版）
绝对忠于「小说背景设定」与「术语所在原文参考」，这是所有判断的最高依据。
专有名词（尤其是人名）的一致性优先级高于字面翻译准确性。
只要该译名在小说中已形成稳定对应关系，不得因缩写、昵称或形态变化而随意修改。
允许并必须识别"同一角色的不同指代形式"（全名/省略名/昵称），并确保其中文译名在规则下保持统一逻辑。
对普通词汇，执行"精简原则"：
删除不必要的通用词、动词、形容词和描述性短语，仅保留具备术语价值的核心名词。

人名一致性专项规则：
已确立的人名映射关系视为"强绑定规则"，不可拆分或混用：
例如：이해든 → 李海灯（角色全名），해든 → 海灯（同一角色的省略名/称呼）
若原文中出现：
全名形式 → 必须使用对应的完整中文名
省略/称呼形式 → 必须使用与之匹配的省略中文名
禁止以下错误行为：
例如：将 이해든 译为「海灯」，将 해든 译为「李海灯」
同一角色的不同名称形式（全名/省略名/昵称）视为"同一人名术语组"，
该术语组中的所有条目 必须共享完全一致的角色属性，包括但不限于：
性别（男性/女性）
角色身份
叙事立场
性别一致性强制规则：
一旦某角色在任一名称形式中被明确判定为男性或女性角色，
该性别属性必须自动继承至该角色的所有其他名称形式。
禁止将同一角色的不同名称形式判定为：
"一个有性别，一个未定义"
"一个男性，一个性别不明"
"一个男性，一个女性"
在同一小说中对同一角色使用多个不成体系的中文名
若术语为人名：
必须判断其是否为已出现角色或其变体指代
若为同一角色的不同写法，应标记为"一致性正确，不修改"
不得因"非全名""看似通用"而建议删除

组织一致性专项规则：
组织、机构、团体、势力、公司、学校、帮派等，均视为专有名词，其一致性规则等同于人名。
一旦某组织的中译名在小说中被确立，即视为"强绑定组织译名"，后续出现不得随意改写、简化或替换同义表达。
需主动识别以下情况，并强制保持一致：
全称 ↔ 简称
正式名称 ↔ 内部称呼/俗称
原文中因语境省略部分词素的组织指代形式
禁止以下行为：
同一组织在不同章节使用不同中文译名
将已确立译名的组织误判为"通用名词"并建议删除
因字面直译或风格偏好擅自更换已稳定的组织译名
若术语为组织名：
必须判断其是否为已出现组织或其变体指代
若为同一组织的不同写法，应判定为"一致性正确，不修改"
仅在明显翻译错误或违背小说设定时，才允许提出修正建议

任务：批量术语审查
请根据「小说背景设定」与每个术语各自的「术语所在原文参考」，逐条、独立判断下列术语是否存在翻译问题。

审查标准：
是否为多义词、且无法稳定指向具体含义？（建议删除）
翻译是否准确，是否符合小说语境？
是否为无歧义的通用日常词？（建议删除）
是否为形容词、动词或纯描述性短语？（建议删除）
若为角色术语：
是否为人名或其指代形式？
是否与既定人名映射保持一致？
性别、称呼层级是否正确？
若为组织术语：
是否为已确立组织或其变体指代？
是否与既定组织译名保持一致？
若非角色或核心设定相关术语，是否应删除？"""

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
