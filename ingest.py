import os
import pickle
from collections import Counter

from ingestion.chunker import chunk_documents
from ingestion.pdf_loader import load_documents
from ingestion.pinecone_upload import upload
from pro.keyword_based import KeywordSearchBM25

# 1. PDFs load (per file merged text)
docs = load_documents("docs2")

# 2. Route chunks by document type
chunks = chunk_documents(docs)
print("Chunk types:", dict(Counter(c.metadata.get("chunk_type", "basic") for c in chunks)))

# 3. Upload vectors (stable ids + e5 passage prefix)
upload(chunks)

# 4. Text + metadata for BM25
# NOTE: chunk text includes a "[section | POL-6.2]" header, so rule-ID keyword search works
chunk_texts = [chunk.page_content for chunk in chunks]
chunk_metadatas = [chunk.metadata for chunk in chunks]

# 5. BM25 build & save
keyword_search = KeywordSearchBM25(chunk_texts, metadatas=chunk_metadatas)

os.makedirs("data", exist_ok=True)
with open("data/bm25.pkl", "wb") as f:
    pickle.dump(keyword_search, f)

print("Ingestion complete, BM25 model saved.")
