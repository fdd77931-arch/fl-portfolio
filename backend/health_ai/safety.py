"""Conservative, local emergency routing before any external request."""
import re
import unicodedata

_PATTERNS = {
    "consciousness": r"叫不醒|不省人事|意识障碍|意识不清|昏迷|失去意识|没有呼吸|停止呼吸|unconscious|not breathing",
    "breathing": r"喘不过气|呼吸不上气|呼吸困难|呼吸不上来|嘴唇发紫|口唇发青|窒息|噎住|can(?:not|'t) breathe",
    "chest": r"胸痛|胸口(?:突然)?(?:疼|痛|压迫|很闷)|胸部压迫|chest pain",
    "stroke": r"疑似卒中|突然中风|口角歪斜|半边脸.{0,5}歪|脸.{0,5}突然歪|(?:左|右)(?:手|臂|胳膊).{0,6}抬不起来|嘴歪|一侧(?:无力|不能动)|说话困难|说不清话|slurred speech",
    "bleeding": r"大量出血|出血不止|(?:流血|出血|血流)止不住|流血不止|severe bleeding",
    "seizure": r"抽搐|持续惊厥|反复惊厥|ongoing seizure",
    "allergy": r"喉咙肿|舌头肿|喉头水肿|anaphylaxis",
    "poisoning": r"疑似中毒|中毒|药物过量|吃了太多药|吞了很多药|overdose",
    "injury": r"严重外伤|严重烧伤|溺水|drowning",
    "self_harm": r"准备跳楼|要跳楼|想自杀|准备自杀|想结束生命",
    "severe_pain": r"突发剧烈|突然.{0,8}(?:剧烈|撕裂|疼得受不了)|雷击样头痛|thunderclap headache",
}


def emergency_signals(question):
    normalized = unicodedata.normalize("NFKC", question).casefold()
    compact = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", normalized)
    return [name for name, pattern in _PATTERNS.items() if re.search(pattern, compact)]
