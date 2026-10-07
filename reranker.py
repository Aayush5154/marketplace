from sentence_transformers import CrossEncoder


class CrossEncoderReranker:

    def __init__(self):
        self.model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )

    def rerank(self, query, documents, top_n=3):

        # Extract text from documents
        texts = []

        for doc in documents:
            if isinstance(doc, str):
                texts.append(doc)

            elif isinstance(doc, dict):
                texts.append(
                    doc.get("text") or
                    doc.get("content") or
                    doc.get("page_content", "")
                )

            else:
                texts.append(doc.page_content)

        # CrossEncoder needs: [(query, document_text), ...]
        pairs = [(str(query), str(text)) for text in texts]

        scores = self.model.predict(pairs)

        # Keep original documents with their scores
        results = list(zip(scores, documents))

        # Sort by score only
        results.sort(key=lambda x: x[0], reverse=True)

        return results[:top_n]