from langchain_pinecone import PineconeVectorStore

from ingestion.embedder import get_embedding_model
from config import PINECONE_INDEX


class SemanticSearch:
    """
    Performs semantic (vector) search using Pinecone.

    Instead of storing vectors locally in a NumPy array,
    this class connects to an existing Pinecone index
    and retrieves the most semantically similar chunks.
    """

    def __init__(self):
        """
        Initialize the Semantic Search class.

        - Loads the embedding model.
        - Connects to the Pinecone index.
        """

        self.embedding_model = get_embedding_model()

        self.vector_store = PineconeVectorStore(
            index_name=PINECONE_INDEX,
            embedding=self.embedding_model
        )

    def search(self, query, top_n=5):
        """
        Perform semantic search.

        Parameters
        ----------
        query : str
            User's search query.

        top_n : int
            Number of most similar chunks to retrieve.

        Returns
        -------
        list
            List containing tuples:
            (Document, Similarity Score)
        """

        results = self.vector_store.similarity_search_with_score(
            query=query,
            k=top_n
        )

        return results