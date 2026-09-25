import socket

def send_file():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 9000))
    server_socket.listen(1)
    print('Listening on port 9000')

    conn, addr = server_socket.accept()
    print(f'Connection from {addr}')

    with open('Chrome-App-Bound-Encryption-Decryption-main.zip', 'rb') as f:
        chunk = f.read(4096)
        while chunk:
            conn.sendall(chunk)
            chunk = f.read(4096)

    conn.close()
    server_socket.close()

if __name__ == '__main__':
    send_file()
