"""Unit tests for the warehouse connector."""
import pytest
from biotools.warehouse import WarehouseClient, get_client


class TestWarehouseClient:
    def test_connect(self):
        client = WarehouseClient()
        assert client.connect() is True

    def test_query_existing_dataset(self):
        client = WarehouseClient()
        client.connect()
        result = client.query("genomics_2024.csv", "BRCA1 mutations")
        assert "matching_records" in result
        assert result["matching_records"] > 0
        assert result["dataset"] == "genomics_2024.csv"

    def test_query_nonexistent_dataset(self):
        client = WarehouseClient()
        client.connect()
        result = client.query("nonexistent.csv", "test")
        assert "error" in result

    def test_query_deterministic(self):
        client = WarehouseClient()
        client.connect()
        r1 = client.query("genomics_2024.csv", "BRCA1")
        r2 = client.query("genomics_2024.csv", "BRCA1")
        assert r1["matching_records"] == r2["matching_records"]

    def test_table_stats(self):
        client = WarehouseClient()
        client.connect()
        stats = client.get_table_stats("protein_structures.parquet")
        assert stats is not None
        assert "total_records" in stats
        assert "size_mb" in stats

    def test_singleton_client(self):
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2
