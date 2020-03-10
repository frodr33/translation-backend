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
    <h1>Translation Backend Server.</h1>
    <p>This root page is only for health checking of the server. To send messages to the web socket server,</p>
    <p>create a web socket connection and send to the ws://translation-backend.herokuapp.com/submit endpoint. </p>
    <p>To receive from the web socket, create a web socket connection at ws://translation-backend.herokuapp.com/receive</p>
    <p>and receive from this endpoint. </p>
    """.format(time=the_time)


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