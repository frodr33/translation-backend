import socket
import threading
import socketio
import websockets
import asyncio

sio = socketio.Client()
sio.connect('ws://translation-backend.herokuapp.com/receive')
print('my session identifier (sid) is', sio.sid)

sio.emit('hello')


@sio.event
def message(data):
    print(data)


while True:
    inp = input(">")
    sio.emit("message", inp)


# async def hello():
#     uri = "ws://translation-backend.herokuapp.com/receive"
#     async with websockets.connect(uri) as websocket:
#         name = input("What's your name? ")
#
#         await websocket.send(name)
#         print(f"> {name}")
#
# asyncio.get_event_loop().run_until_complete(hello())