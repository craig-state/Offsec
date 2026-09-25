# BioGenAI BioTools MCP Server

Internal MCP server providing data platform tools for the BioGenAI bio team. Connects to the data warehouse and exposes commonly used datasets, search, and experiment tracking through a standardized tool interface.

## Quick Start

```bash
pip install -r requirements.txt
python server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `list_datasets` | List all datasets with record counts, sizes, and classifications |
| `get_dataset_schema` | Get column definitions for a specific dataset |
| `query_data` | Query a dataset with natural language or SQL-like search |
| `get_dataset_stats` | Get storage, usage, and performance statistics |
| `search_across_datasets` | Full-text search across all datasets with relevance ranking |
| `list_running_experiments` | List ML experiments with status and metrics |
| `get_experiment_details` | Get full details for a specific experiment |
| `server_info` | Server version and configuration summary |

## Configuration

The server is configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BIOTOOLS_WAREHOUSE_HOST` | `warehouse.internal.biogenai.corp` | Data warehouse hostname |
| `BIOTOOLS_WAREHOUSE_PORT` | `5432` | Data warehouse port |
| `BIOTOOLS_WAREHOUSE_DB` | `biodata` | Database name |
| `BIOTOOLS_LOG_LEVEL` | `INFO` | Logging level |
| `BIOTOOLS_MAX_QUERY_ROWS` | `10000` | Maximum rows per query |
| `BIOTOOLS_QUERY_TIMEOUT` | `30` | Query timeout in seconds |

## MCP Client Configuration

Add to your MCP client (Claude Desktop, VS Code, or custom agent):

```json
{
    "mcpServers": {
        "biotools": {
            "command": "C:\\Python311\\python.exe",
            "args": ["C:\\Users\\nina.seyfried\\mcp-servers\\mcp-biotools\\server.py"],
            "env": {
                "BIOTOOLS_LOG_LEVEL": "WARNING"
            }
        }
    }
}
```

## Project Structure

```
mcp-biotools/
\u251c\u2500\u2500 server.py                  # MCP server entry point
\u251c\u2500\u2500 biotools/
\u2502   \u251c\u2500\u2500 __init__.py
\u2502   \u251c\u2500\u2500 config.py            # Environment-based configuration
\u2502   \u251c\u2500\u2500 datasets.py          # Dataset registry and metadata
\u2502   \u251c\u2500\u2500 warehouse.py         # Data warehouse connector
\u2502   \u251c\u2500\u2500 search.py            # Cross-dataset search engine
\u2502   \u2514\u2500\u2500 experiments.py       # Experiment tracking integration
\u251c\u2500\u2500 tests/
\u2502   \u251c\u2500\u2500 test_datasets.py
\u2502   \u251c\u2500\u2500 test_warehouse.py
\u2502   \u2514\u2500\u2500 test_search.py
\u251c\u2500\u2500 Dockerfile
\u251c\u2500\u2500 .gitlab-ci.yml
\u251c\u2500\u2500 requirements.txt
\u2514\u2500\u2500 requirements-dev.txt
```

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
ruff check biotools/ server.py
```

## Docker

```bash
docker build -t biotools-mcp .
docker run -it biotools-mcp
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
