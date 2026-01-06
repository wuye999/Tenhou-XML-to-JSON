from __future__ import annotations
import re
import json
import copy
import math
from enum import Enum
from typing import Self, Dict, List, Optional, Any, Set
from copy import deepcopy
from itertools import combinations, permutations
from loguru import logger

# --- converter.py ---
tiles_mjai: list[str] = [
    '1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m',
    '1p', '2p', '3p', '4p', '5p', '6p', '7p', '8p', '9p',
    '1s', '2s', '3s', '4s', '5s', '6s', '7s', '8s', '9s',
    'E', 'S', 'W', 'N', 'P', 'F', 'C'
]

tiles_tenhou: dict[str, int] = {
    '1m': 0, '2m': 1, '3m': 2, '4m': 3, '5m': 4, '5mr': 4, '6m': 5, '7m': 6, '8m': 7, '9m': 8,
    '1p': 9, '2p': 10, '3p': 11, '4p': 12, '5p': 13, '5pr': 13, '6p': 14, '7p': 15, '8p': 16, '9p': 17,
    '1s': 18, '2s': 19, '3s': 20, '4s': 21, '5s': 22, '5sr': 22, '6s': 23, '7s': 24, '8s': 25, '9s': 26,
    'E': 27, 'S': 28, 'W': 29, 'N': 30, 'P': 31, 'F': 32, 'C': 33
}

def tenhou_to_mjai_one(index: int) -> str:
    return tenhou_to_mjai([index])[0]

def mjai_to_tenhou_one(state, label: str, tsumogiri: bool = False) -> int:
    if tsumogiri:
        return state.hand[-1]
    else:
        return mjai_to_tenhou(state, [label])[0]

