#!/usr/bin/env python3
"""Security Scanner MCP Server
Scans source code for common security vulnerabilities.
"""
import sys
import os
import re

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "security_scanner",
    host="0.0.0.0",
    port=8012,
    log_level="INFO"
)

REPOS_DIR = "/data/repos"


@mcp.tool(
    description="Scan source code for common security "
                "vulnerabilities including hardcoded secrets, "
                "injection risks, and insecure patterns."
)
def scan_security(file_path: str,
                  severity: str = "all") -> str:
    """Scan source code for security vulnerabilities."""
    full_path = os.path.join(REPOS_DIR, file_path.lstrip("/"))
    if not os.path.isfile(full_path):
        return "Error: File not found: %s" % file_path

    try:
        with open(full_path, "r") as f:
            content = f.read()
    except Exception as e:
        return "Error reading file: %s" % e

    lines = content.split("\n")
    findings = []
    line_num = 0

    for line in lines:
        line_num += 1
        if re.search(r"password\s*=\s*[\"\'\'][^\"\'\']+[\"\'\']", line, re.IGNORECASE):
            findings.append({"line": line_num, "severity": "HIGH",
                "type": "Hardcoded Secret",
                "message": "Hardcoded password detected."})
        if re.search(r"api[_-]?key\s*=\s*[\"\'\'][^\"\'\']+[\"\'\']", line, re.IGNORECASE):
            findings.append({"line": line_num, "severity": "HIGH",
                "type": "Hardcoded Secret",
                "message": "Hardcoded API key detected."})
        if "eval(" in line:
            findings.append({"line": line_num, "severity": "CRITICAL",
                "type": "Code Injection",
                "message": "Use of eval() detected."})

    if severity != "all":
        findings = [f for f in findings if f["severity"].lower() == severity.lower()]

    if findings:
        result = "Security scan - %d finding(s):\n\n" % len(findings)
        for f in findings:
            result += "  [%s] Line %d: %s\n    %s\n\n" % (
                f["severity"], f["line"], f["type"], f["message"])
    else:
        result = "Security scan - No vulnerabilities found."

    return result


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
