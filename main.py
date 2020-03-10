import os
from flask import Flask
from flask_sockets import Sockets
from flask_socketio import SocketIO, emit, send, join_room
from datetime import datetime
import threading
import redis
import gevent

REDIS_URL = os.getenv('REDISTOGO_URL', None)
REDIS_CHANNEL = "translation-room"

if not REDIS_URL:
    print("NO REDIS SERVER FOUND")

num_clients = 0
clients = {}

app = Flask(__name__)
sockets = Sockets(app)
redis = redis.from_url(REDIS_URL)


class ChatBackend:
    def __init__(self):
        self.clients = []
        self.pubsub = redis.pubsub()
        self.pubsub.subscribe(REDIS_CHANNEL)

    def __iter_data(self):
        for message in self.pubsub.listen():
            print("ITERATING THROUGH REDIS PUBSUB: ", message)
            data = message.get('data')
            if message['type'] == 'message':
                app.logger.info(u'Sending message: {}'.format(data))
                yield data

    def register(self, client):
        """Register a WebSocket connection for Redis updates."""
        self.clients.append(client)

    def send(self, client, data):
        """Send given data to the registered client.
        Automatically discards invalid connections."""
        try:
            client.send(data)
        except Exception:
            self.clients.remove(client)

    def run(self):
        """Listens for new messages in Redis, and sends them to clients."""
        for data in self.__iter_data():
            print("RUNNING for data: ", data)
            for client in self.clients:
                print("Client: ", client)
                gevent.spawn(self.send, client, data)

    def start(self):
        """Maintains Redis subscription in the background."""
        gevent.spawn(self.run)

chats = ChatBackend()
chats.start()


@app.route('/')
def homepage():
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    return """
    <h1>Hello heroku</h1>
    <p>It is currently {time}.</p>
    """.format(time=the_time)


# @socketio.on('message')
# def handle_message(message):
#     if num_clients != 2:
#         send("Channel is not full")
#     else:
#         print('received message: ' + message)
#         send("response?")
#         send()
#
#
# @socketio.on('join')
# def on_join(data):
#     global num_clients
#     print("in join")
#     username = data['username']
#     sid = data['sid']
#
#     join_room(CHANNEL)
#     send(username + " has joined chat room")
#
#     num_clients += 1
#     print("Num Clients: ", num_clients)


@sockets.route('/submit')
def inbox(ws):
    """Receives incoming chat messages, inserts them into Redis."""
    print("INSIDE OF SUBMIT: ", ws)

    while not ws.closed:
        gevent.sleep(0.1)
        message = ws.receive()

        if message:
            app.logger.info(u'Inserting message: {}'.format(message))
            print("PUBLISHING MSG TO REDIS")
            redis.publish(REDIS_CHANNEL, message)


@sockets.route('/receive')
def outbox(ws):
    """Sends outgoing chat messages, via `ChatBackend`."""
    print("IN OUTBOX")
    chats.register(ws)

    while not ws.closed:
        # Context switch while `ChatBackend.start` is running in the background.
        gevent.sleep(0.1)