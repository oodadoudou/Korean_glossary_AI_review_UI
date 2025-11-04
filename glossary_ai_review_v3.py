# -*- coding: utf-8 -*-
import pandas as pd
import openai
import re
import os
import time
import json
import sys
import concurrent.futures
from typing import Dict, Any, Optional, List
import importlib.util
import threading
import random

# --- 依赖库检查 (Dependency Check) ---
def check_dependencies():
    """检查所有必需的库是否已安装。"""
    required_dependencies = {
        'pandas': 'pandas',
        'openai': 'openai',
        'openpyxl': 'openpyxl',
        'tqdm': 'tqdm',
        'xlsxwriter': 'XlsxWriter'
    }
    missing_dependencies = []

    for package_name in required_dependencies.keys():
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            missing_dependencies.append(required_dependencies[package_name])

    if missing_dependencies:
        print("错误：脚本运行缺少必要的 Python 库。")
        print(f"缺失的库: {', '.join(missing_dependencies)}")
        print("\n请复制并运行以下命令来安装它们:")
        print(f"pip install {' '.join(missing_dependencies)}")
        sys.exit(1)
    
    global tqdm
    try:
        from tqdm import tqdm
    except ImportError:
        def tqdm(iterable, *args, **kwargs):
            return iterable

# --- 全局配置变量 ---
CONFIG = {}
rate_limit_pause_event = threading.Event()

# --- 文件路径变量 ---
GLOSSARY_FILE_PATH = None 
REFERENCE_FILE_PATH = None
FINAL_GLOSSARY_FILENAME = 'glossary_output.xlsx'
MODIFICATION_LOG_FILENAME = 'modified.xlsx'
ERROR_LOG_FILENAME = 'error_log.txt'
FINAL_GLOSSARY_OUTPUT_PATH = ''
MODIFICATION_LOG_OUTPUT_PATH = ''
ERROR_LOG_OUTPUT_PATH = ''


# --- AI Prompt 模板 (V3) ---
BATCH_REVIEW_PROMPT_TEMPLATE = """
角色：专业小说翻译家 (V3 - 批处理模式)

身份与使命:
你是一位顶级的韩中翻译复审专家。你的任务是接收一批术语，并对其中的每一条进行独立的、精确的审查。

核心行为准则:
- 绝对忠于“小说背景设定”和“术语所在原文参考”，这是你判断的最高依据。
- 对于专有名词（人名、地名、组织等），你的首要任务是确保其“一致性”，在没有明显错误的情况下不轻易修改。
- 对于普通词汇，你的任务是“精简”，大胆地删除不必要的通用词、动词和描述性短语，只保留核心名词。

小说背景设定:
{novel_background}

任务：批量术语审查
请根据“小说背景设定”和每个术语各自的“术语所在原文参考”，独立判断列表中的每一个术语是否有翻译问题。
审查标准如下：
1. 是否为多义词？（建议删除）
2. 翻译是否准确？
3. 是否为通用词（即没有歧义的日常词汇，如“床单”、“水壶”）？（建议删除）
4. 是否为形容词、动词或描述性短语？（建议删除）
5. 如果是角色术语，人名、性别、一致性是否正确？如果不是角色，是否应删除？

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
{batch_json}

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

CONSISTENCY_CHECK_PROMPT_TEMPLATE = """
角色：韩中翻译复审专家 (V3 - 仲裁模式)

身份与使命:
你是一位顶级的韩中翻译复审专家。你的任务是解决一个具体的翻译不一致问题。

小说背景设定:
{novel_background}

任务：翻译一致性仲裁
对于同一个韩语原文“{korean_term}”，现在存在多种不同的译法。请根据“小说背景设定”和每个译法附带的“术语所在原文参考”，判断哪一个译法是最佳的、应被统一采用的译法。

存在冲突的译法列表:
{conflicts_json}

请严格按照我给出的 JSON 格式返回你的最终裁决。

