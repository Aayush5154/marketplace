from collections import defaultdict

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.documents import Document


def load_documents(folder):
    """
    Load all PDFs in `folder` and merge pages per source file.
    Preserves original PDF loader metadata from the first page while merging.
    """
    loader = PyPDFDirectoryLoader(folder)
    pages = loader.load()

    by_source = defaultdict(list)
    for page in pages:
        by_source[page.metadata.get("source", "unknown")].append(page)

    docs = []
    for _source, pgs in by_source.items():
        pgs.sort(key=lambda d: d.metadata.get("page", 0))
        full_text = "\n\n".join(p.page_content for p in pgs)
        # Copy loader metadata from the first page.
        merged_metadata = pgs[0].metadata.copy() if pgs else {}
        merged_metadata["num_pages"] = len(pgs)
        merged_metadata.pop("page", None)

        docs.append(
            Document(
                page_content=full_text,
                metadata=merged_metadata,
            )
        )

    return docs
