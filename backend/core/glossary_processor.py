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
        # Try to find frequency column
        freq_col = None
        for col in original_cols:
            if "次数" in str(col) or "freq" in str(col).lower() or "count" in str(col).lower():
                freq_col = col
                break

        rename_map = {original_cols[0]: 'src', original_cols[1]: 'dst'}
        if freq_col:
            rename_map[freq_col] = 'frequency'

        glossary_df = glossary_df.rename(columns=rename_map)

        # Ensure src and dst are strings
        glossary_df['src'] = glossary_df['src'].fillna('').astype(str)
        glossary_df['dst'] = glossary_df['dst'].fillna('').astype(str)

        # Normalize frequency
        if 'frequency' in glossary_df.columns:
            glossary_df['frequency'] = pd.to_numeric(glossary_df['frequency'], errors='coerce').fillna(1).astype(int)
        else:
            glossary_df['frequency'] = 1

        content = ""
        encodings_to_try = ['utf-8', 'utf-8-sig', 'utf-16', 'cp949', 'gbk']

        for enc in encodings_to_try:
            try:
                with open(reference_path, 'r', encoding=enc) as f:
                    content = f.read().replace('\r\n', '\n').replace('\r', '\n')
                break # Success
            except UnicodeDecodeError:
                continue

        if not content:
             # Final attempt with errors='ignore' if strictly needed, or just raise
             # But usually one of the above works. If all fail, let's try one last time with ignore or let the error bubble up from a specific attempt?
             # Better to fail loudly if we can't read at all, but let's try to be helpful.
             # If completely empty or failed all, we might want to raise.
             # Let's assume if content is still empty and file is not empty, it failed.
             # Actually, if the file is truly empty, content is empty string.
             # We should check if we successfully read it.
             pass

        if not content and os.path.getsize(reference_path) > 0:
             # Attempt with errors='replace' as last resort
             with open(reference_path, 'r', encoding='utf-8', errors='replace') as f:
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

    def process_batch(self, batch_df, novel_background, reference_dict, term_history=None, log_callback=None):
        batch_list = []
        character_keywords = ['角色', '神祇/传说人物', '男性角色', '女性角色']

        for _, row in batch_df.iterrows():
            korean_term = row['src'].strip()
            frequency = row.get('frequency', 1)

            # 1. Tier Calculation
            tier = "B"
            instruction = ""
            is_lore = korean_term in novel_background

            if is_lore:
                tier = "S"
                instruction = "【核心设定词】出现在背景设定中。必须严格保持一致，绝对禁止删除。"
            elif frequency >= 5:
                tier = "A"
                instruction = "【高频词】出现在原文多次。通常是重要术语，但若是被错误提取的通用常用词（如纯字母、数字、单字、虚词、动词、形容词、副词、介词、连词、助词、感叹词、数词、量词、代词、冠词、语气词等），请务必标记删除。"
            elif frequency <= 3:
                tier = "C"
                instruction = "【低频词】仅出现1-3次。若判断为通用词汇（非术语，如纯字母、数字、单字、虚词、动词、形容词、副词、介词、连词、助词、感叹词、数词、量词、代词、冠词、语气词等），请大胆建议删除。"

            # 2. History Injection
            history_context = None
            if term_history and korean_term in term_history:
                past_results = term_history[korean_term]
                if past_results:
                    last = past_results[-1]
                    if not last.get('should_delete'):
                        history_context = f"之前已审定为: {last.get('recommended_translation')}"
                    else:
                        history_context = "之前已建议删除"

            batch_list.append({
                "korean_term": korean_term,
                "chinese_translation": row['dst'].strip(),
                "tier": tier,
                "instruction": instruction,
                "history_context": history_context,
                "is_character": any(keyword in str(row.get('info', '')) for keyword in character_keywords),
                "current_category": str(row.get('info', '')).strip(),
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
请根据「小说背景设定」、「权重等级」、「历史记忆」与每个术语各自的「术语所在原文参考」，逐条、独立判断下列术语是否存在翻译问题。
权重分级与记忆规则 (Tier & Memory):
你收到的数据中包含了 `tier` (S/A/B/C) 和 `instruction` 字段，以及可选的 `history_context`。
1. **记忆优先 (History Priority)**: 如果 `history_context` 存在（例如"之前已审定为: XX"），这意味着在之前的校对中已经达成了结论。若无致命错误，请**务必与历史结论保持一致**，以确保第一章和第一百章的术语统一。
2. **等级策略 (Tier Strategy)**:
    - **Tier S (Lore)**: 绝对权威。必须与设定集严格匹配。
    - **Tier A (High Freq)**: 高频出现。通常为重要名词。但若确认为被错误提取的通用常用词（如单字、连词），**请务必标记删除**。
    - **Tier C (Low Freq)**: 能够容忍删除。如果看起来像普通动词、形容词或无意义短语，**请大胆标记为删除 (should_delete=true)**。

小说背景设定:
{novel_background}

请严格按照我给出的 JSON 格式返回一个包含所有术语审查结果的 JSON 列表。列表的顺序必须与输入列表的顺序完全一致。

下面是一个处理范例：
---
[范例输入]
[
  {{ "korean_term": "침대 시트", "chinese_translation": "床单", "tier": "C", "instruction": "【低频词】...", "is_character": false, "context": "그는 침대 시트를 갈았다. (他换了床单。)" }},
  {{ "korean_term": "현재웅", "chinese_translation": "玄在雄", "tier": "A", "instruction": "【高频词】...", "history_context": "之前已审定为: 玄在雄", "is_character": true, "context": "현재웅은 말했다. (玄在雄说道。)" }}
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

    def test_single_term(self, term, translation, context, custom_prompt=None, novel_background=""):
        # Construct a single term batch item with "Test" tier
        batch_list = [{
            "korean_term": term,
            "chinese_translation": translation,
            "tier": "B (Test)",
            "instruction": "【测试模式】请根据提供的上下文和设定进行判定。",
            "history_context": None,
            "is_character": False,
            "context": context if context else "无上下文"
        }]

        # Use custom prompt if provided, else standard logic (but we need to handle the template)
        # However, _get_batch_prompt expects config prompt.
        # If custom_prompt is passed (e.g. from UI textarea), we should use it as the 'user_prompt' part.

        # We need a slightly modified version of _get_batch_prompt that accepts an override
        # Or we temporarily patch config (not thread safe)
        # Better: Refactor _get_batch_prompt to accept optional base_prompt override

        full_prompt = self._get_batch_prompt(novel_background, batch_list, base_prompt_override=custom_prompt)

        # Call API
        response = self.ai_service.call_api(full_prompt)
        parsed = self._parse_json_response(response)

        if parsed and isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]
        return {"error": "Failed to parse AI response", "raw": response}

    def _get_batch_prompt(self, novel_background, batch_list, base_prompt_override=None):
        if base_prompt_override:
            user_prompt = base_prompt_override
        else:
            user_prompt = self.config.get("prompts", {}).get("batch_review", "")
            if not user_prompt:
                 # Fallback default if config is empty
                 user_prompt = """角色：专业小说翻译家（V3·批处理模式）
... (truncated default default for brevity in code, but actually we should keep it or refer to constant)
... For now let's just use what was there or empty string if config missing.
"""
                 # Actually, to avoid code duplication, we assume config is loaded roughly correctly or
                 # we just use the logic from before.
                 pass

        # If user_prompt is still empty (and no override), we need that big default block again?
        # To avoid massive duplication in this edit, I will rely on self.config being valid usually.
        # But for valid refactoring, let's keep the existing logic structure.

        if not user_prompt and not base_prompt_override:
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
请根据「小说背景设定」、「权重等级」、「历史记忆」与每个术语各自的「术语所在原文参考」，逐条、独立判断下列术语是否存在翻译问题。
权重分级与记忆规则 (Tier & Memory):
你收到的数据中包含了 `tier` (S/A/B/C) 和 `instruction` 字段，以及可选的 `history_context`。
1. **记忆优先 (History Priority)**: 如果 `history_context` 存在（例如"之前已审定为: XX"），这意味着在之前的校对中已经达成了结论。若无致命错误，请**务必与历史结论保持一致**，以确保第一章和第一百章的术语统一。
2. **等级策略 (Tier Strategy)**:
    - **Tier S (Lore)**: 绝对权威。必须与设定集严格匹配。
    - **Tier A (High Freq)**: 高频出现。通常为重要名词。但若确认为被错误提取的通用常用词（如单字、连词），**请务必标记删除**。
    - **Tier C (Low Freq)**: 能够容忍删除。如果看起来像普通动词、形容词或无意义短语，**请大胆标记为删除 (should_delete=true)**。
3. **分类审查 (Category Review)**:
    根据术语原文、上下文和小说背景，判断 `current_category`（现有分类）是否准确，并在 `suggested_category` 字段中返回最准确的分类。
    分类体系如下（格式：大类/子类）：
    - `角色` → 男性角色 / 女性角色 / 动物角色 / 历史人物 / 知名人物 / 角色外号 / 昵称 / 小说作者
    - `地点` → 特定地名 / 通用地名
    - `组织机构` → 特定组织 / XX机构
    - `小说设定` → ABO / Nameverse / 哨兵向导 / 猎人能力设定 / 特定世界设定词
    - `能力技能` → 角色技能 / 特定设定技能
    - `物品` → 特定物品 / 通用物品 / 特殊物品
    规则：
    - 若现有分类已准确，将其标准化为大类/子类格式后原样返回（如 `current_category` 是 "男性角色"，则返回 "角色/男性角色"）
    - 若现有分类不准确或可细化，返回更准确的大类/子类
    - 在 `justification` 中同时说明翻译审查和分类审查的理由

小说背景设定:
{novel_background}

请严格按照我给出的 JSON 格式返回一个包含所有术语审查结果的 JSON 列表。列表的顺序必须与输入列表的顺序完全一致。

下面是一个处理范例：
---
[范例输入]
[
  {{ "korean_term": "침대 시트", "chinese_translation": "床单", "tier": "C", "instruction": "【低频词】...", "is_character": false, "current_category": "物品", "context": "그는 침대 시트를 갈았다. (他换了床单。)" }},
  {{ "korean_term": "현재웅", "chinese_translation": "玄在雄", "tier": "A", "instruction": "【高频词】...", "history_context": "之前已审定为: 玄在雄", "is_character": true, "current_category": "男性角色", "context": "현재웅은 말했다. (玄在雄说道。)" }}
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
    "suggested_category": "物品/通用物品",
    "justification": "该术语为通用词（日常词汇），无特殊含义，建议在最终术语表中删除。分类：通用物品。"
  }},
  {{
    "korean_term": "현재웅",
    "original_translation": "玄在雄",
    "recommended_translation": "玄在雄",
    "should_delete": false,
    "deletion_reason": null,
    "judgment_emoji": "✅",
    "suggested_category": "角色/男性角色",
    "justification": "角色名翻译准确，与背景一致。分类确认为男性角色。"
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
    "suggested_category": "[大类/子类，参照上方分类体系]",
    "justification": "[简洁、精确的核心理由，包含翻译审查和分类审查说明]"
  }}
]
"""
        return user_prompt + "\n" + fixed_suffix
