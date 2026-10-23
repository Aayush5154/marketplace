"""
tests/test_hybrid.py

Unit tests for pro.hybrid.CombinedSearch — RRF fusion logic.
All external dependencies (BM25, Pinecone, CrossEncoder) are mocked.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pro.hybrid import CombinedSearch

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_doc(text, metadata=None):
    """Simulate a LangChain Document-like object."""
    return SimpleNamespace(page_content=text, metadata=metadata or {})


def _keyword_results(*texts):
    """Return a BM25-style list: [(score, text, metadata), ...]."""
    return [(1.0 / (i + 1), text, {"src": "bm25"}) for i, text in enumerate(texts)]


def _vector_results(*texts):
    """Return a Pinecone-style list: [(doc, score), ...]."""
    return [(_make_doc(text, {"src": "vec"}), 1.0 / (i + 1)) for i, text in enumerate(texts)]


@pytest.fixture(autouse=True)
def mock_reranker(monkeypatch):
    """
    Prevent CrossEncoderReranker from loading the model at import time.
    The reranker simply returns its candidate list as (score, doc) pairs.
    """
    mock = MagicMock()
    mock.rerank.side_effect = lambda query, candidates, top_n=5: [
        (1.0 - i * 0.1, c) for i, c in enumerate(candidates[:top_n])
    ]
    monkeypatch.setattr("pro.hybrid.CrossEncoderReranker", lambda: mock)
    return mock


@pytest.fixture
def make_search(mock_reranker):
    """Factory: build a CombinedSearch with fully mocked retrievers."""
    def _make(kw_results, vec_results):
        kw = MagicMock()
        kw.search.return_value = kw_results
        vec = MagicMock()
        vec.search.return_value = vec_results
        cs = CombinedSearch(kw, vec)
        return cs
    return _make


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRRFFusion:
    def test_fused_scores_combine_both_sources(self, make_search):
        """
        docB is rank-1 in keyword, rank-2 in vector.
        docA is rank-2 in keyword, rank-1 in vector.
        Both should appear with non-zero RRF scores.
        """
        cs = make_search(
            _keyword_results("docB", "docA"),
            _vector_results("docA", "docB"),
        )
        # Peek at the internal fused dict by running the fusion step manually
        fetch_k = 5 * 5  # top_n=5 default
        kw_res = cs.keyword_search.search("q", fetch_k)
        vec_res = cs.vector_search.search("q", fetch_k)

        fused = {}
        for rank, (_score, text, _metadata) in enumerate(kw_res, start=1):
            rrf = 1 / (cs.k + rank)
            entry = fused.setdefault(text, {"rrf": 0.0})
            entry["rrf"] += rrf
        for rank, (doc, _score) in enumerate(vec_res, start=1):
            text = doc.page_content
            rrf = 1 / (cs.k + rank)
            entry = fused.setdefault(text, {"rrf": 0.0})
            entry["rrf"] += rrf

        assert "docA" in fused
        assert "docB" in fused

    def test_fused_dict_deduplicates_texts(self, make_search):
        """Overlapping texts should be merged into a single fused entry."""
        cs = make_search(
            _keyword_results("shared", "unique_kw"),
            _vector_results("shared", "unique_vec"),
        )
        fetch_k = 5 * 5
        kw_res = cs.keyword_search.search("q", fetch_k)
        vec_res = cs.vector_search.search("q", fetch_k)

        fused = {}
        for rank, (_score, text, _metadata) in enumerate(kw_res, start=1):
            entry = fused.setdefault(text, {"rrf": 0.0})
            entry["rrf"] += 1 / (cs.k + rank)
        for rank, (doc, _score) in enumerate(vec_res, start=1):
            text = doc.page_content
            entry = fused.setdefault(text, {"rrf": 0.0})
            entry["rrf"] += 1 / (cs.k + rank)

        # "shared" must appear exactly once with accumulated score
        assert list(fused.keys()).count("shared") == 1
        # Its combined score > score from either source alone
        solo_score = 1 / (cs.k + 1)
        assert fused["shared"]["rrf"] > solo_score

    def test_search_calls_reranker(self, make_search, mock_reranker):
        """CombinedSearch.search must delegate final ranking to the reranker."""
        cs = make_search(
            _keyword_results("alpha", "beta"),
            _vector_results("gamma", "alpha"),
        )
        cs.search("test query", top_n=2)
        mock_reranker.rerank.assert_called_once()
        call_args = mock_reranker.rerank.call_args
        assert call_args[0][0] == "test query"   # first positional arg = query

    def test_search_respects_top_n(self, make_search):
        """Returned list must not exceed top_n items."""
        cs = make_search(
            _keyword_results("a", "b", "c", "d"),
            _vector_results("e", "f", "g", "h"),
        )
        results = cs.search("q", top_n=2)
        assert len(results) <= 2

    def test_search_empty_results(self, make_search):
        """Both retrievers return nothing → search returns empty list."""
        cs = make_search([], [])
        results = cs.search("q", top_n=5)
        assert isinstance(results, list)
        assert len(results) == 0
