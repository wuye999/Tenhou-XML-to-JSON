## author：madoka
import xml.etree.ElementTree as ET
import json
import loguru
from loguru import logger
from bridge import TenhouBridge
from tenhou.utils.converter import (mjai_to_tenhou, mjai_to_tenhou_one,
                                     tenhou_to_mjai, tenhou_to_mjai_one, to_34_array)
import copy
import requests
from urllib.parse import parse_qs, urlparse, unquote

mahjong_to_number = {
            '1m': 11, '2m': 12, '3m': 13, '4m': 14, '5m': 15, '6m': 16, '7m': 17, '8m': 18, '9m': 19,
            '1p': 21, '2p': 22, '3p': 23, '4p': 24, '5p': 25, '6p': 26, '7p': 27, '8p': 28, '9p': 29,
            '1s': 31, '2s': 32, '3s': 33, '4s': 34, '5s': 35, '6s': 36, '7s': 37, '8s': 38, '9s': 39,
            "E": 41,  "S": 42,  "W": 43,  "N": 44,  "P": 45,  "F": 46,  "C": 47,
            '5mr': 51, '5pr': 52, '5sr': 53, 
        }

        
def parse_tenhou_xml_to_mjai(xml_content: str, actor: int = 0) -> list[dict]:
    logs ={
        "title": ["",""],
        "name": None,
        "rule": {"disp": "鳳南喰赤","aka": 1},
        "log": None,
    }
    root = ET.fromstring(xml_content)
    bridge = TenhouBridge()

    mjai_logs = []
    tenhou_logs = []

    for element in root:
        tag = element.tag
        attributes = element.attrib

        tenhou_event = {"tag": tag}
        tenhou_event.update(attributes)

        if tag == "INIT":
            # Combine hai0, hai1, hai2, hai3 into a single 'hai' key
            tenhou_event["hai"] = copy.deepcopy(tenhou_event[f"hai{actor}"])

        if tag == "UN":
            logs["name"] = [unquote(tenhou_event.get("n0", '玩家0')), unquote(tenhou_event.get("n1", '玩家1')), unquote(tenhou_event.get("n2", '玩家2')), unquote(tenhou_event.get("n3", '玩家3'))]

        json_event_bytes = json.dumps(tenhou_event).encode('utf-8')
        logger.info(tenhou_event)
        mjai_messages = bridge.parse( json_event_bytes)
        if not mjai_messages:
                continue
        mjai_messages = copy.deepcopy(mjai_messages)
        for mjai_message in mjai_messages:
            # logger.info(mjai_message)

            if not mjai_message:
                continue

            if mjai_message["type"] == "start_kyoku":
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
                match mjai_message["bakaze"]:
                    case "E":
                        chang = chang 
                    case "S":
                        chang += 4
                    case "W":
                        chang += 8
                    case "N":
                        chang += 12
                tenhou_log[0] = [chang, mjai_message["honba"], mjai_message["kyotaku"]]
                tenhou_log[1] = mjai_message["scores"]
                tenhou_log[2] = [mahjong_to_number[mjai_message["dora_marker"]]]
                tenhou_log[3] = []
                            
                hand = [int(s) for s in tenhou_event[f"hai0"].split(',')]
                hand = tenhou_to_mjai(hand)
                tenhou_log[4] = [mahjong_to_number[hai] for hai in hand]

                hand = [int(s) for s in tenhou_event[f"hai1"].split(',')]
                hand = tenhou_to_mjai(hand)
                tenhou_log[7] = [mahjong_to_number[hai] for hai in hand]

                hand = [int(s) for s in tenhou_event[f"hai2"].split(',')]
                hand = tenhou_to_mjai(hand)
                tenhou_log[10] = [mahjong_to_number[hai] for hai in hand]

                hand = [int(s) for s in tenhou_event[f"hai3"].split(',')]
                hand = tenhou_to_mjai(hand)
                tenhou_log[13] = [mahjong_to_number[hai] for hai in hand]
            
            if mjai_message["type"] == "tsumo":
                match mjai_message["actor"]:
                    case 0:
                        tenhou_log[5].append(mahjong_to_number[mjai_message["pai"]])
                    case 1:
                        tenhou_log[8].append(mahjong_to_number[mjai_message["pai"]])
                    case 2:
                        tenhou_log[11].append(mahjong_to_number[mjai_message["pai"]])
                    case 3:
                        tenhou_log[14].append(mahjong_to_number[mjai_message["pai"]])

            if mjai_message["type"] == "dahai":
                # Map actor to corresponding discard log index
                discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
                draw_log_indices = {0: 5, 1: 8, 2: 11, 3: 14}
                actor = mjai_message["actor"]
                discard_idx = discard_log_indices[actor]
                draw_idx = draw_log_indices[actor]
                pai_num = mahjong_to_number[mjai_message["pai"]]

                # New tsumogiri logic
                # tsumogiri = False
                # if tenhou_log[draw_idx] and tenhou_log[draw_idx][-1] == pai_num:
                #     tsumogiri = True
                tsumogiri = mjai_message.get("tsumogiri", False)

                # Fix IndexError: check if discard list is not empty before accessing last element
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

            if mjai_message["type"] == "reach":
                match mjai_message["actor"]:
                    case 0:
                        tenhou_log[6].append('r')
                    case 1:
                        tenhou_log[9].append('r')
                    case 2:
                        tenhou_log[12].append('r')
                    case 3:
                        tenhou_log[15].append('r')

            if mjai_message["type"] == "reach_accepted":   
                pass         

            if mjai_message["type"] == "dora":
                dora_marker = mjai_message["dora_marker"]
                dora_marker_num = mahjong_to_number[dora_marker]
                tenhou_log[2].append(dora_marker_num)

            if mjai_message["type"] == "pon":
                actor = mjai_message["actor"]
                target = mjai_message["target"]
                pai = mjai_message["pai"]
                pai_num = str(mahjong_to_number[pai])

                # (target - actor + 4) % 4
                # 1: 下家, 2: 対面, 3: 上家
                relative_pos = (target - actor + 4) % 4
                
                pon_str = ""
                if relative_pos == 1: # Shimocha (next player)
                    pon_str = f"{pai_num}{pai_num}p{pai_num}"
                elif relative_pos == 2: # Toimen (opposite player)
                    pon_str = f"{pai_num}p{pai_num}{pai_num}"
                elif relative_pos == 3: # Kamicha (previous player)
                    pon_str = f"p{pai_num}{pai_num}{pai_num}"

                if pon_str:
                    match actor:
                        case 0:
                            tenhou_log[5].append(pon_str)
                        case 1:
                            tenhou_log[8].append(pon_str)
                        case 2:
                            tenhou_log[11].append(pon_str)
                        case 3:
                            tenhou_log[14].append(pon_str)

            if mjai_message["type"] == "kan" or mjai_message["type"] == "daiminkan":
                actor = mjai_message["actor"]
                target = mjai_message["target"]
                pai = mjai_message["pai"]
                pai_num = str(mahjong_to_number[pai])

                relative_pos = (target - actor + 4) % 4
                kan_str = ""
                if relative_pos == 1: # Shimocha (next player)
                    kan_str = f"{pai_num}{pai_num}{pai_num}m{pai_num}"
                elif relative_pos == 2: # Toimen (opposite player)
                    kan_str = f"{pai_num}m{pai_num}{pai_num}{pai_num}"
                elif relative_pos == 3: # Kamicha (previous player)
                    kan_str = f"m{pai_num}{pai_num}{pai_num}{pai_num}"

                if kan_str:
                    match actor:
                        case 0:
                            tenhou_log[5].append(kan_str)
                        case 1:
                            tenhou_log[8].append(kan_str)
                        case 2:
                            tenhou_log[11].append(kan_str)
                        case 3:
                            tenhou_log[14].append(kan_str)

            if mjai_message["type"] == "ankan":
                actor = mjai_message["actor"]
                consumed_pai = mjai_message["consumed"][0]
                pai_num = str(mahjong_to_number[consumed_pai])
                
                ankan_str = f"{pai_num}{pai_num}{pai_num}a{pai_num}"

                discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
                discard_idx = discard_log_indices[actor]
                tenhou_log[discard_idx].append(ankan_str)

            if mjai_message["type"] == "kakan":
                actor = mjai_message["actor"]
                consumed_pai = mjai_message["consumed"][0]
                pai_num = str(mahjong_to_number[consumed_pai])
                
                ankan_str = f"{pai_num}{pai_num}k{pai_num}{pai_num}"

                discard_log_indices = {0: 6, 1: 9, 2: 12, 3: 15}
                discard_idx = discard_log_indices[actor]
                tenhou_log[discard_idx].append(ankan_str)


            if mjai_message["type"] == "chi":
                actor = mjai_message["actor"]
                pai = mjai_message["pai"]
                consumed = mjai_message["consumed"]

                pai_num = str(mahjong_to_number[pai])
                consumed_pai1_num = str(mahjong_to_number[consumed[0]])
                consumed_pai2_num = str(mahjong_to_number[consumed[1]])

                chi_str = f"c{pai_num}{consumed_pai1_num}{consumed_pai2_num}"

                match actor:
                    case 0:
                        tenhou_log[5].append(chi_str)
                    case 1:
                        tenhou_log[8].append(chi_str)
                    case 2:
                        tenhou_log[11].append(chi_str)
                    case 3:
                        tenhou_log[14].append(chi_str)
            

            if mjai_message["type"] == "end_kyoku" or mjai_message["type"] == "end_game":
                tenhou_logs.append(tenhou_log)
                
    logs['log'] = tenhou_logs
    return logs

