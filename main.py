import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sockets import Sockets
from datetime import datetime
import time
import threading
import gevent
from googletrans import Translator
from redis.client import StrictRedis

REDIS_URL = os.getenv('REDIS_URL', "redis://localhost:6379")
REDIS_CHANNEL = "translation-room"

MAX_CLIENTS = 2  # 0 and 1
CLIENTS = 0

app = Flask(__name__)
CORS(app)
sockets = Sockets(app)

# POOL = redis.ConnectionPool(REDIS_URL, 6379)
# redis = redis.StrictRedis(POOL)

redis = StrictRedis.from_url(REDIS_URL)

chat_rooms = {}
connection_monitors = {}

# Redis var setup
num_clients = redis.get("clients")
if not num_clients:
    redis.set("clients", 0)


class TranslationAPI:
    def __init__(self):
        self.translator = Translator()

    def translate(self, user_id, message, src="Eng", dest="Span"):
        if not isinstance(message, str):
            message = message.decode("utf-8")

        # Check if ignore flag
        if "IGNORE" in message:
            return message

        # Remove prepended metadata
        lang_index = message.index(":") + 1
        message_index = message.index(":", lang_index) + 1

        # language = message[lang_index:message_index-1]
        message_content = message[message_index:]

        # print("GETTING preferred language for user: " + user_id)
        language = redis.get(user_id)
        # print(language)

        # print("Translating for langauge: ", language)
        # print(message_content)

        if not isinstance(language, str):
            language = language.decode("utf-8")

        translation = self.translator.translate(message_content, dest=language)

        # print("translated")
        translated_text = translation.text

        # Add metadata back in
        # print("adding preprend")
        final_message = message[:message_index] + translated_text

        # print("Translated: ", message, " to: ", final_message)
        return final_message


class ChatBackend:
    def __init__(self, chat_room_id=REDIS_CHANNEL):
        self.clients = []
        self.client_user_id_map = {}
        self.user_ids = []
        self.pubsub = redis.pubsub()
        self.pubsub.subscribe(chat_room_id)
        self.translation_api = TranslationAPI()
        self.clients_key = chat_room_id + "_clients"

    def __iter_data(self):
        for message in self.pubsub.listen():
            data = message.get('data')
            if message['type'] == 'message':
                app.logger.info(u'Sending message: {}'.format(data))
                yield data

    def register(self, client, user_id):
        """Register a WebSocket connection for Redis updates."""

        #  If this user exists already in this, remove them.
        if user_id in self.user_ids:
            inv_map = {v: k for k, v in self.client_user_id_map.items()}
            old_client = inv_map[user_id]

            try:
                print("Deleting subscription to chat room:" + str(self) + " for old client: " + str(old_client))
                self.clients.remove(old_client)
                del self.client_user_id_map[old_client]
            except Exception as e:
                print("unable to remove from class lists")
                print(e)
                print(str(self.clients))
                print(str(self.client_user_id_map))
                print(str(self.user_ids))
                print(str(self.user_id))

        self.user_ids.append(user_id)
        self.clients.append(client)
        self.client_user_id_map[client] = user_id

    def send(self, client, user_id, data):
        """Send given data to the registered client.
        Automatically discards invalid connections."""

        try:
            #  Initiate text-text translations
            translated_data = self.translation_api.translate(user_id, data)
            client.send(translated_data)
        except Exception as err:
            print(err)
            self.clients.remove(client)

    def run(self):
        """Listens for new messages in Redis, and sends them to clients."""
        for data in self.__iter_data():
            print("Chat room: " + str(self) + " received data: " + data.decode("utf-8") + " and has clients: " +
                  str(self.clients))

            for client in self.clients:
                user_id = self.client_user_id_map[client]

                if redis.get(user_id):
                    gevent.spawn(self.send, client, user_id, data)
                else:
                    print("remvoing client with user id: " + user_id)
                    self.clients.remove(client)

    def start(self):
        """Maintains Redis subscription in the background."""
        gevent.spawn(self.run)


class ConnectionMonitor:
    def __init__(self, clients_key="clients"):
        self.clients = []
        self.clients_key = clients_key

    def register(self, client):
        """Register a WebSocket connection for all socket connection updates"""
        self.clients.append(client)

    def send(self, client):
        """Send socket connection updates to clients"""
        try:
            num_connected = redis.get(self.clients_key)
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

    while not ws.closed:
        gevent.sleep(0.1)
        message = ws.receive()
        if message:
            if ":" in message:
                print("/submit received: " + message)
                room_index = message.rfind(":")

                room_id = message[room_index+1:]
                redis.publish(room_id, message[0:room_index])
            else:
                print("Incorrectly Formatted Message, ABORT")


def join_chat_room(chat_room_id, user_id, language):
    # Called if chat room exists locally
    chat_room_clients_key = chat_room_id + "_clients"
    chat_room_languages_list = chat_room_id + "_languages"

    if user_id is None:
        # Socket Reconnecting to get refreshed version of list of languages
        langs = []
        lang_arr = redis.lrange(chat_room_languages_list, 0, redis.llen(chat_room_languages_list))

        for lang in lang_arr:
            if not isinstance(lang, str):
                lang_key = lang.decode("utf-8")
            else:
                lang_key = lang

            langs.append(lang_key)
        return jsonify(langs)

    # Join chat room
    num_connected = redis.get(chat_room_clients_key)
    num_connected = int(num_connected.decode("utf-8"))
    redis.set(chat_room_clients_key, num_connected + 1)

    # List logic
    redis.lpush(chat_room_languages_list, language)

    # while num_connected < 2:
    #     num_connected = redis.get(chat_room_clients_key)
    #     num_connected = int(num_connected.decode("utf-8"))
    #
    #     print("waiting for other client in /connect. Currently have: ", num_connected)
    #     gevent.sleep(0.5)

    langs = []
    lang_arr = redis.lrange(chat_room_languages_list, 0, redis.llen(chat_room_languages_list))

    for lang in lang_arr:
        if not isinstance(lang, str):
            lang_key = lang.decode("utf-8")
        else:
            lang_key = lang

        langs.append(lang_key)

    return langs


