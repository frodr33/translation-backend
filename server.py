import select, socket, sys, queue, time
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setblocking(0)

print("setting up server")
server.bind(('localhost', 50000))
server.listen(5)
print("server listening on localhost:5000")

inputs = [server]  # All socket connections
clients = []  # Clients
outputs = []
message_queues = {}

server_full = False

while inputs:
    print("waiting for inputs")
    readable, writable, exceptional = select.select(
        inputs, outputs, inputs)
    for s in readable:
        if s is server:
            connection, client_address = s.accept()
            print("Base server is: ", s)
            print("Created TCP Socket Connection", connection, client_address)
            connection.setblocking(0)
            inputs.append(connection)
            clients.append(connection)
            message_queues[connection] = queue.Queue()
        else:
            if len(inputs) < 3:
               server_full = False
               continue
            elif len(inputs) == 3 and not server_full:
               server_full = True
               print("Both clients connected")


            # Both clients connected, redirect messages to each other
            data = s.recv(1024)
            if data:
                for i in range(0, len(clients)):
                    if clients[i] == s:
                         # Found this client connection
                         other_client = len(clients) - 1 - i

                other_connection = clients[other_client]

                message_queues[other_connection].put(data)
                if other_connection not in outputs:
                    outputs.append(other_connection)
            else:
                print("Disconnecting client: ", s)
                if s in outputs:
                    outputs.remove(s)
                inputs.remove(s)
                clients.remove(s)
                s.close()
                del message_queues[s]

    for s in writable:
        try:
            next_msg = message_queues[s].get_nowait()
        except queue.Empty:
            outputs.remove(s)
        else:
            s.send(next_msg)

    for s in exceptional:
        inputs.remove(s)
        if s in outputs:
            outputs.remove(s)
        s.close()
        del message_queues[s]
