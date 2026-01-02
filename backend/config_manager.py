import json
import os

import sys

# Determine config path based on whether we are frozen (packaged) or not
if getattr(sys, 'frozen', False):
    # In a frozen app, the config should be next to the executable
    CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), 'cfg.json')
else:
    # In dev, it's relative to this file
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cfg.json')

DEFAULT_CONFIG = {
    "api_key": "YOUR-API-KEY",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "MAX_WORKERS": 10,
    "BATCH_SIZE": 10,
    "default_directory": os.path.join(os.path.expanduser('~'), 'Downloads'),
    "prompts": {
        "batch_review": """角色：专业小说翻译家 (V3 - 批处理模式)

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
    }
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Ensure prompts exist in config even if loading old version
            if "prompts" not in config:
                config["prompts"] = DEFAULT_CONFIG["prompts"]
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