def extract_log_id(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return params.get('log', [None])[0]

def build_download_url(original_url):
    log_id = extract_log_id(original_url)
    if not log_id:
        return None
    return f"https://tenhou.net/0/log/?{log_id}"

def get_headers(referer):
    return {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'zh-CN,zh;q=0.9,zh-HK;q=0.8,zh-TW;q=0.7',
        'Connection': 'keep-alive',
        'Host': 'tenhou.net',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0',
        'sec-ch-ua': '"Not(A:Brand";v="99", "Microsoft Edge";v="133", "Chromium";v="133"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

def download_paipu_data(original_url):
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
        # print(response.text)
        return response.text
    except Exception as e:
        print(f"下载失败 {original_url}: {str(e)}")
        return None


def main():
    url = input("天凤牌谱URL格式示例：http://tenhou.net/0/?log=2025120632gm-00a9-0000-8f4679af&tw=2\n请输入天凤牌谱URL: ")
    paipu_data = download_paipu_data(url)

    if paipu_data:
        log_id = extract_log_id(url)
        logs = parse_tenhou_xml_to_mjai(paipu_data, 0)
        output_filename = f"{log_id}.json"

        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, separators=(',', ':'))
        print(f"牌谱已成功保存到 {output_filename}")
        input("按任意键退出...")
    else:
        print("未找到有效的牌谱数据，请检查URL是否正确。")



if __name__ == "__main__":
    main()
