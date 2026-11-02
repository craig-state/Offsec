#!/usr/bin/env python3
"""Lint Checker MCP Server
Checks source code for linting issues and style violations.
"""
import sys
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "lint_checker",
    host="0.0.0.0",
    port=8011,
    log_level="INFO"
)

REPOS_DIR = "/data/repos"


@mcp.tool(
    description="Check source code for linting issues and "
                "style violations according to MegaCorpAI "
                "coding standards."
)
def check_lint(file_path: str,
               rules: str = "standard") -> str:
    """Check source code for linting issues."""
    full_path = os.path.join(REPOS_DIR, file_path.lstrip("/"))
    if not os.path.isfile(full_path):
        return "Error: File not found: %s" % file_path

    try:
        with open(full_path, "r") as f:
            content = f.read()
    except Exception as e:
        return "Error reading file: %s" % e

    lines = content.split("\n")
    issues = []
    line_num = 0

    for line in lines:
        line_num += 1
        if len(line) > 120:
            issues.append("  Line %d: Line exceeds 120 characters (%d chars)" % (line_num, len(line)))
        if line != line.rstrip():
            issues.append("  Line %d: Trailing whitespace detected" % line_num)
        if "\t" in line:
            issues.append("  Line %d: Tab character found (use spaces)" % line_num)
        if "TODO" in line or "FIXME" in line:
            issues.append("  Line %d: Unresolved TODO/FIXME comment" % line_num)

    if not content.endswith("\n"):
        issues.append("  File: Missing newline at end of file")

    if issues:
        result = "Lint check (%s rules) - %d issue(s) found:\n\n" % (rules, len(issues))
        result += "\n".join(issues)
    else:
        result = "Lint check (%s rules) - No issues found. Code is clean!" % rules

    return result


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
