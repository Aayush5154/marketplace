from reranker import CrossEncoderReranker


class CombinedSearch:
    def __init__(self, keyword_search, vector_search):

        self.keyword_search = keyword_search
        self.vector_search = vector_search
        self.k = 60
        self.reranker = CrossEncoderReranker()

    def search(self, query, top_n=5):
        """
        Perform a combined search using both keyword-based and vector-based search,
        and return re-ranked results.

        Parameters:
        - query (str): The search query.
        - top_n (int): The number of top results to return.

        Returns:
        - list of tuple: (score, item) where item is a dict:
              {"text": str, "metadata": dict}
          carrying chunk_type / section / template_name etc. through to the caller.
        """
        fetch_k = top_n * 5

        # BM25 Results: (score, text, metadata)
        keyword_results = self.keyword_search.search(query, fetch_k)

        # Pinecone Results: (Document, score)
        semantic_results = self.vector_search.search(query, fetch_k)

        # text -> {"rrf": float, "metadata": dict}
        fused = {}

        # BM25 Ranking
        for rank, (score, text, metadata) in enumerate(keyword_results, start=1):
            rrf_score = 1 / (self.k + rank)
            entry = fused.setdefault(text, {"rrf": 0.0, "metadata": {}})
            entry["rrf"] += rrf_score
            if metadata:
                entry["metadata"] = metadata

        # Semantic Ranking
        for rank, (doc, score) in enumerate(semantic_results, start=1):
            text = doc.page_content if hasattr(doc, "page_content") else doc
            metadata = getattr(doc, "metadata", {}) or {}
            rrf_score = 1 / (self.k + rank)
            entry = fused.setdefault(text, {"rrf": 0.0, "metadata": {}})
            entry["rrf"] += rrf_score
            if metadata:
                entry["metadata"] = metadata

        # Sort according to RRF score
        ranked_results = sorted(fused.items(), key=lambda x: x[1]["rrf"], reverse=True)

        # Take Top 25 after RRF, as {"text":..., "metadata":...} candidates
        candidate_docs = [
            {"text": text, "metadata": data["metadata"]}
            for text, data in ranked_results[:25]
        ]

        # Cross Encoder Re-ranking (metadata rides along on each candidate dict)
        reranked = self.reranker.rerank(query, candidate_docs, top_n=top_n)

        return reranked