import os
from flask import Flask, jsonify
from flask_sockets import Sockets
from flask_socketio import SocketIO, emit, send, join_room
from datetime import datetime
import threading
import redis
import gevent
from googletrans import Translator

REDIS_URL = os.getenv('REDISTOGO_URL', "redis://localhost:6379")
REDIS_CHANNEL = "translation-room"

MAX_CLIENTS = 2  # 0 and 1
CLIENTS = 0

app = Flask(__name__)
sockets = Sockets(app)
redis = redis.from_url(REDIS_URL)

# Redis var setup
num_clients = redis.get("clients")
if not num_clients:
    redis.set("clients", 0)


class TranslationAPI:
    def __init__(self):
        self.translator = Translator()

    def translate(self, message, src="Eng", dest="Span"):
        if not isinstance(message, str):
            message = message.decode("utf-8")

        # Check if ignore flag
        if "IGNORE" in message:
            return message

        # Remove prepended metadata
        lang_index = message.index(":") + 1
        message_index = message.index(":", lang_index)

        language = message[lang_index:message_index]
        message_content = message[message_index:]

        print("Translating for langauge: ", language)

        translation = self.translator.translate(message_content, dest=language)
        translated_text = translation.text

        # Add metadata back in
        final_message = message[:message_index] + translated_text

        print("Translated: ", message, " to: ", final_message)
        return final_message


class ChatBackend:
    def __init__(self):
        self.clients = []
        self.pubsub = redis.pubsub()
        self.pubsub.subscribe(REDIS_CHANNEL)
        self.translation_api = TranslationAPI()

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
            #  Initiate text-text translations
            translated_data = self.translation_api.translate(data)
            client.send(translated_data)
        except Exception as err:
            print(err)
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
    # print()

    while not ws.closed:
        gevent.sleep(0.1)
        message = ws.receive()

        if message:
            app.logger.info(u'Inserting message: {}'.format(message))
            print("PUBLISHING MSG TO REDIS")
            redis.publish(REDIS_CHANNEL, message)


@app.route('/connect')
def homepage():
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    print("CONNECTING")
    num_connected = redis.get("clients")
    num_connected = int(num_connected.decode("utf-8"))

    redis.set("clients", num_connected + 1)
    return "HELLO".format(time=the_time)


@app.route('/disconnect')
def homepage():
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    print("DISCONNECTING")
    num_connected = redis.get("clients")
    num_connected = int(num_connected.decode("utf-8"))
    redis.set("clients", num_connected - 1)

    return "HELLO".format(time=the_time)


@sockets.route('/receive')
def outbox(ws):
    """Sends outgoing chat messages, via `ChatBackend`."""
    print("IN OUTBOX")
    chats.register(ws)

    print("PRINTING CLIENTS", redis.get("clients"))
    while not ws.closed:
        # Context switch while `ChatBackend.start` is running in the background.
        gevent.sleep(0.1)
