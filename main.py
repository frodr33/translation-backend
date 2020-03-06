from flask import Flask
from flask_socketio import SocketIO, emit, send, join_room
from datetime import datetime
import threading

CHANNEL = "translation-room"
num_clients = 0
clients = {}

app = Flask(__name__)
socketio = SocketIO(app)


@app.route('/')
def homepage():
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    return """
    <h1>Hello heroku</h1>
    <p>It is currently {time}.</p>
    """.format(time=the_time)


@socketio.on('message')
def handle_message(message):
    if num_clients != 2:
        send("Channel is not full")
    else:
        print('received message: ' + message)
        send("response?")
        send()


@socketio.on('join')
def on_join(data):
    global num_clients
    print("in join")
    username = data['username']
    sid = data['sid']

    if num_clients < 2:
        join_room(CHANNEL)
        send(username + " has joined chat room")
    else:
        send("Channel full, unable to join")

    num_clients += 1
    print("Num Clients: ", num_clients)


if __name__ == '__main__':
    socketio.run(app, debug=True)