输出格式 (Output Format):
{{
  "korean_term": "{korean_term}",
  "recommended_translation": "[你裁定的最佳统一译法]"
}}
"""

FUZZY_CONSISTENCY_PROMPT_TEMPLATE = """
角色：韩中翻译复审专家 (V3.2 - 实体关联仲裁模式)

身份与使命:
你是一位顶级的韩中翻译复审专家。你的任务是解决一组可能相关的角色名称的翻译一致性问题。

小说背景设定:
{novel_background}

任务：角色名关联一致性仲裁
以下是一组可能相关的角色术语（例如，全名与简称）。请检查它们的译法是否保持了逻辑上的一致性。
例如，“玄在雄”和“在雄”的翻译应该有关联性。

请严格按照以下思维链进行判断，并返回一个包含所有术语最终推荐译法的 JSON 列表：
1.  **识别核心实体**: 在术语组中，识别出核心的角色实体是什么。
2.  **评估一致性**: 检查当前每个术语的译法是否都与这个核心实体保持了一致。例如，简称的翻译是否是全名翻译的一部分。
3.  **给出最终推荐**: 为列表中的每一个术语，给出一个最终的、保持了一致性的推荐译法。如果某个术语的当前译法已经是最佳的，则推荐译法与当前译法相同。

存在关联冲突的术语组:
{conflicts_json}

最终指令：你的输出必须且只能是一个 JSON 列表，严禁在 JSON 列表之后附加任何形式的解释、标题或说明文字。

