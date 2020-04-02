import socket
import threading
import socketio
import websockets
import asyncio


async def receive():
    # uri = "ws://translation-backend.herokuapp.com/receive"
    uri = "ws://localhost:7000/receive"
    async with websockets.connect(uri) as websocket:
        while True:
            msg = await websocket.recv()
            print(f"> {msg}")

asyncio.get_event_loop().run_until_complete(receive())