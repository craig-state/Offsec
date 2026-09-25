import socket

def send_file():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 9000))
    server_socket.listen(1)
    print('Listening on port 9000')

    conn, addr = server_socket.accept()
    print(f'Connection from {addr}')

    with open('chromelevator_x64.exe', 'rb') as f:
        data = f.read()  # Read entire file at once
        conn.sendall(data)  # Send all data in one call

    conn.close()
    server_socket.close()

if __name__ == '__main__':
    send_file()