输出格式 (Output Format):
[
  {{
    "korean_term": "[输入术语1的原文]",
    "recommended_translation": "[你为术语1裁定的最终译法]"
  }},
  {{
    "korean_term": "[输入术语2的原文]",
    "recommended_translation": "[你为术语2裁定的最终译法]"
  }}
]
"""


# --- 核心功能函数 (Core Functions) ---

def load_config():
    """加载或创建 cfg.json 配置文件。"""
    global CONFIG
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()
        
    config_path = os.path.join(script_dir, 'cfg.json')

    if not os.path.exists(config_path):
        print(f"配置文件 {config_path} 不存在，正在为您创建一个模板...")
        default_config = {
            "api_key": "在此处填入您的API密钥",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-reasoner",
            "MAX_WORKERS": 10,
            "BATCH_SIZE": 10,
            "default_directory": "/Users/doudouda/Downloads/2/"
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        print(f"请在 {config_path} 文件中填入您的 API 密钥后重新运行脚本。")
        return False

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            CONFIG = json.load(f)
        if CONFIG.get("api_key") == "在此处填入您的API密钥":
            print(f"错误：请先在 {config_path} 文件中填入您的 API 密钥。")
            return False
        return True
    except (json.JSONDecodeError, Exception) as e:
        print(f"读取配置文件时发生错误: {e}")
        return False

def find_input_files(directory: str):
    """在指定目录查找术语表 (.xlsx) 和参考文件 (.txt)。"""
    global GLOSSARY_FILE_PATH, REFERENCE_FILE_PATH
    excluded_files = [FINAL_GLOSSARY_FILENAME, MODIFICATION_LOG_FILENAME]
    
    xlsx_files = []
    for file in os.listdir(directory):
        if file.endswith('.xlsx') and not file.startswith('~') and file not in excluded_files:
            xlsx_files.append(file)
        elif file.endswith('.txt'):
            REFERENCE_FILE_PATH = os.path.join(directory, file)
    
    if not xlsx_files:
        raise FileNotFoundError(f"错误：在目录 '{directory}' 中未找到源 .xlsx 术语表文件。")
    if len(xlsx_files) > 1:
        print(f"警告：在目录 '{directory}' 中找到多个 .xlsx 文件，将使用第一个文件: {xlsx_files[0]}")
    
    GLOSSARY_FILE_PATH = os.path.join(directory, xlsx_files[0])
    
    if not REFERENCE_FILE_PATH:
        raise FileNotFoundError(f"错误：在目录 '{directory}' 中未找到 .txt 参考文件。")
    
    print(f"找到术语表文件: {GLOSSARY_FILE_PATH}")
    print(f"找到参考文件: {REFERENCE_FILE_PATH}")


def load_data(glossary_path: str, reference_path: str) -> (pd.DataFrame, Dict[str, str], pd.Series, List[str]):
    """从术语表和参考文件中加载数据，并保留原始数据类型和列名。"""
    print("正在加载文件...")
    glossary_df_orig = pd.read_excel(glossary_path, engine='openpyxl')
    original_dtypes = glossary_df_orig.dtypes
    original_cols = glossary_df_orig.columns.tolist()

    if len(original_cols) < 2:
        raise ValueError("术语表 Excel 文件必须至少包含两列（原文和译文）。")
    rename_map = {original_cols[0]: 'src', original_cols[1]: 'dst'}
    glossary_df_renamed = glossary_df_orig.rename(columns=rename_map)
    
    glossary_df = glossary_df_renamed.fillna('').astype(str)
    print(f"成功加载术语表，共 {len(glossary_df)} 条。")

    with open(reference_path, 'r', encoding='utf-8') as f:
        content = f.read().replace('\r\n', '\n').replace('\r', '\n')
    
    blocks = content.split('原文：')[1:]
    reference_dict = {}
    for i, block in enumerate(blocks):
        match = re.search(
            r'^(?P<korean_term>.*?)\n译文：.*?\n备注：.*?\n出现次数：.*?\n参考文本：.*?\n(?P<context>.*)',
            block,
            re.DOTALL
        )
        if match:
            data = match.groupdict()
            korean_term = data['korean_term'].strip()
            context = data['context'].strip().replace("※", "")
            reference_dict[korean_term] = context
        else:
            match_alt = re.search(r'^(?P<korean_term>.*?)\n参考文本：.*\n(?P<context>.*)', block, re.DOTALL)
            if match_alt:
                data = match_alt.groupdict()
                korean_term = data['korean_term'].strip()
                context = data['context'].strip().replace("※", "")
                reference_dict[korean_term] = context

    print(f"成功解析参考文件，共 {len(reference_dict)} 个术语的上下文。")
    return glossary_df, reference_dict, original_dtypes, original_cols


def call_ai_api(client: openai.OpenAI, prompt: str) -> Optional[str]:
    """通用 API 调用函数，包含自适应节流和重试逻辑。"""
    global rate_limit_pause_event
    max_retries = 3
    base_retry_delay = 5

    if rate_limit_pause_event.is_set():
        print(f"线程 {threading.get_ident()}: 检测到全局暂停，等待...")
        rate_limit_pause_event.wait()

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=CONFIG.get("model", "deepseek-reasoner"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
                temperature=0.1
            )
            return response.choices[0].message.content
        except openai.RateLimitError:
            if not rate_limit_pause_event.is_set():
                print("\n检测到 API 速率限制！触发全局暂停...")
                rate_limit_pause_event.set()
            
            wait_time = (base_retry_delay * (2 ** attempt)) + random.uniform(0, 1)
            print(f"线程 {threading.get_ident()}: 速率超限，将在 {wait_time:.2f} 秒后重试...")
            time.sleep(wait_time)

            if attempt == max_retries - 1:
                print("最后一个重试线程完成等待，解除全局暂停。")
                rate_limit_pause_event.clear()
        except Exception as e:
            if attempt == max_retries - 1:
                log_error(f"API请求在 {max_retries} 次重试后仍然失败。错误: {e}\nPrompt: {prompt[:500]}...")
                return None
    
    return None


def parse_ai_json_response(response_text: str) -> Optional[Any]:
    """从 AI 的回复中解析 JSON 对象，增加三层防御容错机制。"""
    if not response_text: return None
    
    clean_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
    
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        json_match = re.search(r'(\[.*?\]|\{.*?\})', clean_text, re.DOTALL)
        if json_match:
            extracted_json = json_match.group(1)
            try:
                return json.loads(extracted_json)
            except json.JSONDecodeError:
                pass 
        
        if clean_text.startswith('[') and not clean_text.endswith(']'):
            last_brace_pos = clean_text.rfind('}')
            if last_brace_pos != -1:
                fixed_text = clean_text[:last_brace_pos+1] + ']'
                try:
                    return json.loads(fixed_text)
                except json.JSONDecodeError as e:
                    log_error(f"JSON修复后解析仍然失败。错误: {e}\n修复尝试: {fixed_text}")
                    return None
        
        log_error(f"JSON解析在所有防御层均失败。\n原始文本: {response_text}")
        return None
    except Exception as e:
        log_error(f"解析 AI 回复时发生未知错误: {e}")
        return None

def process_batch(args: tuple) -> Optional[List[dict]]:
    """处理一批术语的函数，用于多线程。"""
    batch_df, novel_background, reference_dict, client = args
    
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
    
    prompt = BATCH_REVIEW_PROMPT_TEMPLATE.format(
        novel_background=novel_background,
        batch_json=json.dumps(batch_list, ensure_ascii=False, indent=2)
    )
    
    ai_response_text = call_ai_api(client, prompt)
    return parse_ai_json_response(ai_response_text)


def get_multiline_input(prompt_message: str) -> str:
    """获取用户多行输入。"""
    print(prompt_message)
    lines = []
    while True:
        try:
            line = input()
            if not line:
                break
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines)

def log_error(message: str):
    """将错误信息记录到 error_log.txt。"""
    with open(ERROR_LOG_OUTPUT_PATH, 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n\n")

def save_results(final_df, log_df, original_dtypes, original_cols):
    """保存最终结果到 Excel 文件，并添加筛选功能。"""
    print("\n正在保存结果...")
    
    rename_map_reverse = {'src': original_cols[0], 'dst': original_cols[1]}
    final_df_to_save = final_df.rename(columns=rename_map_reverse)

    # 恢复原始数据类型，同时修复空列被填充为 0 的问题
    for col, dtype in original_dtypes.items():
        if col in final_df_to_save.columns:
            try:
                # 检查原始数据类型是否为数字（整数或浮点数）
                if 'int' in str(dtype) or 'float' in str(dtype):
                    # 将列转换为数字，无法转换的值（如空字符串）会变成 NaN
                    numeric_col = pd.to_numeric(final_df_to_save[col], errors='coerce')
                    
                    # --- BUG FIX START ---
                    # 如果原始类型是浮点数，则保留 NaN（在 Excel 中显示为空单元格）
                    # 这可以防止像 'regex' 这样完全为空的列被错误地填充为 0
                    if 'float' in str(dtype):
                        final_df_to_save[col] = numeric_col
                    # 如果原始类型是整数，则将 NaN 填充为 0 并转换为整数，以保持原有的行为
                    elif 'int' in str(dtype):
                        final_df_to_save[col] = numeric_col.fillna(0).astype(int)
                    # --- BUG FIX END ---
                else:
                    # 对于非数字类型，直接转换回原始类型
                    final_df_to_save[col] = final_df_to_save[col].astype(dtype)
            except (ValueError, TypeError):
                # 如果类型转换失败，则忽略并保持原样
                pass

    try:
        with pd.ExcelWriter(FINAL_GLOSSARY_OUTPUT_PATH, engine='xlsxwriter') as writer:
            final_df_to_save.to_excel(writer, index=False, sheet_name='Sheet1')
            worksheet = writer.sheets['Sheet1']
            (max_row, max_col) = final_df_to_save.shape
            worksheet.autofilter(0, 0, max_row, max_col - 1)
        print(f"成功保存最终术语表到: {FINAL_GLOSSARY_OUTPUT_PATH}")
        
        if not log_df.empty:
            if 'count' in log_df.columns:
                log_df['count'] = pd.to_numeric(log_df['count'], errors='coerce').fillna(0).astype(int)

            with pd.ExcelWriter(MODIFICATION_LOG_OUTPUT_PATH, engine='xlsxwriter') as writer:
                log_df.to_excel(writer, index=False, sheet_name='Modifications')
                worksheet = writer.sheets['Modifications']
                (max_row, max_col) = log_df.shape
                worksheet.autofilter(0, 0, max_row, max_col - 1)
            print(f"成功保存修改日志到: {MODIFICATION_LOG_OUTPUT_PATH}")
        else:
            print("没有检测到任何修改，未生成修改日志文件。")

    except Exception as e:
        print(f"保存文件时出错: {e}")


def main():
    """主处理函数，负责两阶段审查流程。"""
    if not load_config():
        sys.exit(1)

    default_dir = CONFIG.get("default_directory", "./")
    directory_path = input(f"请输入文件所在目录 (默认: {default_dir}): ").strip()
    if not directory_path:
        directory_path = default_dir
    
    novel_background = get_multiline_input("请输入小说背景设定 (输入空行并回车以结束): ")
    if not novel_background:
        novel_background = "无特定背景设定。"

    global FINAL_GLOSSARY_OUTPUT_PATH, MODIFICATION_LOG_OUTPUT_PATH, ERROR_LOG_OUTPUT_PATH
    FINAL_GLOSSARY_OUTPUT_PATH = os.path.join(directory_path, FINAL_GLOSSARY_FILENAME)
    MODIFICATION_LOG_OUTPUT_PATH = os.path.join(directory_path, MODIFICATION_LOG_FILENAME)
    ERROR_LOG_OUTPUT_PATH = os.path.join(directory_path, ERROR_LOG_FILENAME)

    try:
        find_input_files(directory_path)
        glossary_df, reference_dict, original_dtypes, original_cols = load_data(GLOSSARY_FILE_PATH, REFERENCE_FILE_PATH)
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return

    client = openai.OpenAI(api_key=CONFIG["api_key"], base_url=CONFIG["base_url"])
    
    # --- 初始化变量 ---
    processed_rows = []
    modification_log = []
    final_df = pd.DataFrame()

    # --- 核心修正: 将整个处理流程包裹在 try...except 中 ---
    try:
        # --- 断点续传逻辑 ---
        if os.path.exists(MODIFICATION_LOG_OUTPUT_PATH):
            print(f"检测到已存在的日志文件 '{MODIFICATION_LOG_OUTPUT_PATH}'，将在此基础上继续。")
            log_df_existing = pd.read_excel(MODIFICATION_LOG_OUTPUT_PATH)
            modification_log = log_df_existing.to_dict('records')
            
            processed_src_terms = set(log_df_existing['术语原文'].unique())
            
            processed_df = glossary_df[glossary_df['src'].isin(processed_src_terms)].copy()
            terms_to_process_df = glossary_df[~glossary_df['src'].isin(processed_src_terms)].copy()
            
            for log_entry in modification_log:
                if log_entry['审查阶段'] == '逐条审查':
                    term_src = log_entry['术语原文']
                    action = log_entry['操作']
                    if action == '修改':
                        processed_df.loc[processed_df['src'] == term_src, 'dst'] = log_entry['新译文']
                    elif action == '删除':
                        processed_df = processed_df[processed_df['src'] != term_src]

            processed_rows = processed_df.to_dict('records')
            print(f"已处理 {len(processed_src_terms)} 个术语，剩余 {len(terms_to_process_df)} 个待处理。")
        else:
            terms_to_process_df = glossary_df.copy()

        # --- 阶段一：批量审查 (并行处理) ---
        if not terms_to_process_df.empty:
            print("\n" + "="*20 + " 阶段一：开始批量审查 " + "="*20)
            
            batch_size = CONFIG.get("BATCH_SIZE", 10)
            batches = [terms_to_process_df.iloc[i:i + batch_size] for i in range(0, len(terms_to_process_df), batch_size)]
            tasks = [(batch, novel_background, reference_dict, client) for batch in batches]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG.get("MAX_WORKERS", 10)) as executor:
                future_to_batch = {executor.submit(process_batch, task): task for task in tasks}
                for future in tqdm(concurrent.futures.as_completed(future_to_batch), total=len(tasks), desc="阶段一审查进度"):
                    batch_results = future.result()
                    original_batch_df = future_to_batch[future][0]

                    if batch_results and len(batch_results) == len(original_batch_df):
                        for i, ai_result in enumerate(batch_results):
                            original_row_dict = original_batch_df.iloc[i].to_dict()
                            row_series = pd.Series(original_row_dict)
                            current_row_for_next_phase = original_row_dict.copy()
                            
                            log_entry_base = {'术语原文': row_series['src'], '原译文': row_series['dst'], 'info': row_series.get('info', ''), 'count': row_series.get('count', '')}

                            if ai_result.get('should_delete'):
                                modification_log.append({**log_entry_base, '审查阶段': '逐条审查', '操作': '删除', '新译文': '', '判断结果': ai_result.get('judgment_emoji'), '判断依据': f"{ai_result.get('deletion_reason')}: {ai_result.get('justification')}"})
                                continue
                            
                            recommended_dst = ai_result.get('recommended_translation', '').strip()
                            if recommended_dst and recommended_dst != row_series['dst'].strip():
                                modification_log.append({**log_entry_base, '审查阶段': '逐条审查', '操作': '修改', '新译文': recommended_dst, '判断结果': ai_result.get('judgment_emoji'), '判断依据': ai_result.get('justification')})
                                current_row_for_next_phase['dst'] = recommended_dst
                            else:
                                modification_log.append({**log_entry_base, '审查阶段': '逐条审查', '操作': '保留', '新译文': row_series['dst'], '判断结果': ai_result.get('judgment_emoji'), '判断依据': ai_result.get('justification')})
                            processed_rows.append(current_row_for_next_phase)
                    else:
                        log_error(f"批处理失败或返回结果数量不匹配。批次原文: {[row['src'] for _, row in original_batch_df.iterrows()]}")
                        for _, row in original_batch_df.iterrows():
                            log_entry_base = {'术语原文': row['src'], '原译文': row['dst'], 'info': row.get('info', ''), 'count': row.get('count', '')}
                            modification_log.append({**log_entry_base, '审查阶段': '逐条审查', '操作': '失败', '新译文': row['dst'], '判断结果': '❌', '判断依据': '批处理失败或AI返回格式错误'})
                        processed_rows.extend(original_batch_df.to_dict('records'))

        first_pass_df = pd.DataFrame(processed_rows)

        # --- 阶段二：脚本驱动的一致性终审 ---
        print("\n" + "="*20 + " 阶段二：开始一致性终审 " + "="*20)
        
        final_df = first_pass_df.copy()
        
        # 2a: 完全匹配一致性检查
        duplicates = final_df[final_df.duplicated('src', keep=False)]
        conflicts = duplicates.groupby('src')['dst'].nunique()
        conflict_groups = conflicts[conflicts > 1].index.tolist()

        if conflict_groups:
            print(f"脚本发现 {len(conflict_groups)} 组「完全匹配」翻译不一致的术语，正在请求 AI 仲裁...")
            for term_src in tqdm(conflict_groups, desc="完全匹配仲裁进度"):
                conflict_rows = final_df[final_df['src'] == term_src]
                conflicts_list = [{"translation": row['dst'], "context": reference_dict.get(term_src, "无上下文")} for _, row in conflict_rows.iterrows()]
                prompt = CONSISTENCY_CHECK_PROMPT_TEMPLATE.format(novel_background=novel_background, korean_term=term_src, conflicts_json=json.dumps(conflicts_list, ensure_ascii=False, indent=2))
                decision = parse_ai_json_response(call_ai_api(client, prompt))
                if decision and decision.get('recommended_translation'):
                    recommended_trans = decision['recommended_translation']
                    indices_to_update = final_df[final_df['src'] == term_src].index
                    for idx in indices_to_update:
                        original_trans = final_df.loc[idx, 'dst']
                        if original_trans != recommended_trans:
                            modification_log.append({'审查阶段': '最终校对', '术语原文': term_src, '原译文': original_trans, 'info': final_df.loc[idx, 'info'], 'count': final_df.loc[idx, 'count'],'操作': '修改 (一致性)', '新译文': recommended_trans, '判断结果': '⚠️', '判断依据': f"统一为推荐译法 '{recommended_trans}'"})
                            final_df.loc[idx, 'dst'] = recommended_trans
                else:
                    log_error(f"完全匹配一致性仲裁失败，术语: {term_src}")

        # 2b: 模糊匹配（角色名）一致性检查
        character_keywords = ['角色', '神祇/传说人物', '男性角色', '女性角色']
        char_df = final_df[final_df['info'].str.contains('|'.join(character_keywords), na=False)].copy()
        char_df = char_df.sort_values(by='src', key=lambda x: x.str.len(), ascending=False)
        
        processed_chars = set()
        fuzzy_conflict_groups = []
        for _, row in char_df.iterrows():
            full_name = row['src']
            if full_name in processed_chars:
                continue
            
            related_group = [full_name]
            processed_chars.add(full_name)
            
            for _, other_row in char_df.iterrows():
                short_name = other_row['src']
                if short_name != full_name and short_name in full_name and short_name not in processed_chars:
                    related_group.append(short_name)
                    processed_chars.add(short_name)
            
            if len(related_group) > 1:
                fuzzy_conflict_groups.append(related_group)

        if fuzzy_conflict_groups:
            print(f"脚本发现 {len(fuzzy_conflict_groups)} 组「模糊关联」的角色术语，正在请求 AI 仲裁...")
            for group in tqdm(fuzzy_conflict_groups, desc="模糊关联仲裁进度"):
                group_df = final_df[final_df['src'].isin(group)]
                conflicts_list = [{"korean_term": row['src'], "current_translation": row['dst']} for _, row in group_df.iterrows()]
                prompt = FUZZY_CONSISTENCY_PROMPT_TEMPLATE.format(novel_background=novel_background, conflicts_json=json.dumps(conflicts_list, ensure_ascii=False, indent=2))
                decisions = parse_ai_json_response(call_ai_api(client, prompt))
                
                if isinstance(decisions, list):
                    for decision in decisions:
                        term_to_update = decision.get('korean_term')
                        recommended_trans = decision.get('recommended_translation')
                        if term_to_update and recommended_trans:
                            indices_to_update = final_df[final_df['src'] == term_to_update].index
                            for idx in indices_to_update:
                                original_trans = final_df.loc[idx, 'dst']
                                if original_trans != recommended_trans:
                                    modification_log.append({'审查阶段': '最终校对', '术语原文': term_to_update, '原译文': original_trans, 'info': final_df.loc[idx, 'info'], 'count': final_df.loc[idx, 'count'], '操作': '修改 (模糊一致性)', '新译文': recommended_trans, '判断结果': '⚠️', '判断依据': f"为保持关联一致性，统一为 '{recommended_trans}'"})
                                    final_df.loc[idx, 'dst'] = recommended_trans
                else:
                    log_error(f"模糊关联一致性仲裁失败，术语组: {group}")

        # --- 保存结果 ---
        save_results(final_df, pd.DataFrame(modification_log), original_dtypes, original_cols)
        print("\n处理完成！")

    except KeyboardInterrupt:
        print("\n捕获到中断信号 (Ctrl+C)！正在保存当前进度...")
        # 确保即使在第二阶段中断，也能保存第一阶段的成果
        if 'first_pass_df' in locals():
             final_df_to_save = first_pass_df
        else:
             final_df_to_save = pd.DataFrame(processed_rows)
             
        save_results(final_df_to_save, pd.DataFrame(modification_log), original_dtypes, original_cols)
        sys.exit(0)


# --- 脚本入口 (Script Entry Point) ---
if __name__ == "__main__":
    check_dependencies()
    main()
