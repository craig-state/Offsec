"""Configuration management for BioTools MCP server."""
import os
import logging

logger = logging.getLogger("biotools")


class Settings:
    """Server configuration loaded from environment variables with sensible defaults."""

    WAREHOUSE_HOST: str = os.environ.get("BIOTOOLS_WAREHOUSE_HOST", "warehouse.internal.biogenai.corp")
    WAREHOUSE_PORT: int = int(os.environ.get("BIOTOOLS_WAREHOUSE_PORT", "5432"))
    WAREHOUSE_DB: str = os.environ.get("BIOTOOLS_WAREHOUSE_DB", "biodata")
    WAREHOUSE_USER: str = os.environ.get("BIOTOOLS_WAREHOUSE_USER", "biotools_svc")
    WAREHOUSE_PASSWORD: str = os.environ.get("BIOTOOLS_WAREHOUSE_PASSWORD", "")

    SEARCH_INDEX_PATH: str = os.environ.get("BIOTOOLS_SEARCH_INDEX", "/var/lib/biotools/search_index")
    EXPORT_DIR: str = os.environ.get("BIOTOOLS_EXPORT_DIR", "/tmp/biotools_exports")

    MAX_QUERY_ROWS: int = int(os.environ.get("BIOTOOLS_MAX_QUERY_ROWS", "10000"))
    QUERY_TIMEOUT_SECONDS: int = int(os.environ.get("BIOTOOLS_QUERY_TIMEOUT", "30"))

    LOG_LEVEL: str = os.environ.get("BIOTOOLS_LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of configuration warnings."""
        warnings = []
        if not cls.WAREHOUSE_PASSWORD:
            warnings.append("BIOTOOLS_WAREHOUSE_PASSWORD not set; using empty password")
        if cls.MAX_QUERY_ROWS > 100000:
            warnings.append(f"MAX_QUERY_ROWS={cls.MAX_QUERY_ROWS} is very high; consider reducing")
        return warnings

    @classmethod
    def summary(cls) -> dict:
        """Return non-sensitive configuration summary."""
        return {
            "warehouse_host": cls.WAREHOUSE_HOST,
            "warehouse_port": cls.WAREHOUSE_PORT,
            "warehouse_db": cls.WAREHOUSE_DB,
            "search_index": cls.SEARCH_INDEX_PATH,
            "export_dir": cls.EXPORT_DIR,
            "max_query_rows": cls.MAX_QUERY_ROWS,
            "query_timeout_seconds": cls.QUERY_TIMEOUT_SECONDS,
            "log_level": cls.LOG_LEVEL,
        }


settings = Settings()