def create_chat_room(chat_room_id, user_id, language):
    print("Request to join chat room: " + chat_room_id)

    redis.lpush("chat_rooms", chat_room_id)

    chat_room_clients_key = chat_room_id + "_clients"
    chat_room_languages_list = chat_room_id + "_languages"

    if user_id is None:
        # Socket Reconnecting to get refreshed version of list of languages
        langs = []
        lang_arr = redis.lrange(chat_room_languages_list, 0, redis.llen(chat_room_languages_list))

        for lang in lang_arr:
            if not isinstance(lang, str):
                lang_key = lang.decode("utf-8")
            else:
                lang_key = lang

            langs.append(lang_key)
        return jsonify(langs)

    # Create or update entry in redis map with clients for this chat room
    chat_clients = redis.get(chat_room_clients_key)
    if not chat_clients:
        redis.set(chat_room_clients_key, 0)

    # Creating Chat Room
    chat_room = ChatBackend(chat_room_id)
    chat_room.start()
    chat_rooms[chat_room_id] = chat_room
    print("Created chat room: " + str(chat_room) + " with room ID: " + chat_room_id)

    # Creating Connection Monitor
    room_connection_monitor = ConnectionMonitor(chat_room_clients_key)
    room_connection_monitor.start()
    connection_monitors[chat_room_id] = room_connection_monitor
    print("Created room connection monitor: " + str(room_connection_monitor) + " for room ID: " + chat_room_id)

    # Join chat room
    num_connected = redis.get(chat_room_clients_key)
    num_connected = int(num_connected.decode("utf-8"))
    redis.set(chat_room_clients_key, num_connected + 1)

    # List logic
    redis.lpush(chat_room_languages_list, language)

    # while num_connected < 2:
    #     num_connected = redis.get(chat_room_clients_key)
    #     num_connected = int(num_connected.decode("utf-8"))
    #
    #     print("waiting for other client in /connect. Currently have: ", num_connected)
    #     gevent.sleep(0.5)

    langs = []
    lang_arr = redis.lrange(chat_room_languages_list, 0, redis.llen(chat_room_languages_list))

    for lang in lang_arr:
        if not isinstance(lang, str):
            lang_key = lang.decode("utf-8")
        else:
            lang_key = lang

        langs.append(lang_key)

    return langs


@app.route('/connect')
def connect():
    language = request.args.get('lang')
    roomID = request.args.get('roomID')
    id = request.args.get('id')

    chat_room_languages_list = roomID + "_languages"

    if id is None:
        # Socket Reconnecting to get refreshed version of list of languages
        langs = []
        lang_arr = redis.lrange(chat_room_languages_list, 0, redis.llen(chat_room_languages_list))

        for lang in lang_arr:
            if not isinstance(lang, str):
                lang_key = lang.decode("utf-8")
            else:
                lang_key = lang

            langs.append(lang_key)
        return jsonify(langs)

    user_id = id[0:len(id)-1]  # Removing :
    redis.set(user_id, language)

    # Join Chat Room
    all_chat_rooms = redis.lrange("chat_rooms", 0, redis.llen("chat_rooms"))
    byte_roomID = roomID.encode("utf-8")

    if byte_roomID in all_chat_rooms:
        # Exists
        print("Chat room with ID: " + roomID + " exists in redis")

        if roomID in chat_rooms:
            print("Chat room object with ID: " + roomID + "exists locally")
            languages = join_chat_room(roomID, id, language)
        else:
            print("Chat room object with ID: " + roomID + "does not exist locally")
            languages = create_chat_room(roomID, id, language)
    else:
        print("Chat room with ID: " + roomID + " doesn't exist")
        languages = create_chat_room(roomID, id, language)

    print("Chatrooms that currently exist on this server: " + str(chat_rooms))
    return jsonify(languages)


@app.route('/disconnect')
def disconnect():
    lang = request.args.get('lang')
    chat_room_id = request.args.get('roomID')
    user_id = request.args.get('userID')

    print("Disconnecting with lang: ", lang)

    chat_room_clients_key = chat_room_id + "_clients"

    num_connected = redis.get(chat_room_clients_key)
    num_connected = int(num_connected.decode("utf-8"))

    redis.set(chat_room_clients_key, num_connected - 1)
    redis.delete(user_id)

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
    input = ""
    while not ws.closed and input == "":
        gevent.sleep(0.1)
        input = ws.receive()

    colon_index = input.find(":")
    room_id = input[0:colon_index]
    user_id = input[colon_index+1:len(input)-1]

    print("In /receive for user id: " + user_id + "and client: " + str(ws))
    # get chat object from redis
    chat_room = chat_rooms[room_id]
    print(user_id + " found chat room: " + str(chat_room))

    # ALSO need to sent chat room to this socket and then if it doesnt exist create it
    chat_room.register(ws, user_id)

    while not ws.closed:
        gevent.sleep(0.1)


@sockets.route('/test')
def socket_test(ws):
    print("In test")
    lang = ws.receive()
    print(lang)


@sockets.route('/interruptions')
def socket_monitor(ws):
    """Pushes message to clients when there is a disconnection"""
    room_id = ws.receive()

    # Only current server will have this value
    connection_monitor = connection_monitors[room_id]
    print("Found connection_monitor: " + str(connection_monitor))

    connection_monitor.register(ws)

    while not ws.closed:
        gevent.sleep(1)
