from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json
from doudizhu_rules import DouDiZhu

app = FastAPI()

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件（客户端页面）
app.mount("/static", StaticFiles(directory="static"), name="static")

# 房间存储：{room_id: {players: {player1: ws, player2: ws, player3: ws}, game: DouDiZhu实例, status: 状态}}
rooms = {}

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await websocket.accept()

    # 初始化房间
    if room_id not in rooms:
        rooms[room_id] = {
            "players": {},  # 玩家WS映射
            "game": DouDiZhu(),  # 斗地主实例
            "status": "waiting",  # waiting/叫地主/出牌/结束
            "call_landlord_order": ["player1", "player2", "player3"],  # 叫地主顺序
            "current_call_player": None,  # 当前叫地主玩家
        }
    room = rooms[room_id]
    players = room["players"]

    # 校验玩家ID（仅允许player1/2/3）
    if player_id not in ["player1", "player2", "player3"]:
        await websocket.close(code=1008, reason="无效玩家ID（仅player1/2/3）")
        return
    # 房间已满
    if player_id in players:
        await websocket.close(code=1008, reason="该玩家已在房间内")
        return
    # 绑定玩家WS
    players[player_id] = websocket
    print(f"玩家{player_id}加入房间{room_id}，当前人数：{len(players)}")

    # 通知所有玩家当前房间状态
    await broadcast_room_status(room_id)

    # 3人全部加入，开始洗牌发牌+叫地主阶段
    if len(players) == 3 and room["status"] == "waiting":
        room["game"].shuffle_cards()
        room["status"] = "call_landlord"
        room["current_call_player"] = room["call_landlord_order"][0]  # 先让player1叫地主
        # 通知所有人进入叫地主阶段，告知当前叫地主玩家
        await broadcast(room_id, json.dumps({
            "type": "call_landlord_start",
            "current_player": room["current_call_player"],
            "msg": "3人已就位，开始叫地主！"
        }))

    try:
        while True:
            # 监听玩家消息
            data = await websocket.receive_text()
            data_json = json.loads(data)
            print(f"收到玩家{player_id}消息：{data_json}")

            # 处理叫地主请求
            if data_json["type"] == "call_landlord" and room["status"] == "call_landlord":
                await handle_call_landlord(room_id, player_id, data_json["action"])  # action: call/skip
            
            # 处理出牌请求
            elif data_json["type"] == "play_cards" and room["status"] == "playing":
                await handle_play_cards(room_id, player_id, data_json["cards"])  # cards: 出牌列表
            
            # 处理聊天消息
            elif data_json["type"] == "chat":
                await broadcast(room_id, json.dumps({
                    "type": "chat",
                    "player": player_id,
                    "msg": data_json["msg"]
                }))

    except WebSocketDisconnect:
        # 玩家断开连接，清理房间
        del players[player_id]
        await broadcast(room_id, json.dumps({
            "type": "player_disconnect",
            "player": player_id,
            "msg": f"玩家{player_id}已退出房间"
        }))
        # 房间无玩家则删除
        if not players:
            del rooms[room_id]
        else:
            room["status"] = "waiting"
            await broadcast_room_status(room_id)

# 广播房间状态（玩家列表、游戏状态等）
async def broadcast_room_status(room_id):
    room = rooms[room_id]
    status_data = {
        "type": "room_status",
        "players": list(room["players"].keys()),
        "status": room["status"],
        "player_count": len(room["players"])
    }
    await broadcast(room_id, json.dumps(status_data))

# 广播消息给房间内所有玩家
async def broadcast(room_id, msg):
    room = rooms[room_id]
    for ws in room["players"].values():
        await ws.send_text(msg)

