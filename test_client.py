import socket
import threading

host = "wss://translation-backend.herokuapp.com"
# host = "localhost"
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((host, 50000))

print("Send messages to other client")


def receive_and_print():
    for message in iter(lambda: s.recv(1024).decode(), ''):
        print(message)


receiving_thread = threading.Thread(target=receive_and_print)
receiving_thread.start()

while True:
    inp = input(">")
    byt_msg = inp.encode()
    s.sendall(byt_msg)
