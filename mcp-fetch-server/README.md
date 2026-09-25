# MCP Fetch Server

Internal MCP server for URL content retrieval. Used by the DevOps team for automated portal monitoring and content verification.

## Usage

```bash
# MCP mode (stdio — used by MCP clients)
python3 server.py

# Standalone mode (for manual testing)
python3 server.py --standalone https://example.com

# Client
python3 client.py http://192.168.50.20/users/sign_in
```

## Tool

| Name | Description |
|------|-------------|
| `fetch` | Fetch URL content. Strips HTML boilerplate and returns clean text. |

## Requirements

Python 3.10+ (stdlib only, no external dependencies).

## Maintainers

- amy.fernandez@biogenai.corp
- felix.hernandez@biogenai.corp