# 处理叫地主逻辑
async def handle_call_landlord(room_id, player_id, action):
    room = rooms[room_id]
    # 不是当前叫地主玩家，拒绝
    if player_id != room["current_call_player"]:
        await room["players"][player_id].send_text(json.dumps({
            "type": "error",
            "msg": "还没到你的回合叫地主！"
        }))
        return

    # 玩家选择叫地主
    if action == "call":
        room["game"].landlord = player_id
        # 地主获得底牌
        room["game"].player_cards[player_id].extend(room["game"].landlord_cards)
        # 排序地主的牌
        room["game"].player_cards[player_id] = room["game"].sort_cards(room["game"].player_cards[player_id])
        room["status"] = "playing"
        room["current_turn"] = player_id  # 地主先出牌
        # 通知所有人：地主确定+底牌+手牌+出牌回合
        await broadcast(room_id, json.dumps({
            "type": "landlord_confirmed",
            "landlord": player_id,
            "landlord_cards": room["game"].landlord_cards,
            "player_cards": room["game"].player_cards,
            "current_turn": player_id,
            "msg": f"玩家{player_id}成为地主，获得底牌{room['game'].landlord_cards}，开始出牌！"
        }))
    # 玩家选择不叫
    elif action == "skip":
        # 获取下一个叫地主玩家
        current_idx = room["call_landlord_order"].index(player_id)
        next_idx = (current_idx + 1) % 3
        room["current_call_player"] = room["call_landlord_order"][next_idx]
        # 通知所有人：当前玩家不叫，下一个玩家叫地主
        await broadcast(room_id, json.dumps({
            "type": "call_landlord_skip",
            "player": player_id,
            "next_player": room["current_call_player"],
            "msg": f"玩家{player_id}不叫地主，轮到{room['current_call_player']}叫地主！"
        }))

# 处理出牌逻辑
async def handle_play_cards(room_id, player_id, cards):
    room = rooms[room_id]
    game = room["game"]
    # 不是当前回合玩家
    if player_id != room["current_turn"]:
        await room["players"][player_id].send_text(json.dumps({
            "type": "error",
            "msg": "还没到你的回合出牌！"
        }))
        return
    # 玩家牌中没有要出的牌
    player_current_cards = game.player_cards[player_id]
    if not set(cards).issubset(set(player_current_cards)):
        await room["players"][player_id].send_text(json.dumps({
            "type": "error",
            "msg": "你没有这些牌！"
        }))
        return
    # 校验牌型合法性
    last_cards_info = game.parse_card_type(game.last_cards) if game.last_cards else ('空', 0)
    if not game.is_valid_play(cards, last_cards_info):
        await room["players"][player_id].send_text(json.dumps({
            "type": "error",
            "msg": "牌型不合法/打不过上一轮的牌！"
        }))
        return

    # 出牌合法：更新状态
    # 移除玩家已出的牌
    for card in cards:
        player_current_cards.remove(card)
    game.player_cards[player_id] = player_current_cards
    game.last_cards = cards
    game.last_player = player_id

    # 判定是否胜利（牌打完）
    if len(player_current_cards) == 0:
        room["status"] = "finished"
        winner = player_id
        # 通知所有人胜利
        await broadcast(room_id, json.dumps({
            "type": "game_over",
            "winner": winner,
            "is_landlord": (winner == game.landlord),
            "msg": f"玩家{winner}获胜！{'地主赢' if winner == game.landlord else '农民赢'}"
        }))
        return

    # 切换回合（下一个玩家）
    player_order = ["player1", "player2", "player3"]
    current_idx = player_order.index(player_id)
    next_idx = (current_idx + 1) % 3
    room["current_turn"] = player_order[next_idx]

    # 广播出牌结果
    await broadcast(room_id, json.dumps({
        "type": "play_cards_ok",
        "player": player_id,
        "cards": cards,
        "remaining_cards": {p: len(game.player_cards[p]) for p in player_order},
        "current_turn": room["current_turn"],
        "msg": f"玩家{player_id}出牌：{cards}，轮到{room['current_turn']}出牌！"
    }))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)