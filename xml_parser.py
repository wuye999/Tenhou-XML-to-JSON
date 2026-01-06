# author：madoka
# -*- coding: utf-8 -*-
import xml.etree.ElementTree as ET
import json
import copy
import math
import requests
import os
from loguru import logger
# from logger import logger
from urllib.parse import parse_qs, urlparse, unquote
from typing import Dict, List, Optional, Any

# 引用合并后的单一文件
from tenhou_merged import TenhouBridge, tenhou_to_mjai


# 麻将牌的字符串表示到数字ID的映射
mahjong_to_number: Dict[str, int] = {
    '1m': 11, '2m': 12, '3m': 13, '4m': 14, '5m': 15, '6m': 16, '7m': 17, '8m': 18, '9m': 19,
    '1p': 21, '2p': 22, '3p': 23, '4p': 24, '5p': 25, '6p': 26, '7p': 27, '8p': 28, '9p': 29,
    '1s': 31, '2s': 32, '3s': 33, '4s': 34, '5s': 35, '6s': 36, '7s': 37, '8s': 38, '9s': 39,
    "E": 41,  "S": 42,  "W": 43,  "N": 44,  "P": 45,  "F": 46,  "C": 47, # 字牌：东南西北白发中
    '5mr': 51, '5pr': 52, '5sr': 53, # 赤宝牌
}


# 天凤役种ID到名称的映射
YAKU_MAP: Dict[int, str] = {
    0: "門前清自摸和", 1: "立直", 2: "一発", 3: "槍槓", 4: "嶺上開花", 5: "海底摸月", 6: "河底撈魚", 7: "平和", 8: "断幺九", 9: "一盃口",
    10: "自風 東", 11: "自風 南", 12: "自風 西", 13: "自風 北", 14: "場風 東", 15: "場風 南", 16: "場風 西", 17: "場風 北",
    18: "役牌 白", 19: "役牌 發", 20: "役牌 中", 21: "両立直", 22: "七対子", 23: "混全帯幺九", 24: "一気通貫", 25: "三色同順",
    26: "三色同刻", 27: "三槓子", 28: "対々和", 29: "三暗刻", 30: "小三元", 31: "混老頭", 32: "二盃口", 33: "純全帯幺九", 34: "混一色", 35: "清一色",
    36: "人和", 37: "天和", 38: "地和", 39: "大三元", 40: "四暗刻", 41: "四暗刻単騎", 42: "字一色", 43: "緑一色", 44: "清老頭", 45: "九蓮宝燈",
    46: "純正九蓮宝燈", 47: "国士無双", 48: "国士無双１３面", 49: "大四喜", 50: "小四喜", 51: "四槓子",
    52: "ドラ", 53: "裏ドラ", 54: "赤ドラ"
}

DAN_MAP = [
    "新人", "９級", "８級", "７級", "６級", "５級", "４級", "３級", "２級", "１級",
    "初段", "二段", "三段", "四段", "五段", "六段", "七段", "八段", "九段", "十段", "天鳳"
]

def get_rule_disp(go_type: int) -> str:
    """根据 GO type 解析规则描述字符串。"""
    # 动态解析
    
    # 1. 判定人数 (0x10)
    人数 = "三" if (go_type & 0x10) else ""
    
    # 2. 判定卓等级 (0x20 + 0x80)
    if (go_type & 0x20) and (go_type & 0x80):
        卓 = "鳳"
    elif go_type & 0x20:
        卓 = "特"
    elif go_type & 0x80:
        卓 = "上"
    else:
        卓 = "般"
        
    # 3. 判定局数 (0x08)
    局 = "南" if (go_type & 0x08) else "东"
    
    # 4. 判定速度 (0x40)
    速 = "速" if (go_type & 0x40) else ""
    
    # 5. 判定喰/赤 (0x04 / 0x02 为 1 表示无，0 表示有)
    喰 = "喰" if not (go_type & 0x04) else ""
    赤 = "赤" if not (go_type & 0x02) else ""
    
    return f"{卓}{局}{喰}{赤}{速}"

