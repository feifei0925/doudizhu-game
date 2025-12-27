import random

# 牌面值定义（数值越大牌越大，便于比较）
CARD_VALUE = {
    '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
    'J': 11, 'Q': 12, 'K': 13, 'A': 14, '2': 15, '小王': 16, '大王': 17
}
# 花色（仅用于显示，不影响大小）
CARD_SUIT = ['♠', '♥', '♣', '♦']

class DouDiZhu:
    def __init__(self):
        # 初始化牌库（去掉大小王是52张，加大小王54张）
        self.all_cards = []
        for suit in CARD_SUIT:
            for num in ['3','4','5','6','7','8','9','10','J','Q','K','A','2']:
                self.all_cards.append(f"{suit}{num}")
        self.all_cards.extend(['小王', '大王'])
        self.landlord_cards = []  # 地主底牌
        self.player_cards = {     # 3个玩家的牌
            'player1': [], 'player2': [], 'player3': []
        }
        self.landlord = None      # 当前地主（player1/2/3）
        self.current_turn = None  # 当前出牌玩家
        self.last_cards = None    # 上一轮出牌（牌型+牌列表）
        self.last_player = None   # 上一轮出牌玩家

    def shuffle_cards(self):
        """洗牌+发牌"""
        random.shuffle(self.all_cards)
        # 发牌：每人17张，剩余3张为地主底牌
        self.player_cards['player1'] = self.all_cards[:17]
        self.player_cards['player2'] = self.all_cards[17:34]
        self.player_cards['player3'] = self.all_cards[34:51]
        self.landlord_cards = self.all_cards[51:]
        # 牌按大小排序（便于显示）
        for p in self.player_cards:
            self.player_cards[p] = self.sort_cards(self.player_cards[p])

    def sort_cards(self, cards):
        """按牌面值从大到小排序"""
        return sorted(cards, key=lambda x: CARD_VALUE[x[1:] if x not in ['小王','大王'] else x], reverse=True)

    def parse_card_type(self, cards):
        """解析牌型：返回(牌型标识, 核心数值)，如(单张, 14)、(炸弹, 15)"""
        if not cards:
            return ('空', 0)
        # 提取牌面值（去掉花色）
        card_values = [CARD_VALUE[c[1:] if c not in ['小王','大王'] else c] for c in cards]
        value_count = {}
        for v in card_values:
            value_count[v] = value_count.get(v, 0) + 1
        
        # 特殊牌型：王炸（大王+小王）
        if set(cards) == {'大王', '小王'}:
            return ('王炸', 18)
        
        # 炸弹（4张相同）
        if 4 in value_count.values():
            bomb_value = [v for v, cnt in value_count.items() if cnt ==4][0]
            return ('炸弹', bomb_value)
        
        # 三张（3张相同）
        if 3 in value_count.values() and len(cards)==3:
            three_value = [v for v, cnt in value_count.items() if cnt ==3][0]
            return ('三张', three_value)
        
        # 对子（2张相同）
        if 2 in value_count.values() and len(cards)==2:
            pair_value = [v for v, cnt in value_count.items() if cnt ==2][0]
            return ('对子', pair_value)
        
        # 单张
        if len(cards)==1:
            return ('单张', card_values[0])
        
        # 暂只支持基础牌型（可扩展：顺子、三带一、飞机等）
        return ('无效牌型', 0)

    def is_valid_play(self, current_cards, last_cards_info):
        """校验出牌是否合法：current_cards是当前出的牌，last_cards_info是上一轮(牌型, 核心值)"""
        if last_cards_info[0] == '空':  # 上一轮没人出牌，任意合法牌型都可以
            return self.parse_card_type(current_cards)[0] != '无效牌型'
        
        current_type, current_val = self.parse_card_type(current_cards)
        last_type, last_val = last_cards_info

        # 王炸可以打任意牌
        if current_type == '王炸':
            return True
        
        # 炸弹可以打非王炸/非炸弹的任意牌，或更大的炸弹
        if current_type == '炸弹':
            if last_type != '炸弹' and last_type != '王炸':
                return True
            elif last_type == '炸弹':
                return current_val > last_val
        
        # 同牌型且数值更大
        if current_type == last_type and current_val > last_val:
            return True
        
        return False