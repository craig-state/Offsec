"""Data warehouse connector for the BioGenAI data platform.

In production this connects to the PostgreSQL-based warehouse via psycopg2.
For the MCP server, queries are simulated using deterministic hashing to
produce realistic-looking result counts and summaries without requiring a
live database connection.
"""
import hashlib
import logging
from typing import Optional

from biotools.config import settings
from biotools.datasets import get_dataset, DATASET_REGISTRY

logger = logging.getLogger("biotools.warehouse")


class WarehouseClient:
    """Client for the BioGenAI data warehouse."""

    def __init__(self):
        self._connected = False
        self._host = settings.WAREHOUSE_HOST
        self._port = settings.WAREHOUSE_PORT

    def connect(self) -> bool:
        """Establish connection to the warehouse. Returns True on success."""
        try:
            logger.info("Connecting to warehouse at %s:%d", self._host, self._port)
            # In production: psycopg2.connect(...)
            # For MCP server: simulate connection
            self._connected = True
            return True
        except Exception as e:
            logger.error("Failed to connect to warehouse: %s", e)
            self._connected = False
            return False

    def query(self, dataset_name: str, query_text: str, limit: Optional[int] = None) -> dict:
        """Execute a query against a dataset.

        Args:
            dataset_name: Target dataset name
            query_text: Natural language or SQL-like query
            limit: Maximum rows to return (defaults to settings.MAX_QUERY_ROWS)

        Returns:
            Dict with query results summary
        """
        if limit is None:
            limit = settings.MAX_QUERY_ROWS

        ds = get_dataset(dataset_name)
        if ds is None:
            available = ", ".join(DATASET_REGISTRY.keys())
            return {
                "error": f"Dataset \'{dataset_name}\' not found",
                "available_datasets": available,
            }

        # Deterministic result count based on query hash
        query_hash = hashlib.sha256(f"{dataset_name}:{query_text}".encode()).hexdigest()
        match_count = int(query_hash[:6], 16) % ds["records"]
        match_count = max(1, min(match_count, limit))

        # Simulate query execution time
        exec_time_ms = (int(query_hash[6:10], 16) % 800) + 50

        return {
            "dataset": dataset_name,
            "query": query_text,
            "total_records": ds["records"],
            "matching_records": match_count,
            "columns_returned": [c["name"] for c in ds["columns"]],
            "execution_time_ms": exec_time_ms,
            "truncated": match_count >= limit,
            "summary": f"Found {match_count:,} records matching \"{query_text}\" in {dataset_name}",
        }

    def get_table_stats(self, dataset_name: str) -> Optional[dict]:
        """Get storage and usage statistics for a dataset."""
        ds = get_dataset(dataset_name)
        if ds is None:
            return None

        name_hash = hashlib.md5(dataset_name.encode()).hexdigest()
        return {
            "dataset": dataset_name,
            "total_records": ds["records"],
            "size_mb": ds["size_mb"],
            "column_count": len(ds["columns"]),
            "last_refreshed": f"2024-{(int(name_hash[:2], 16) % 12) + 1:02d}-{(int(name_hash[2:4], 16) % 28) + 1:02d}T{int(name_hash[4:6], 16) % 24:02d}:00:00Z",
            "refresh_schedule": ds["refresh_schedule"],
            "owner": ds["owner"],
            "classification": ds["classification"],
            "avg_query_time_ms": (int(name_hash[6:10], 16) % 500) + 30,
            "queries_last_30d": (int(name_hash[10:14], 16) % 5000) + 100,
        }


# Module-level singleton
_client: Optional[WarehouseClient] = None


def get_client() -> WarehouseClient:
    """Get or create the warehouse client singleton."""
    global _client
    if _client is None:
        _client = WarehouseClient()
        _client.connect()
    return _client
