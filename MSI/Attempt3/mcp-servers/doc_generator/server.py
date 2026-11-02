#!/usr/bin/env python3
"""Documentation Generator MCP Server
Generates documentation for source code files.
"""
import sys
import os
import re

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "doc_generator",
    host="0.0.0.0",
    port=8013,
    log_level="INFO"
)

REPOS_DIR = "/data/repos"


@mcp.tool(
    description="Generate documentation for source code "
                "including function signatures, parameter "
                "descriptions, and usage examples."
)
def generate_docs(file_path: str,
                  format: str = "markdown") -> str:
    """Generate documentation for a source code file."""
    full_path = os.path.join(REPOS_DIR, file_path.lstrip("/"))
    if not os.path.isfile(full_path):
        return "Error: File not found: %s" % file_path

    try:
        with open(full_path, "r") as f:
            content = f.read()
    except Exception as e:
        return "Error reading file: %s" % e

    functions = re.findall(r"(?:def|function|func)\s+(\w+)\s*\(([^)]*)\)", content)
    classes = re.findall(r"(?:class)\s+(\w+)", content)
    imports = re.findall(r"(?:import|from|require|include)\s+(.+)", content)

    ext = os.path.splitext(file_path)[1]
    file_type = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".java": "Java", ".go": "Go", ".yml": "YAML Configuration",
        ".yaml": "YAML Configuration", ".json": "JSON Configuration",
        ".env": "Environment Configuration"
    }.get(ext, "Unknown")

    lines = content.split("\n")

    if format == "markdown":
        doc = "# Documentation: `%s`\n\n" % os.path.basename(file_path)
        doc += "**File type:** %s\n" % file_type
        doc += "**Lines:** %d\n\n" % len(lines)
        if imports:
            doc += "## Dependencies\n\n"
            for imp in imports[:10]:
                doc += "- `%s`\n" % imp.strip()
            doc += "\n"
        if classes:
            doc += "## Classes\n\n"
            for cls in classes:
                doc += "### `%s`\n\n" % cls
        if functions:
            doc += "## Functions\n\n"
            for name, params in functions:
                doc += "### `%s(%s)`\n\n" % (name, params)
                doc += "Parameters: %s\n\n" % (params if params else "None")
        if not functions and not classes:
            doc += "## Contents\n\n"
            doc += "Configuration file with %d lines.\n" % len(lines)
    else:
        doc = "Documentation for %s\n" % os.path.basename(file_path)
        doc += "Type: %s, Lines: %d\n" % (file_type, len(lines))

    return doc


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
