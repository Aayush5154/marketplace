"""Focused tests: backend helpers and guarded endpoints (no models needed)."""

from backend.app import build_revised, current_outcome, is_self_review, parse_attributes


def test_parse_attributes():
    assert parse_attributes("brand: Aurora\nmodel: PB-20") == {"brand": "Aurora", "model": "PB-20"}
    assert parse_attributes("brand: Aurora; model: PB-20") == {"brand": "Aurora", "model": "PB-20"}


def test_self_review_block():
    assert is_self_review("Aurora Store", "aurora store")
    assert not is_self_review("Reviewer", "Aurora Store")
    assert not is_self_review("", "Aurora Store")


def test_current_outcome_from_decisions():
    rows = [{"id": 1, "severity": "Major"}, {"id": 2, "severity": "Minor"}]
    assert current_outcome(rows, {}) == "Needs changes"
    assert current_outcome(rows, {1: {"action": "approve"}}) == "Approved"


def test_build_revised_uses_only_decided_fields():
    listing = {"title": "Old", "description": "Old desc", "tags": "a, b"}
    result = {"ai": {"revised_listing": {"title": "AI title", "description": "AI desc"}}}
    findings = [
        {"id": 1, "kind": "ai", "field": "title"},
        {"id": 2, "kind": "ai", "field": "description"},
    ]
    out = build_revised(listing, result, findings, {1: {"action": "approve", "revised": "AI title"}})
    assert out["title"] == "AI title"
    assert out["description"] == "Old desc"  # undecided fields stay original


def test_approved_ai_finding_uses_ai_revision():
    """Approve-as-is must surface the AI wording in Compare, not the original text."""
    listing = {"title": "Old title", "description": "Old desc", "tags": ""}
    result = {"ai": {"revised_listing": {"title": "AI rewritten title"}}}
    findings = [{"id": 1, "kind": "ai", "field": "title", "quote": ""}]
    out = build_revised(listing, result, findings, {1: {"action": "approve", "revised": ""}})
    assert out["title"] == "AI rewritten title"


def test_ai_revision_round_trip(tmp_path):
    import store
    conn = store.get_db(str(tmp_path / "rev.db"))
    lid = store.save_listing(conn, {"title": "t", "description": "d", "category": "Electronics",
                                    "price": "1", "attributes": {}, "seller": "S", "tags": []})
    rid = store.save_review(conn, lid, reviewer="R")
    store.save_ai_revision(conn, rid, {"title": "Fixed title"})
    assert store.get_ai_revision(conn, rid) == {"title": "Fixed title"}
    assert store.get_ai_revision(conn, rid + 999) == {}


def test_endpoints_guard_without_models():
    import pytest
    from fastapi import HTTPException
    from backend import app as app_module
    assert app_module._state["loaded"] is False
    for guarded in (app_module.require_models,):
        with pytest.raises(HTTPException) as ei:
            guarded()
        assert ei.value.status_code == 409
    client_routes = {r.path for r in app_module.app.routes}
    assert {"/api/health", "/api/reviews", "/api/ask", "/api/decisions"} <= client_routes