def tenhou_to_mjai(indices: list[int]) -> list[str]:
    ret = []
    for index in indices:
        label = tiles_mjai[index // 4]
        ret.append(label + 'r' if index in [16, 52, 88] else label)
    return ret

def mjai_to_tenhou(state, labels: list[str]) -> list[int]:
    ret = []
    hand = deepcopy(state.hand)
    hand = sorted(hand, reverse=True)
    for label in labels:
        is_red = label[-1] == 'r'
        index = tiles_tenhou[label[:2] if is_red else label]
        index = [i for i in hand if i // 4 == index and (not is_red or i % 4 == 0)][0]
        ret.append(index)
    return ret

def to_34_array(indices: list[int]) -> list[int]:
    ret = [0] * 34
    for index in indices:
        ret[index // 4] += 1
    return ret

# --- judwin.py ---
def iswh0(h: list[int]) -> bool:
    a, b = h[0], h[1]
    for i in range(7):
        r = a % 3
        if b >= r and h[i + 2] >= r:
            a, b = b - r, h[i + 2] - r
        else:
            return False
    return a % 3 == 0 and b % 3 == 0

def iswh2(h: list[int]) -> bool:
    s = 0
    for i in range(9):
        s += i * h[i]
    for p in range(s * 2 % 3, 9, 3):
        if h[p] >= 2:
            h[p] -= 2
            if iswh0(h):
                h[p] += 2
                return True
            else:
                h[p] += 2
    return False

def islh(h: list[int]) -> bool:
    head: int | None = None
    for i in range(3):
        s = sum(h[9 * i:9 * i + 9])
        if s % 3 == 1:
            return False
        elif s % 3 == 2:
            if head is None:
                head = i
            else:
                return False
    for i in range(27, 34):
        if h[i] % 3 == 1:
            return False
        elif h[i] % 3 == 2:
            if head is None:
                head = i
            else:
                return False
    for i in range(3):
        if i == head:
            if not iswh2(h[9 * i:9 * i + 9]):
                return False
        else:
            if not iswh0(h[9 * i:9 * i + 9]):
                return False
    return True

def issp(h: list[int]) -> bool:
    for i in range(34):
        if h[i] != 0 and h[i] != 2:
            return False
    return True

def isto(h: list[int]) -> bool:
    for i in [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 24, 25]:
        if h[i] > 0:
            return False
    for i in [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]:
        if h[i] == 0:
            return False
    return True

# --- judrdy.py ---
def isrh(h: list[int]) -> set[int]:
    ret = set()
    for i in range(34):
        if h[i] < 4:
            h[i] += 1
            if islh(h) or issp(h) or isto(h):
                ret.add(i)
            h[i] -= 1
    return ret

# --- decoder.py ---
class Meld:
    CHI = 'chi'
    PON = 'pon'
    KAKAN = 'kakan'
    DAIMINKAN = 'daiminkan'
    ANKAN = 'ankan'

    def __init__(self, target: int, meld_type: str, tiles: list[int], unused: int | None = None, r: int | None = None):
        self.target: int = target
        self.meld_type: str = meld_type
        self.tiles: list[int] = tiles
        self.unused: int | None = unused
        self.r: int | None = r

    @property
    def pai(self) -> str:
        return tenhou_to_mjai([self.tiles[0]])[0]

    @property
    def consumed(self) -> list[str]:
        if self.meld_type == self.ANKAN:
            return tenhou_to_mjai(self.tiles)
        else:
            return tenhou_to_mjai(self.tiles[1:])

    @property
    def exposed(self) -> list[int]:
        if self.meld_type == self.ANKAN:
            return self.tiles
        elif self.meld_type == self.KAKAN:
            return self.tiles[0:1]
        else:
            return self.tiles[1:]

    @staticmethod
    def parse_meld(m: int) -> 'Meld':
        if m & (1 << 2):
            return Meld.parse_chi(m)
        elif m & (1 << 3):
            return Meld.parse_pon(m)
        elif m & (1 << 4):
            return Meld.parse_kakan(m)
        else:
            return Meld.parse_daiminkan_ankan(m)

    @staticmethod
    def parse_chi(m: int) -> 'Meld':
        t = m >> 10
        r = t % 3
        t //= 3
        t = t // 7 * 9 + t % 7
        t *= 4
        h = [
            t + 4 * 0 + ((m >> 3) & 0x3),
            t + 4 * 1 + ((m >> 5) & 0x3),
            t + 4 * 2 + ((m >> 7) & 0x3),
        ]
        h[0], h[r] = h[r], h[0]
        return Meld(m & 3, Meld.CHI, h, r=r)

    @staticmethod
    def parse_pon(m: int) -> 'Meld':
        unused = (m >> 5) & 0x3
        t = m >> 9
        r = t % 3
        t = t // 3 * 4
        h = [t, t + 1, t + 2, t + 3]
        unused = h.pop(unused)
        h[0], h[r] = h[r], h[0]
        return Meld(m & 3, Meld.PON, h, unused=unused)

    @staticmethod
    def parse_kakan(m: int) -> 'Meld':
        added = (m >> 5) & 0x3
        t = m >> 9
        r = t % 3
        t = t // 3 * 4
        h = [t, t + 1, t + 2, t + 3]
        added = h.pop(added)
        h[0], h[r] = h[r], h[0]
        h = [added, *h]
        return Meld(m & 3, Meld.KAKAN, h)

    @staticmethod
    def parse_daiminkan_ankan(m: int) -> 'Meld':
        target = m & 3
        hai0 = m >> 8
        t = hai0 // 4 * 4
        r = hai0 % 4
        h = [t, t + 1, t + 2, t + 3]
        h[0], h[r] = h[r], h[0]
        if target == 0:
            return Meld(target, Meld.ANKAN, h)
        else:
            return Meld(target, Meld.DAIMINKAN, h)

def parse_sc_tag(message: dict[str, str]) -> list[int]:
    sc = [int(s) for s in message['sc'].split(',')]
    before = sc[0::2]
    delta = sc[1::2]
    after = [(x + y) * 100 for x, y in zip(before, delta)]
    return after

def parse_owari_tag(message: dict[str, str]) -> list[int]:
    sc = [int(s) for s in message['owari'].split(',')[0::2]]
    ret = [x * 100 for x in sc]
    return ret

# --- state.py ---
class State:
    def __init__(self, name: str = 'NoName', room: str = '0_0'):
        self.name: str = name
        self.room: str = room.replace('_', ',')
        self.seat: int = 0
        self.hand: list[int] = []
        self.in_riichi: bool = False
        self.live_wall: int | None = None
        self.melds: list[Meld] = []
        self.wait: set[int] = set()
        self.last_kawa_tile: str = '?'
        self.is_tsumo: bool = False
        self.is_3p: bool = False
        self.is_new_round: bool = False

# --- bridge.py ---
class TenhouBridge():
    def __init__(self):
        self.state = State()

    def parse(self, content: bytes) -> None | list[dict]:
        if content == b'<Z/>':
            return None
        try:
            message = json.loads(content)
            assert isinstance(message, dict)
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON: %s", content)
            return None
        except AssertionError:
            logger.warning("Invalid JSON: %s", content)
            return None

        tag = message.get("tag")
        if tag == "HELO": return self._convert_helo(message)
        if tag == "REJOIN": return self._convert_rejoin(message)
        if tag == "GO": return self._convert_go(message)
        if tag == "TAIKYOKU": return self._convert_start_game(message)
        if tag == "INIT": return self._convert_start_kyoku(message)
        if re.match(r'^[TUVW]\d*$', tag): return self._convert_tsumo(message)
        if re.match(r'^[DEFGdefg]\d*$', tag): return self._convert_dahai(message)
        if tag == 'N' and 'm' in message: return self._convert_meld(message)
        if tag == 'REACH' and message['step'] == '1': return self._convert_reach(message)
        if tag == 'REACH' and message['step'] == '2': return self._convert_reach_accepted(message)
        if tag == 'DORA': return self._convert_dora(message)
        if tag == 'AGARI' and 'owari' not in message: return self._convert_hora(message)
        if tag == 'RYUUKYOKU' and 'owari' not in message: return self._convert_ryukyoku(message)
        if 'owari' in message: return self._convert_end_game(message)
        return None
    
    def _convert_helo(self, message: dict) -> list[dict] | None: return None
    def _convert_rejoin(self, message: dict) -> list[dict] | None: return None
    def _convert_go(self, message: dict) -> list[dict] | None: return None
    
    def _convert_start_game(self, message: dict) -> list[dict] | None:
        mjai_messages = [{'type': 'start_game', 'id': 0}]
        self.state.seat = (4-int(message['oya'])) % 4
        mjai_messages[0]['id'] = self.state.seat
        return mjai_messages
    
    def _convert_start_kyoku(self, message: dict) -> list[dict] | None:
        self.state.hand = [int(s) for s in message['hai'].split(',')]
        self.state.in_riichi = False
        self.state.live_wall = 70
        self.state.melds.clear()
        self.state.wait.clear()
        self.state.last_kawa_tile = '?'
        self.state.is_tsumo = False
        self.state.is_new_round = True
        bakaze_names = ['E', 'S', 'W', 'N']
        oya = self.rel_to_abs(int(message['oya']))
        seed = [int(s) for s in message['seed'].split(',')]
        bakaze = bakaze_names[seed[0] // 4]
        kyoku = seed[0] % 4 + 1
        honba = seed[1]
        kyotaku = seed[2]
        dora_marker = tenhou_to_mjai_one(seed[5])
        scores = [int(s)*100 for s in message['ten'].split(',')]
        tehais = [['?' for _ in range(13)]] * 4
        tehais[self.state.seat] = tenhou_to_mjai(self.state.hand)
        if bakaze == 'E' and kyoku == 1 and honba == 0:
            if 0 in scores: self.state.is_3p = True
        if self.state.is_3p:
            new_scores = [-1, -1, -1, -1]
            for i in range(4): new_scores[self.rel_to_abs(i)] = scores[i]
            scores = new_scores
        return [{
            'type': 'start_kyoku', 'bakaze': bakaze, 'kyoku': kyoku, 'honba': honba,
            'kyotaku': kyotaku, 'oya': oya, 'dora_marker': dora_marker, 'scores': scores, 'tehais': tehais
        }]
    
    def _convert_tsumo(self, message: dict) -> list[dict] | None:
        self.state.live_wall -= 1
        tag = message['tag']
        actor = self.rel_to_abs(ord(tag[0]) - ord('T'))
        mjai_messages = [{'type': 'tsumo', 'actor': actor, 'pai': '?'}]
        index = int(tag[1:])
        mjai_messages[0]['pai'] = tenhou_to_mjai_one(index)
        self.state.hand.append(index)
        self.state.is_tsumo = True
        return mjai_messages

    def _convert_dahai(self, message: dict) -> list[dict] | None:
        tag = message['tag']
        actor = self.rel_to_abs(ord(str.upper(tag[0])) - ord('D'))
        if len(tag) == 1:
            index = self.state.hand[-1]
        else:
            index = int(tag[1:])
        pai = tenhou_to_mjai_one(index)
        tsumogiri = index == self.state.hand[-1]
        self.state.last_kawa_tile = pai
        mjai_messages = [{'type': 'dahai', 'actor': actor, 'pai': pai, 'tsumogiri': tsumogiri}]
        self.state.is_tsumo = False
        if actor == self.state.seat:
            try: self.state.hand.remove(index)
            except ValueError: pass
        return mjai_messages
    
    def _convert_meld(self, message: dict) -> list[dict] | None:
        actor = self.rel_to_abs(int(message['who']))
        m = int(message['m'])
        if (m & 0x3F) == 0x20 :
            mjai_messages = [{'type': 'nukidora', 'actor': actor, 'pai': 'N'}]
            if actor == self.state.seat:
                for i in self.state.hand:
                    if i // 4 == 30:
                        self.state.hand.remove(i)
                        break
            return mjai_messages
        meld = Meld.parse_meld(m)
        if meld.meld_type == Meld.CHI: target = (actor - 1) % 4
        else: target = (actor + meld.target) % 4
        mjai_messages = [{
            'type': meld.meld_type, 'actor': actor, 'target': target,
            'pai': meld.pai, 'consumed': meld.consumed
        }]
        if meld.meld_type in [Meld.KAKAN, Meld.ANKAN]: del mjai_messages[0]['target']
        if meld.meld_type == Meld.ANKAN: del mjai_messages[0]['pai']
        if actor == self.state.seat:
            for i in meld.exposed:
                try: self.state.hand.remove(i)
                except ValueError: pass
            self.state.melds.append(meld)
        return mjai_messages
    
    def _convert_reach(self, message: dict) -> list[dict] | None:
        actor = self.rel_to_abs(int(message['who']))
        return [{'type': 'reach', 'actor': actor}]
        
    def _convert_reach_accepted(self, message: dict) -> list[dict] | None:
        actor = self.rel_to_abs(int(message['who']))
        if actor == self.state.seat:
            self.state.in_riichi = True
            self.state.wait = isrh(to_34_array(self.state.hand))
        deltas = [0] * 4
        deltas[actor] = -1000
        scores = [int(s) * 100 for s in message['ten'].split(',')]
        return [{'type': 'reach_accepted', 'actor': actor, 'deltas': deltas, 'scores': scores}]
    
    def _convert_dora(self, message: dict) -> list[dict] | None:
        hai = int(message['hai'])
        dora_marker = tenhou_to_mjai_one(hai)
        return [{'type': 'dora', 'dora_marker': dora_marker}]

    def _convert_hora(self, message: dict) -> list[dict] | None:
        return [{'type': 'end_kyoku'}]
    
    def _convert_ryukyoku(self, message: dict) -> list[dict] | None:
        scores = parse_sc_tag(message)
        return [{'type': 'ryukyoku', 'scores': scores}, {'type': 'end_kyoku'}]
    
    def _convert_end_game(self, message: dict) -> list[dict] | None:
        return [{'type': 'end_game'}]

    def rel_to_abs(self, rel: int) -> int: return (rel + self.state.seat) % 4
    def abs_to_rel(self, abs: int) -> int: return (abs - self.state.seat) % 4

    def consumed_ankan(self, state: State) -> set[tuple[str, str, str, str]]:
        ret = set()
        if state.live_wall <= 0: return ret
        hand34 = to_34_array(state.hand)
        if state.in_riichi:
            i = state.hand[-1] // 4
            if hand34[i] == 4:
                hand34[i] -= 4
                if state.wait == isrh(hand34):
                    ret.add(tuple(tenhou_to_mjai([4 * i, 4 * i + 1, 4 * i + 2, 4 * i + 3])))
            return ret
        else:
            for i in range(34):
                if hand34[i] == 4: ret.add(tuple(tenhou_to_mjai([4 * i, 4 * i + 1, 4 * i + 2, 4 * i + 3])))
            return ret

    def consumed_kakan(self, state: State) -> set[tuple[str, str, str, str]]:
        ret = set()
        if state.live_wall <= 0: return ret
        for i in state.hand:
            for meld in state.melds:
                if meld.meld_type == Meld.PON and i // 4 == meld.tiles[0] // 4:
                    ret.add(tuple(tenhou_to_mjai([i] + meld.tiles)))
        return ret
    
    def consumed_pon(self, state: State, index: int) -> set[tuple[str, str]]:
        ret = set()
        for i, j in list(combinations(state.hand, 2)):
            if i // 4 == j // 4 == index // 4: ret.add(tuple(tenhou_to_mjai([i, j])))
        return ret

    def consumed_chi(self, state: State, index: int) -> set[tuple[str, str]]:
        ret = set()
        for i, j in list(permutations(state.hand, 2)):
            i34, j34, index34 = i // 4, j // 4, index // 4
            if i34 // 9 == j34 // 9 == index34 // 9:
                if index34 == i34 - 1 == j34 - 2 \
                        or i34 + 1 == index34 == j34 - 1 \
                        or i34 + 2 == j34 + 1 == index34:
                    ret.add(tuple(tenhou_to_mjai([i, j])))
        return ret
