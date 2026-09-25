"""Full-text search engine for cross-dataset sample discovery.

Provides unified search across all registered datasets. In production,
this uses an Elasticsearch backend. For the MCP server, results are
simulated from the dataset registry.
"""
import hashlib
import logging
from typing import Optional

from biotools.datasets import DATASET_REGISTRY

logger = logging.getLogger("biotools.search")


class SearchEngine:
    """Cross-dataset search engine."""

    def __init__(self):
        self._index_loaded = False

    def load_index(self) -> None:
        """Load the search index from disk or rebuild from warehouse."""
        logger.info("Loading search index...")
        self._index_loaded = True

    def search(
        self,
        query: str,
        dataset_filter: Optional[str] = None,
        max_results: int = 50,
    ) -> dict:
        """Search across datasets for matching records.

        Args:
            query: Search query string
            dataset_filter: Optional dataset name to restrict search to
            max_results: Maximum number of results to return

        Returns:
            Dict with search results and relevance scores
        """
        if not self._index_loaded:
            self.load_index()

        results = []
        query_hash = hashlib.sha256(query.encode()).hexdigest()

        datasets_to_search = DATASET_REGISTRY
        if dataset_filter and dataset_filter in DATASET_REGISTRY:
            datasets_to_search = {dataset_filter: DATASET_REGISTRY[dataset_filter]}

        for ds_name, ds_info in datasets_to_search.items():
            combined = f"{ds_name}:{query}"
            h = hashlib.sha256(combined.encode()).hexdigest()
            hit_count = int(h[:4], 16) % min(ds_info["records"], 200)

            if hit_count > 0:
                relevance = round((int(h[4:8], 16) % 80 + 20) / 100.0, 2)
                results.append({
                    "dataset": ds_name,
                    "hits": hit_count,
                    "relevance_score": relevance,
                    "owner": ds_info["owner"],
                    "classification": ds_info["classification"],
                    "top_columns": [c["name"] for c in ds_info["columns"][:3]],
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:max_results]

        return {
            "query": query,
            "total_hits": sum(r["hits"] for r in results),
            "datasets_matched": len(results),
            "results": results,
        }


# Module-level singleton
_engine: Optional[SearchEngine] = None


def get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        _engine = SearchEngine()
        _engine.load_index()
    return _engine
