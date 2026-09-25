"""Unit tests for the cross-dataset search engine."""
from biotools.search import SearchEngine, get_engine


class TestSearchEngine:
    def test_search_returns_results(self):
        engine = SearchEngine()
        engine.load_index()
        results = engine.search("BRCA1 mutation")
        assert results["total_hits"] > 0
        assert results["datasets_matched"] > 0

    def test_search_with_filter(self):
        engine = SearchEngine()
        engine.load_index()
        results = engine.search("mutation", dataset_filter="genomics_2024.csv")
        assert results["datasets_matched"] <= 1
        if results["datasets_matched"] == 1:
            assert results["results"][0]["dataset"] == "genomics_2024.csv"

    def test_search_deterministic(self):
        engine = SearchEngine()
        engine.load_index()
        r1 = engine.search("test query")
        r2 = engine.search("test query")
        assert r1["total_hits"] == r2["total_hits"]

    def test_singleton_engine(self):
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2
