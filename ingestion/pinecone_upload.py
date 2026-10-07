import config
from langchain_pinecone import PineconeVectorStore
from ingestion.embedder import get_embedding_model


def _clean_metadata(meta):
    """Pinecone metadata allows only str / number / bool / list[str]."""
    out = {}
    for k, v in meta.items():
        if v is None or v == "" or v == [] or v == ():
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple, set)):
            out[k] = [str(x) for x in v]
        else:
            out[k] = str(v)
    return out


def upload(chunks, batch_size=64):
    for c in chunks:
        c.metadata = _clean_metadata(c.metadata)

    # Stable ids: re-ingest overwrites the same ids instead of duplicating.
    source_tag = lambda c: str(c.metadata.get("source", "doc")).replace("\\", "/").split("/")[-1]
    ids = []
    for i, c in enumerate(chunks):
        cid = c.metadata.get("chunk_id")
        ids.append(f"{source_tag(c)}::{cid}" if cid else f"{source_tag(c)}::{i}")

    PineconeVectorStore.from_documents(
        chunks,
        embedding=get_embedding_model(),
        index_name=config.PINECONE_INDEX,
        ids=ids,
        batch_size=batch_size,
        namespace=getattr(config, "PINECONE_NAMESPACE", None),
    )
    print(f"Uploaded Successfully ({len(chunks)} chunks)")