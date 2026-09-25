#!/usr/bin/env python3
"""MCP Playwright Client — connects to server.py and calls the navigate tool.

Usage:
    python3 client.py http://192.168.50.20/users/sign_in
    python3 client.py https://example.com
"""
import subprocess
import json
import sys
import os

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")


def call_navigate(url):
    """Start the MCP server and call the navigate tool."""
    proc = subprocess.Popen(
        [sys.executable, SERVER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Initialize
    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05",
                   "clientInfo": {"name": "playwright-client", "version": "1.0"}}
    }) + "\n")
    proc.stdin.flush()
    proc.stdout.readline()  # read init response

    # Initialized notification
    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0", "method": "notifications/initialized"
    }) + "\n")
    proc.stdin.flush()

    # Call navigate
    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "navigate", "arguments": {"url": url}}
    }) + "\n")
    proc.stdin.flush()

    resp_line = proc.stdout.readline()
    proc.terminate()

    resp = json.loads(resp_line)
    content_text = resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    return json.loads(content_text)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.50.20/users/sign_in"
    print(f"[*] Navigating to {url} via MCP Playwright server...")
    result = call_navigate(url)
    if "error" in result:
        print(f"[-] Error: {result['error']}")
    else:
        print(f"[+] Status: {result.get('status')}")
        print(f"[+] Title: {result.get('title', 'N/A')}")
        print(f"[+] Links: {len(result.get('links', []))}")
        print("---")
        print(result.get("text", "")[:500])
