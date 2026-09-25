"""Unit tests for the datasets module."""
import pytest
from biotools.datasets import get_dataset, list_all, get_schema, DATASET_REGISTRY


class TestDatasetRegistry:
    def test_list_all_returns_all_datasets(self):
        result = list_all()
        assert len(result) == len(DATASET_REGISTRY)

    def test_list_all_has_required_fields(self):
        for ds in list_all():
            assert "name" in ds
            assert "records" in ds
            assert "description" in ds
            assert "owner" in ds

    def test_get_existing_dataset(self):
        ds = get_dataset("genomics_2024.csv")
        assert ds is not None
        assert ds["records"] == 48_521
        assert ds["owner"] == "genomics-team"

    def test_get_nonexistent_dataset(self):
        assert get_dataset("nonexistent.csv") is None

    def test_get_schema_returns_columns(self):
        schema = get_schema("genomics_2024.csv")
        assert schema is not None
        assert len(schema) > 0
        assert all("name" in col and "type" in col for col in schema)

    def test_get_schema_nonexistent(self):
        assert get_schema("nonexistent.csv") is None

    @pytest.mark.parametrize("dataset_name", list(DATASET_REGISTRY.keys()))
    def test_all_datasets_have_columns(self, dataset_name):
        ds = get_dataset(dataset_name)
        assert "columns" in ds
        assert len(ds["columns"]) >= 1
