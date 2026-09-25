#!/usr/bin/env python3
"""Simple MCP client for the fetch server.
Connects to server.py via stdio and calls the fetch tool.

Usage:
    python3 client.py http://192.168.50.20/users/sign_in
    python3 client.py https://example.com
"""
import subprocess
import json
import sys
import os

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")


def call_fetch(url):
    """Start the MCP server and call the fetch tool."""
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Initialize
    init_req = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05",
                   "clientInfo": {"name": "mcp-client", "version": "1.0"}}
    })
    proc.stdin.write(init_req + "\n")
    proc.stdin.flush()
    init_resp = proc.stdout.readline()

    # Send initialized notification
    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0", "method": "notifications/initialized"
    }) + "\n")
    proc.stdin.flush()

    # Call fetch tool
    fetch_req = json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "fetch", "arguments": {"url": url}}
    })
    proc.stdin.write(fetch_req + "\n")
    proc.stdin.flush()
    fetch_resp = json.loads(proc.stdout.readline())

    proc.terminate()

    # Extract content
    result = fetch_resp.get("result", {})
    content = result.get("content", [{}])[0].get("text", "{}")
    return json.loads(content)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.50.20/users/sign_in"
    print(f"[*] Fetching {url} via MCP fetch server...")
    result = call_fetch(url)
    if "error" in result:
        print(f"[-] Error: {result['error']}")
    else:
        print(f"[+] Status: {result['status']}")
        print(f"[+] Type: {result['content_type']}")
        print(f"---")
        print(result['content'][:500])
