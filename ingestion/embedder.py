from langchain_huggingface import HuggingFaceEmbeddings


class E5Embeddings(HuggingFaceEmbeddings):
    """multilingual-e5 needs prefixes: documents -> "passage: ...", queries -> "query: ..."."""

    def embed_documents(self, texts):
        return super().embed_documents([f"passage: {t}" for t in texts])

    def embed_query(self, text):
        return super().embed_query(f"query: {text}")


def get_embedding_model():
    return E5Embeddings(
        model_name="intfloat/multilingual-e5-base",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