def _create_agari_description(ten_str: str, yaku_str: Optional[str], yakuman_str: Optional[str], who: int, fromWho: int, oya: int) -> str:
    """根据和牌信息生成描述字符串。"""
    ten = [int(i) for i in ten_str.split(',')]
    fu, score, mangan_level = ten[0], ten[1], ten[2]

    mangan_map = {1: "満貫", 2: "跳満", 3: "倍満", 4: "三倍満"}
    if yakuman_str:
        yakuman_count = len(yakuman_str.split(','))
        if yakuman_count > 1:
            return f"{yakuman_count}倍役満{score}点"
        return f"役満{score}点"
    
    if mangan_level in mangan_map:
        return f"{mangan_map[mangan_level]}{score}点"

    if not yaku_str:
        return f"{fu}符{score}点"

    yaku_list = [int(i) for i in yaku_str.split(',')]
    han = sum(yaku_list[1::2])

    if who != fromWho:  # 荣和
        return f"{fu}符{han}飜{score}点"
    else:  # 自摸
        base_points = fu * (2 ** (han + 2))
        if who == oya:
            payment = math.ceil(base_points * 2 / 100) * 100
            return f"{fu}符{han}飜{payment}点オール"
        else:
            oya_pay = math.ceil(base_points * 2 / 100) * 100
            ko_pay = math.ceil(base_points / 100) * 100
            return f"{fu}符{han}飜{ko_pay}-{oya_pay}点"

# --- mjai 消息处理函数 ---

def _handle_start_kyoku(mjai_message: Dict[str, Any], tenhou_event: Dict[str, Any]) -> List[Any]:
    """处理 `start_kyoku` 消息，初始化一局的数据结构。"""
    tenhou_log = [
        [], # 场次，本场数，场供
        [], # 手牌点数
        [], # 朵拉指示牌
        [], # 里宝牌指示牌
        [], # 玩家0手牌 4
        [], # 玩家0摸牌
        [], # 玩家0打牌 ?
        [], # 玩家1手牌 7
        [], # 玩家1摸牌
        [], # 玩家1打牌 ?
        [], # 玩家2手牌 10 ?
        [], # 玩家2摸牌
        [], # 玩家2打牌
        [], # 玩家3手牌 13 ?
        [], # 玩家3摸牌
        [], # 玩家3打牌
        [], # 和牌信息 16
    ]
    chang = mjai_message["oya"]
    bakaze_map = {"E": 0, "S": 4, "W": 8, "N": 12}
    chang += bakaze_map.get(mjai_message["bakaze"], 0)

    tenhou_log[0] = [chang, mjai_message["honba"], mjai_message["kyotaku"]]
    tenhou_log[1] = mjai_message["scores"]
    tenhou_log[2] = [mahjong_to_number[mjai_message["dora_marker"]]]
    tenhou_log[3] = []  # 里宝牌指示牌，初始为空

    # 初始化四家手牌
    for i in range(4):
        hand_str = tenhou_event.get(f"hai{i}", "")
        hand = [int(s) for s in hand_str.split(',')]
        hand_mjai = tenhou_to_mjai(hand)
        tenhou_log[4 + i * 3] = [mahjong_to_number[hai] for hai in hand_mjai]

    return tenhou_log

