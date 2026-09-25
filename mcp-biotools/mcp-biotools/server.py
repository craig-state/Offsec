#!/usr/bin/env python3
"""BioGenAI BioTools MCP Server - Data platform tooling for the bio team.

Provides dataset browsing, querying, cross-dataset search, experiment
tracking, and reporting tools via the Model Context Protocol (MCP).

Usage:
    python server.py

Configuration:
    Set environment variables to override defaults (see biotools/config.py):
    - BIOTOOLS_WAREHOUSE_HOST: Data warehouse hostname
    - BIOTOOLS_LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
    - BIOTOOLS_MAX_QUERY_ROWS: Maximum rows returned per query
"""
import json
import logging
import sys
import os

# Ensure biotools package is importable from the server directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from biotools import __version__
from biotools.config import settings
from biotools.datasets import list_all, get_dataset, get_schema, DATASET_REGISTRY
from biotools.warehouse import get_client
from biotools.search import get_engine
from biotools.experiments import list_experiments, get_experiment

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("biotools.server")

mcp = FastMCP("BioGenAI BioTools")


# ---- Dataset tools ----

@mcp.tool()
def list_datasets() -> str:
    """List all available datasets in the BioGenAI data warehouse.

    Returns a JSON array of dataset objects with name, record count,
    size, owner, classification level, and description.
    """
    logger.info("Listing all datasets")
    return json.dumps(list_all(), indent=2)


@mcp.tool()
def get_dataset_schema(dataset_name: str) -> str:
    """Get the column schema for a specific dataset.

    Args:
        dataset_name: Name of the dataset (from list_datasets)

    Returns:
        JSON array of column definitions with name, type, and description.
    """
    logger.info("Getting schema for dataset: %s", dataset_name)
    schema = get_schema(dataset_name)
    if schema is None:
        available = ", ".join(DATASET_REGISTRY.keys())
        return json.dumps({"error": f"Dataset \'{dataset_name}\' not found. Available: {available}"})
    return json.dumps({
        "dataset": dataset_name,
        "column_count": len(schema),
        "columns": schema,
    }, indent=2)


@mcp.tool()
def query_data(dataset_name: str, query: str) -> str:
    """Query a specific dataset with a natural language or SQL-like search.

    Args:
        dataset_name: Name of the dataset to query (from list_datasets)
        query: Natural language query to filter/search the data

    Returns:
        Summary of matching records including count, execution time,
        and columns returned.
    """
    logger.info("Querying dataset %s: %s", dataset_name, query[:100])
    client = get_client()
    result = client.query(dataset_name, query)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_dataset_stats(dataset_name: str) -> str:
    """Get storage and usage statistics for a dataset.

    Args:
        dataset_name: Name of the dataset

    Returns:
        JSON object with record count, size, last refresh time,
        average query time, and query volume.
    """
    logger.info("Getting stats for dataset: %s", dataset_name)
    client = get_client()
    stats = client.get_table_stats(dataset_name)
    if stats is None:
        available = ", ".join(DATASET_REGISTRY.keys())
        return json.dumps({"error": f"Dataset \'{dataset_name}\' not found. Available: {available}"})
    return json.dumps(stats, indent=2)


# ---- Search tools ----

@mcp.tool()
def search_across_datasets(query: str, dataset_filter: str = "") -> str:
    """Search across all datasets for matching records.

    Performs full-text search across the entire data warehouse and returns
    results ranked by relevance score.

    Args:
        query: Search query string (e.g., "BRCA1 mutation", "phase 3 trial")
        dataset_filter: Optional dataset name to restrict search to a single dataset

    Returns:
        JSON object with total hits, matched datasets, and per-dataset results
        with relevance scores.
    """
    logger.info("Cross-dataset search: %s (filter=%s)", query[:100], dataset_filter or "none")
    engine = get_engine()
    ds_filter = dataset_filter if dataset_filter else None
    results = engine.search(query, dataset_filter=ds_filter)
    return json.dumps(results, indent=2)


# ---- Experiment tracking tools ----

@mcp.tool()
def list_running_experiments(status: str = "") -> str:
    """List ML experiments tracked in the BioGenAI experiment registry.

    Args:
        status: Filter by status: "running", "completed", "failed", "queued".
                Leave empty to list all experiments.

    Returns:
        JSON array of experiment summaries with ID, name, status, owner,
        and current metrics (for running experiments).
    """
    logger.info("Listing experiments (status=%s)", status or "all")
    status_filter = status if status else None
    experiments = list_experiments(status_filter=status_filter)
    return json.dumps(experiments, indent=2)


@mcp.tool()
def get_experiment_details(experiment_id: str) -> str:
    """Get detailed information about a specific ML experiment.

    Args:
        experiment_id: Experiment identifier (e.g., "EXP-2024-0142")

    Returns:
        JSON object with full experiment details including model,
        dataset, metrics, GPU assignment, and timing.
    """
    logger.info("Getting experiment details: %s", experiment_id)
    details = get_experiment(experiment_id)
    return json.dumps(details, indent=2)


# ---- Server info ----

@mcp.tool()
def server_info() -> str:
    """Get BioTools MCP server version and configuration summary.

    Returns server version, connection status, and non-sensitive
    configuration parameters.
    """
    return json.dumps({
        "server": "BioGenAI BioTools",
        "version": __version__,
        "config": settings.summary(),
        "datasets_registered": len(DATASET_REGISTRY),
        "status": "operational",
    }, indent=2)


if __name__ == "__main__":
    logger.info("Starting BioGenAI BioTools MCP Server v%s", __version__)
    config_warnings = settings.validate()
    for w in config_warnings:
        logger.warning("Config: %s", w)
    mcp.run()
