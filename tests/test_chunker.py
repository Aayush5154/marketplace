"""
tests/test_chunker.py

Unit tests for ingestion.chunker — no network calls, no PDFs.
Uses minimal inline text strings with POL-x.y rule markers.
"""

import pytest
from langchain_core.documents import Document

from ingestion.chunker import is_policy_doc, split_policy_document

# ---------------------------------------------------------------------------
# Minimal policy-like text: contains >= 10 POL-x.y markers so that
# is_policy_doc() returns True and split_policy_document() has rules to parse.
# ---------------------------------------------------------------------------
POLICY_TEXT = """\
Part A. Policy
1. General Rules

POL-1.1 Listings must have a title between 15 and 80 characters.
POL-1.2 Titles must not contain offensive language.
POL-1.3 Descriptions must be at least 80 characters long.

2. Pricing

POL-2.1 Price must be a positive number.
POL-2.2 Price must not exceed 100000.
POL-2.3 Price must use at most two decimal places.

3. Category

POL-3.1 Each listing must belong to a supported category.
POL-3.2 Category names are case-insensitive.

4. Attributes

POL-4.1 Electronics listings require brand, model, condition, warranty.
POL-4.2 Condition must be one of the allowed values.
"""

PLAIN_TEXT = "This is a plain document with no policy rule identifiers at all."


# ---------------------------------------------------------------------------
# is_policy_doc
# ---------------------------------------------------------------------------

class TestIsPolicyDoc:
    def test_returns_true_for_policy_text(self):
        assert is_policy_doc(POLICY_TEXT) is True

    def test_returns_false_for_plain_text(self):
        assert is_policy_doc(PLAIN_TEXT) is False

    def test_threshold_is_ten_markers(self):
        # Exactly 9 markers → False; 10 → True
        nine_rules = "\n".join(f"POL-{i}.1 Some rule." for i in range(1, 10))
        ten_rules = "\n".join(f"POL-{i}.1 Some rule." for i in range(1, 11))
        assert is_policy_doc(nine_rules) is False
        assert is_policy_doc(ten_rules) is True


# ---------------------------------------------------------------------------
# split_policy_document
# ---------------------------------------------------------------------------

class TestSplitPolicyDocument:
    @pytest.fixture
    def policy_doc(self):
        return Document(
            page_content=POLICY_TEXT,
            metadata={"source": "test_policy.pdf"},
        )

    def test_returns_non_empty_list(self, policy_doc):
        chunks = split_policy_document(policy_doc)
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_all_chunks_are_documents(self, policy_doc):
        chunks = split_policy_document(policy_doc)
        for chunk in chunks:
            assert hasattr(chunk, "page_content")
            assert hasattr(chunk, "metadata")

    def test_rule_ids_appear_in_metadata(self, policy_doc):
        chunks = split_policy_document(policy_doc)
        rule_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "rule"]
        assert len(rule_chunks) > 0
        rule_ids = {c.metadata["rule_id"] for c in rule_chunks}
        # At minimum the first rule in the text should be parsed
        assert any(rid.startswith("POL-") for rid in rule_ids)

    def test_source_preserved_in_metadata(self, policy_doc):
        chunks = split_policy_document(policy_doc)
        for chunk in chunks:
            assert chunk.metadata.get("source") == "test_policy.pdf"

    def test_no_crash_on_empty_body(self):
        """Edge case: document with no rule IDs and no sections."""
        doc = Document(page_content="Nothing here.", metadata={"source": "empty.pdf"})
        # Should return gracefully (empty list or minimal chunks, no exception)
        result = split_policy_document(doc)
        assert isinstance(result, list)
