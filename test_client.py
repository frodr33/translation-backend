import socket
import threading
import socketio

sio = socketio.Client()
sio.connect('http://localhost:5000')
print('my session identifier (sid) is', sio.sid)

sio.emit('join', {"username": "Frank", "sid": sio.sid})


@sio.event
def message(data):
    print(data)


while True:
    inp = input(">")
    sio.emit("message", inp)
