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
        "batch_review": """角色：专业小说翻译家（V3·批处理模式）

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
