import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sockets import Sockets
from flask_socketio import SocketIO, emit, send, join_room
from datetime import datetime
import time
import threading
import redis
import gevent
from googletrans import Translator

REDIS_URL = os.getenv('REDISTOGO_URL', "redis://localhost:6379")
REDIS_CHANNEL = "translation-room"

MAX_CLIENTS = 2  # 0 and 1
CLIENTS = 0

app = Flask(__name__)
CORS(app)
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
        message_index = message.index(":", lang_index) + 1

        language = message[lang_index:message_index-1]
        message_content = message[message_index:]

        print("Translating for langauge: ", language)
        print(message_content)

        translation = self.translator.translate(message_content, dest=language)

        print("translated")
        translated_text = translation.text

        # Add metadata back in
        print("adding preprend")
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

            num_connected = redis.get("clients")
            num_connected = int(num_connected.decode("utf-8"))

            while num_connected != 2:
                num_connected = redis.get("clients")
                num_connected = int(num_connected.decode("utf-8"))
                print("NUM CONNECTED IS: ", num_connected)
                time.sleep(.5)

            for client in self.clients:
                print("Client: ", client)
                gevent.spawn(self.send, client, data)

    def start(self):
        """Maintains Redis subscription in the background."""
        gevent.spawn(self.run)


chats = ChatBackend()
chats.start()


class ConnectionMonitor:
    def __init__(self):
        self.clients = []

    def register(self, client):
        """Register a WebSocket connection for all socket connection updates"""
        self.clients.append(client)

    def send(self, client):
        """Send socket connection updates to clients"""
        try:
            num_connected = redis.get("clients")
            num_connected = num_connected.decode("utf-8")
            client.send(num_connected)
        except Exception as err:
            print(err)
            self.clients.remove(client)

    def run(self):
        """Listens for new messages in Redis, and sends them to clients."""
        while True:
            for client in self.clients:
                gevent.spawn(self.send, client)
            gevent.sleep(1)

    def start(self):
        """Maintains Redis subscription in the background."""
        gevent.spawn(self.run)


connection_montior = ConnectionMonitor()
connection_montior.start()


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

        if ":" in message:
            if message:
                app.logger.info(u'Inserting message: {}'.format(message))
                print("PUBLISHING MSG TO REDIS")
                redis.publish(REDIS_CHANNEL, message)
        else:
            print("received blob?")
            print(message)


@app.route('/connect')
def connect():
    language = request.args.get('lang')

    # id parameter needed to avoid heroku caching request and waiting because
    # it was exactly the same as previous request when languages are also the same
    id = request.args.get('id')

    # print("IN /CONNECT")

    if id is None or language is None:
        # print("Reconnection received")
        langs = []
        lang_arr = redis.lrange("langs", 0, redis.llen("langs"))

        for lang in lang_arr:
            if not isinstance(lang, str):
                lang_key = lang.decode("utf-8")
            else:
                lang_key = lang

            langs.append(lang_key)

        # print("Language list currently contains: ", langs)
        return jsonify(langs)

    else:
        print("IN ELSE")
        print(language)
        print(id)

    try:
        print("Connecting client with ID: " + id)
        num_connected = redis.get("clients")
        num_connected = int(num_connected.decode("utf-8"))

        redis.set("clients", num_connected + 1)
        print("PRINTING CLIENTS", redis.get("clients"))


        # List logic
        redis.lpush("langs", language)

        # redis.sadd("languages", language)
        print("Current languages", redis.smembers("languages"))

        # langs = redis.smembers("languages")

        while num_connected != 2:
            num_connected = redis.get("clients")
            num_connected = int(num_connected.decode("utf-8"))

            time.sleep(.5)
            print("waiting for other client in /connect. Currently have: ", num_connected)

        langs = []
        lang_arr = redis.lrange("langs", 0, redis.llen("langs"))

        for lang in lang_arr:
            if not isinstance(lang, str):
                lang_key = lang.decode("utf-8")
            else:
                lang_key = lang

            langs.append(lang_key)

    except Exception as err:
        print("IN EXCEPT")
        langs = []
        lang_arr = redis.lrange("langs", 0, redis.llen("langs"))

        for lang in lang_arr:
            if not isinstance(lang, str):
                lang_key = lang.decode("utf-8")
            else:
                lang_key = lang

            langs.append(lang_key)

    print("Language list currently contains: ", langs)
    return jsonify(langs)


@app.route('/disconnect')
def disconnect():
    lang = request.args.get('lang')
    print("Disconnecting with lang: ", lang)

    num_connected = redis.get("clients")
    num_connected = int(num_connected.decode("utf-8"))
    redis.set("clients", num_connected - 1)
    print("PRINTING CLIENTS", redis.get("clients"))

    redis.lrem("langs", 1, lang)
    print("Current languages", redis.lrange("langs", 0, redis.llen("langs")))
    return jsonify("HELLO")


@app.route('/reset')
def reset():
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    redis.set("clients", 0)
    print("PRINTING CLIENTS", redis.get("clients"))

    redis.delete("languages")
    redis.delete("langs")
    print("PRINTING CLIENTS", redis.smembers("languages"))

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


@sockets.route('/interruptions')
def socket_monitor(ws):
    """Pushes message to clients when there is a disconnection"""
    print("In socket monitor")
    connection_montior.register(ws)

    while not ws.closed:
        gevent.sleep(1)