def _handle_tsumo(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `tsumo` (摸牌) 消息。"""
    actor = mjai_message["actor"]
    pai_num = mahjong_to_number[mjai_message["pai"]]
    draw_log_indices = {0: 5, 1: 8, 2: 11, 3: 14}
    if actor in draw_log_indices:
        tenhou_log[draw_log_indices[actor]].append(pai_num)

def _handle_dahai(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `dahai` (打牌) 消息。"""
    discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
    draw_log_indices = {0: 5, 1: 8, 2: 11, 3: 14}
    actor = mjai_message["actor"]
    
    # if actor not in discard_log_indices:
    #     return

    discard_idx = discard_log_indices[actor]
    draw_idx = draw_log_indices[actor]
    pai_num = mahjong_to_number[mjai_message["pai"]]
    tsumogiri = mjai_message.get("tsumogiri", False)

    # 如果摸牌记录的最后是鸣牌（字符串），则不是模切
    if tenhou_log[draw_idx] and isinstance(tenhou_log[draw_idx][-1], str):
        tsumogiri = False

    # 处理立直后的打牌
    if tenhou_log[discard_idx] and tenhou_log[discard_idx][-1] == 'r':
        if tsumogiri:
            tenhou_log[discard_idx][-1] += '60'
        else:
            tenhou_log[discard_idx][-1] += str(pai_num)
    elif tenhou_log[discard_idx] and 'r' in str(tenhou_log[discard_idx]):
        tenhou_log[discard_idx].append(60)
    else:
        if tsumogiri:
            tenhou_log[discard_idx].append(60)
        else:
            tenhou_log[discard_idx].append(pai_num)

def _handle_reach(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `reach` (立直) 消息。"""
    actor = mjai_message["actor"]
    discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
    if actor in discard_log_indices:
        tenhou_log[discard_log_indices[actor]].append('r')

def _handle_dora(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `dora` (开宝牌) 消息。"""
    dora_marker = mjai_message["dora_marker"]
    dora_marker_num = mahjong_to_number[dora_marker]
    tenhou_log[2].append(dora_marker_num)

def _handle_pon(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `pon` (碰) 消息。"""
    actor = mjai_message["actor"]
    target = mjai_message["target"]
    pai = mjai_message["pai"]
    consumed = mjai_message["consumed"]

    pai_num = str(mahjong_to_number[pai])
    consumed_nums = [str(mahjong_to_number[c]) for c in consumed]

    relative_pos = (target - actor + 4) % 4
    
    pon_str = ""
    if relative_pos == 3:  # 上家
        pon_str = f"p{pai_num}{consumed_nums[0]}{consumed_nums[1]}"
    elif relative_pos == 2:  # 对家
        pon_str = f"{consumed_nums[0]}p{pai_num}{consumed_nums[1]}"
    elif relative_pos == 1:  # 下家
        pon_str = f"{consumed_nums[0]}{consumed_nums[1]}p{pai_num}"

    if pon_str:
        draw_log_indices = {0: 5, 1: 8, 2: 11, 3: 14}
        if actor in draw_log_indices:
            tenhou_log[draw_log_indices[actor]].append(pon_str)

def _handle_daiminkan(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `daiminkan` (大明杠) 消息。"""
    actor = mjai_message["actor"]
    target = mjai_message["target"]
    pai = mjai_message["pai"]
    consumed = mjai_message["consumed"]

    pai_num = str(mahjong_to_number[pai])
    consumed_nums = [str(mahjong_to_number[c]) for c in consumed]

    relative_pos = (target - actor + 4) % 4
    kan_str = ""
    if relative_pos == 3:  # 上家
        kan_str = f"m{pai_num}{consumed_nums[0]}{consumed_nums[1]}{consumed_nums[2]}"
    elif relative_pos == 2:  # 对家
        kan_str = f"{consumed_nums[0]}m{pai_num}{consumed_nums[1]}{consumed_nums[2]}"
    elif relative_pos == 1:  # 下家
        kan_str = f"{consumed_nums[0]}{consumed_nums[1]}{consumed_nums[2]}m{pai_num}"

    if kan_str:
        draw_log_indices = {0: 5, 1: 8, 2: 11, 3: 14}
        discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
        if actor in draw_log_indices:
            tenhou_log[draw_log_indices[actor]].append(kan_str)
            tenhou_log[discard_log_indices[actor]].append(0)

def _handle_ankan(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `ankan` (暗杠) 消息。"""
    actor = mjai_message["actor"]
    consumed = mjai_message["consumed"]
    
    consumed_nums = [str(mahjong_to_number[c]) for c in consumed]
    ankan_str = f"{consumed_nums[0]}{consumed_nums[1]}{consumed_nums[2]}a{consumed_nums[3]}"

    discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
    if actor in discard_log_indices:
        tenhou_log[discard_log_indices[actor]].append(ankan_str)

def _handle_kakan(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `kakan` (加杠) 消息。"""
    actor = mjai_message["actor"]
    pai = mjai_message["pai"]
    consumed = mjai_message["consumed"]

    pai_num = str(mahjong_to_number[pai])
    consumed_nums = [str(mahjong_to_number[c]) for c in consumed]
    
    all_tiles = consumed_nums + [pai_num]
    kakan_str = f"{all_tiles[0]}{all_tiles[1]}k{all_tiles[2]}{all_tiles[3]}"

    discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
    if actor in discard_log_indices:
        tenhou_log[discard_log_indices[actor]].append(kakan_str)

def _handle_chi(mjai_message: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `chi` (吃) 消息。"""
    actor = mjai_message["actor"]
    pai = mjai_message["pai"]
    consumed = mjai_message["consumed"]

    pai_num = str(mahjong_to_number[pai])
    
    # 为了正确排序，将赤宝牌视为普通牌
    sort_key = lambda n: {51: 15, 52: 25, 53: 35}.get(n, n)
    consumed_nums = sorted([mahjong_to_number[c] for c in consumed], key=sort_key)
    
    consumed_pai1_num = str(consumed_nums[0])
    consumed_pai2_num = str(consumed_nums[1])

    chi_str = f"c{pai_num}{consumed_pai1_num}{consumed_pai2_num}"

    draw_log_indices = {0: 5, 1: 8, 2: 11, 3: 14}
    if actor in draw_log_indices:
        tenhou_log[draw_log_indices[actor]].append(chi_str)

def _handle_agari(tenhou_event: Dict[str, Any], tenhou_log: Optional[List[Any]], tenhou_logs: List[List[Any]]) -> None:
    """处理 `AGARI` (和牌) 事件, 包括一炮多响。"""
    
    active_log = tenhou_log
    is_multi_ron_case = False

    # 一炮多响的启发式判断：当前局日志为空，但存在上一局日志，且上一局以“和了”结束
    if active_log is None:
        if tenhou_logs and tenhou_logs[-1][16] and tenhou_logs[-1][16][0] == "和了":
            active_log = tenhou_logs[-1]
            is_multi_ron_case = True
    
    if active_log is None:
        # 如果仍然没有有效的日志，则忽略此事件（可能发生在文件开头或其他错误情况）
        return

    sc_list = [int(s) for s in tenhou_event['sc'].split(',')]
    score_changes = [sc_list[i] * 100 for i in range(1, 8, 2)]

    who = int(tenhou_event['who'])
    from_who = int(tenhou_event['fromWho'])
    oya = active_log[0][0] % 4

    description = _create_agari_description(
        tenhou_event['ten'],
        tenhou_event.get('yaku'),
        tenhou_event.get('yakuman'),
        who,
        from_who,
        oya
    )

    agari_info = [who, from_who, who, description]

    # 解析并添加役种详情
    yaku_list_str = tenhou_event.get('yaku')
    if yaku_list_str:
        yaku_list = yaku_list_str.split(',')
        for i in range(0, len(yaku_list), 2):
            yaku_id = int(yaku_list[i])
            han = int(yaku_list[i+1])
            yaku_name = YAKU_MAP.get(yaku_id, f"不明な役{yaku_id}")
            agari_info.append(f"{yaku_name}({han}飜)")

    yakuman_list_str = tenhou_event.get('yakuman')
    if yakuman_list_str:
        yakuman_list = yakuman_list_str.split(',')
        for y_id in yakuman_list:
            yaku_id = int(y_id)
            yaku_name = YAKU_MAP.get(yaku_id, f"不明な役満{yaku_id}")
            agari_info.append(yaku_name)

    # 如果是多响情况，或当前日志已记录了和牌信息
    if is_multi_ron_case or (active_log[16] and active_log[16][0] == "和了"):
        # 累加分数变化
        # active_log[16][1] = [x + y for x, y in zip(active_log[16][1], score_changes)]
        # 追加新的和牌者信息
        active_log[16].append(score_changes)
        active_log[16].append(agari_info)
    else:
        # 记录第一次和牌
        active_log[16] = ["和了", score_changes, agari_info]

def _handle_ryuukyoku(tenhou_event: Dict[str, Any], tenhou_log: List[Any]) -> None:
    """处理 `RYUUKYOKU` (流局) 事件。"""
    if tenhou_log is None:
        return

    ryuukyoku_type = tenhou_event.get('type')

    if ryuukyoku_type:
        special_draw_map = {
            'yao9': "九種九牌",
            'kaze4': "四風連打",
            'reach4': "四家立直",
            'ron3': "三家和了",
            'kan4': "四槓散了",
        }
        if ryuukyoku_type == 'nm':  # 流し満貫
            sc_list = [int(s) for s in tenhou_event['sc'].split(',')]
            score_changes = [sc_list[i] * 100 for i in range(1, 8, 2)]
            tenhou_log[16] = ["流し満貫", score_changes]
        elif ryuukyoku_type in special_draw_map:
            tenhou_log[16] = [special_draw_map[ryuukyoku_type]]
        else: # Fallback for other types
            sc_list = [int(s) for s in tenhou_event['sc'].split(',')]
            score_changes = [sc_list[i] * 100 for i in range(1, 8, 2)]
            tenhou_log[16] = ["流局", score_changes]
    else:
        # Normal draw
        tenpai_players = [f'hai{i}' in tenhou_event for i in range(4)]
        num_tenpai = sum(tenpai_players)

        if num_tenpai == 4:
            tenhou_log[16] = ["全員聴牌"]
        elif num_tenpai == 0:
            tenhou_log[16] = ["全員不聴"]
        else:
            sc_list = [int(s) for s in tenhou_event['sc'].split(',')]
            score_changes = [sc_list[i] * 100 for i in range(1, 8, 2)]
            tenhou_log[16] = ["流局", score_changes]


# --- 主解析逻辑 ---

def parse_tenhou_xml_to_mjai(xml_content: str, log_id: str = "") -> Dict[str, Any]:
    """
    将天凤XML牌谱内容解析为Mortal/Akasaka分析器所需的JSON格式。

    Args:
        xml_content (str): 从天凤下载的原始XML字符串。
        log_id (str): 牌谱ID。

    Returns:
        Dict[str, Any]: 包含牌谱标题、名称、规则和详细日志的字典。
    """
    logs: Dict[str, Any] = {
        "ver": 2.3,
        "ref": log_id,
        "ratingc": "PF4",
        "title": ["", ""],
        "name": None,
        "rule": {
            "disp": "",    
            "aka53": 1,
            "aka52": 1,
            "aka51": 1
        },
        "lobby": 0,
        "dan": [],
        "rate": [],
        "sx": [],
        "sc": [],
        "log": None,
    }

    root = ET.fromstring(xml_content)
    
    # 提取全局信息
    last_settlement = None
    for element in root:
        if element.tag == "GO":
            go_type = int(element.attrib.get("type", 0))
            logs["rule"]["disp"] = get_rule_disp(go_type)
            logs["lobby"] = int(element.attrib.get("lobby", 0))
        elif element.tag == "UN":
            logs["name"] = [unquote(element.attrib.get(f"n{i}", "")) for i in range(4)]
            logs["dan"] = [DAN_MAP[int(d)] for d in element.attrib.get("dan", "0,0,0,0").split(",")]
            logs["rate"] = [float(r) for r in element.attrib.get("rate", "0,0,0,0").split(",")]
            logs["sx"] = element.attrib.get("sx", "M,M,M,M").split(",")
        elif element.tag in ["AGARI", "RYUUKYOKU"]:
            last_settlement = element

    if last_settlement is not None and "owari" in last_settlement.attrib:
        owari_data = last_settlement.attrib["owari"].split(",")
        # owari 格式为 [点数0, 变动0, 点数1, 变动1, ...]
        # 目标格式为 [终局点数0*100, 变动0, 终局点数1*100, 变动1, ...]
        sc = []
        for i in range(0, len(owari_data), 2):
            sc.append(int(owari_data[i]) * 100)
            sc.append(float(owari_data[i+1]))
        logs["sc"] = sc

    bridge = TenhouBridge()

    tenhou_logs: List[List[Any]] = []
    tenhou_log: Optional[List[Any]] = None

    # 消息类型到处理函数的分发字典
    message_handlers = {
        "tsumo": _handle_tsumo,
        "dahai": _handle_dahai,
        "reach": _handle_reach,
        "dora": _handle_dora,
        "pon": _handle_pon,
        "daiminkan": _handle_daiminkan,
        "ankan": _handle_ankan,
        "kakan": _handle_kakan,
        "chi": _handle_chi,
    }

    for element in root:
        tag = element.tag
        attributes = element.attrib
        tenhou_event = {"tag": tag, **attributes}

        if tag == "INIT":
            tenhou_event["hai"] = copy.deepcopy(tenhou_event.get(f"hai0", ""))

        if tag == "UN":
            logs["name"] = [unquote(tenhou_event.get(f"n{i}", f'玩家{i}')) for i in range(4)]

        if tag == "AGARI":
            _handle_agari(tenhou_event, tenhou_log, tenhou_logs)

        if tag == "RYUUKYOKU":
            _handle_ryuukyoku(tenhou_event, tenhou_log)

        json_event_bytes = json.dumps(tenhou_event).encode('utf-8')
        mjai_messages = bridge.parse(json_event_bytes)
        
        # 调试日志，输出 tenhou_event 和 mjai_messages
        # logger.debug(f"tenhou_event: {tenhou_event}")
        # logger.debug(f"mjai_messages: {mjai_messages}")

        if not mjai_messages:
            continue
        
        mjai_messages = copy.deepcopy(mjai_messages)
        for mjai_message in mjai_messages:
            if not mjai_message:
                continue

            msg_type = mjai_message.get("type")

            if msg_type == "start_kyoku":
                tenhou_log = _handle_start_kyoku(mjai_message, tenhou_event)
            elif msg_type in message_handlers and tenhou_log is not None:
                handler = message_handlers[msg_type]
                handler(mjai_message, tenhou_log)
            elif msg_type in ["end_kyoku", "end_game", "ryukyoku"] and tenhou_log is not None:
                if tenhou_log:
                    tenhou_logs.append(tenhou_log)
                    tenhou_log = None  # 重置当前局日志

    logs['log'] = tenhou_logs
    return logs

# --- 网络与文件处理 ---

def save_split_rounds(logs: Dict[str, Any], folder_path: str) -> None:
    """将整个牌谱拆分为各个小局并保存。"""
    kaze_names = ["东", "南", "西", "北"]
    
    for log_entry in logs['log']:
        round_index = log_entry[0][0]
        honba_index = log_entry[0][1]
        
        kaze_idx = round_index // 4
        kyoku_idx = (round_index % 4) + 1
        
        # 生成文件名：例如 "东1局" 或 "东1局1本场"
        filename = f"{kaze_names[kaze_idx]}{kyoku_idx}局"
        if honba_index > 0:
            filename += f"{honba_index}本场"
        
        round_data = {
            "title": logs["title"],
            "name": logs["name"],
            "rule": logs["rule"],
            "log": [log_entry]
        }
        
        file_path = os.path.join(folder_path, f"{filename}.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(round_data, f, ensure_ascii=False, separators=(',', ':'))
        except IOError as e:
            print(f"保存小局 {filename} 失败: {e}")

def extract_log_id(url: str) -> Optional[str]:
    """从天凤URL中提取牌谱ID。"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return params.get('log', [None])[0]

def build_download_url(original_url: str) -> Optional[str]:
    """构建用于下载牌谱的直接URL。"""
    log_id = extract_log_id(original_url)
    if not log_id:
        return None
    return f"https://tenhou.net/0/log/?{log_id}"

def get_headers(referer: str) -> Dict[str, str]:
    """构造请求头，模拟浏览器行为。"""
    return {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'zh-CN,zh;q=0.9,zh-HK;q=0.8,zh-TW;q=0.7',
        'Connection': 'keep-alive',
        'Host': 'tenhou.net',
        'Referer': referer,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0',
        'sec-ch-ua': '"Not(A:Brand";v="99", "Microsoft Edge";v="133", "Chromium";v="133"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

def download_paipu_data(original_url: str) -> Optional[str]:
    """下载指定URL的牌谱XML数据。"""
    download_url = build_download_url(original_url)
    if not download_url:
        print(f"无效URL: {original_url}")
        return None

    try:
        response = requests.get(
            download_url,
            headers=get_headers(original_url),
            timeout=10
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"下载失败 {original_url}: {str(e)}")
        return None

# --- 主程序入口 ---

def save_split_rounds(logs: Dict[str, Any], folder_path: str) -> None:
    """将整个牌谱拆分为各个小局并保存。"""
    kaze_names = ["东", "南", "西", "北"]
    
    for log_entry in logs['log']:
        round_index = log_entry[0][0]
        honba_index = log_entry[0][1]
        
        kaze_idx = round_index // 4
        kyoku_idx = (round_index % 4) + 1
        
        # 生成文件名：例如 "东1局" 或 "东1局1本场"
        filename = f"{kaze_names[kaze_idx]}{kyoku_idx}局"
        if honba_index > 0:
            filename += f"{honba_index}本场"
        
        round_data = {
            "title": logs["title"],
            "name": logs["name"],
            "rule": logs["rule"],
            "log": [log_entry]
        }
        
        file_path = os.path.join(folder_path, f"{filename}.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(round_data, f, ensure_ascii=False, separators=(',', ':'))
            # print(f"已保存小局：{filename}")
        except IOError as e:
            print(f"保存小局 {filename} 失败: {e}")

def main() -> None:
    """脚本主函数，处理用户输入、下载、解析和文件保存。"""
    url = input("天凤牌谱URL格式示例：http://tenhou.net/0/?log=2025120632gm-00a9-0000-8f4679af&tw=2\n请输入天凤牌谱URL: ")
    paipu_data = download_paipu_data(url)

    if paipu_data:
        log_id = extract_log_id(url)
        if not log_id:
            print("无法从URL中提取log_id，无法生成文件名。")
            return
            
        logs = parse_tenhou_xml_to_mjai(paipu_data, log_id)
        
        # 创建文件夹
        if not os.path.exists(log_id):
            os.makedirs(log_id)
            print(f"已创建文件夹: {log_id}")

        # 保存完整牌谱
        output_filename = os.path.join(log_id, f"{log_id}.json")

        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, separators=(',', ':'))
            print(f"完整牌谱已保存到 {output_filename}")
            
            # 拆分并保存小局
            save_split_rounds(logs, log_id)
            print(f"所有小局已成功拆分并保存到文件夹 {log_id} 中。")
            
        except IOError as e:
            print(f"写入文件失败: {e}")
    else:
        print("未找到有效的牌谱数据，请检查URL是否正确。")
    input("按任意键退出...")




if __name__ == "__main__":
    main()
