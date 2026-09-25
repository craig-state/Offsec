# MCP Playwright Server

Browser automation MCP server for the QA team. Provides page navigation, content extraction, and link analysis tools for AI-driven testing workflows.

## Usage

```bash
# MCP mode (stdio — used by MCP clients)
python3 server.py

# Standalone mode (for manual testing)
python3 server.py --standalone http://192.168.50.20/users/sign_in

# Client
python3 client.py http://192.168.50.20/users/sign_in
```

## Tools

| Name | Description |
|------|-------------|
| `navigate` | Navigate to a URL and extract page content, title, and links |
| `get_title` | Get the title of a web page |
| `extract_links` | Extract all links from a page |

## Requirements

Python 3.10+ (stdlib only, no external dependencies).

## Maintainers

- daniel.schneider@biogenai.corp
- verena.smith@biogenai.corp
