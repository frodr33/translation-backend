import socket
import threading
import socketio
import websockets
import asyncio

# sio = socketio.Client()
# sio.connect('http://translation-backend.herokuapp.com/submit')
# print('my session identifier (sid) is', sio.sid)
#
# sio.emit('hello')
#
#
# @sio.event
# def message(data):
#     print(data)
#
#
# while True:
#     inp = input(">")
#     sio.emit("message", inp)


async def hello():
    uri = "ws://translation-backend.herokuapp.com/submit"
    async with websockets.connect(uri) as websocket:
        while True:
            name = input(">")

            await websocket.send(name)
            print(f"Sent message '{name}'")

asyncio.get_event_loop().run_until_complete(hello())