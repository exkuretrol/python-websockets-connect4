import asyncio
import logging
from websockets.server import WebSocketServerProtocol, WebSocketServer, serve
from websockets.legacy.protocol import broadcast
import secrets
import json
import signal
from Connect4.connect4 import PLAYER1, PLAYER2, Connect4
import http

logging.basicConfig(format="%(message)s", level=logging.DEBUG)

JOIN = {}
WATCH = {}


async def error(websocket: WebSocketServerProtocol, message: str):
    event = {
        "type": "error",
        "message": message
    }
    await websocket.send(json.dumps(event))


async def replay(websocket: WebSocketServerProtocol, game: Connect4):
    for player, column, row in game.moves.copy():
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row
        }

        await websocket.send(json.dumps(event))


async def play(websocket: WebSocketServerProtocol, game: Connect4, player, connected):
    async for message in websocket:
        # print("first player sent ", message)
        event = json.loads(message)
        assert event['type'] == "play"
        column = event['column']

        try:
            row = game.play(player, column)
        except RuntimeError as err:
            await error(websocket, str(err))
            continue

        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row
        }

        broadcast(connected, json.dumps(event))

        if game.winner is not None:
            event = {
                "type": "win",
                "player": game.winner,
            }
            broadcast(connected, json.dumps(event))


async def start(websocket: WebSocketServerProtocol):
    game = Connect4()
    connected = {websocket}
    join_key = secrets.token_urlsafe(10)
    JOIN[join_key] = game, connected

    watch_key = secrets.token_urlsafe(10)
    WATCH[watch_key] = game, connected

    try:
        event = {
            "type": "init",
            "join": join_key,
            "watch": watch_key
        }

        await websocket.send(json.dumps(event))
        print("first player joined the game", id(game))
        await play(websocket, game, PLAYER1, connected)

    except Exception as e:
        pass
    finally:
        del JOIN[join_key]
        del WATCH[watch_key]


async def join(websocket: WebSocketServerProtocol, join_key: str):
    try:
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not found!")
        return

    connected.add(websocket)
    try:
        await replay(websocket, game)
        await play(websocket, game, PLAYER2, connected)
    finally:
        connected.remove(websocket)


async def watch(websocket: WebSocketServerProtocol, watch_key):
    try:
        game, connected = WATCH[watch_key]
    except KeyError:
        await error(websocket, "Game not found!")
        return

    connected.add(websocket)
    try:
        await replay(websocket, game)
        await websocket.wait_closed()
    finally:
        connected.remove(websocket)


async def handler(websocket: WebSocketServerProtocol):
    message = await websocket.recv()
    event = json.loads(message)
    assert event['type'] == "init"

    if "join" in event:
        await join(websocket, event['join'])
    elif "watch" in event:
        await watch(websocket, event['watch'])
    else:
        await start(websocket)

async def health_check(path, request_headers):
    if path == '/healthz':
        return http.HTTPStatus.OK, [], b"OK\n"

async def main():
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with serve(
        handler, 
        host='localhost', 
        port=8001,
        process_request=health_check
    ):
        await stop

if __name__ == "__main__":
    asyncio.run(main())
