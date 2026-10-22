"""FastAPI backend: deterministic checks + RAG/AI review + review workflow."""

import logging
import os
import pickle

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import store
from app_logging import setup as setup_logging
from llm.chat import (
    format_context,
    generate_answer,
    item_meta,
    item_text,
    review_listing_with_ai,
)
from validator import CATEGORY_ATTRIBUTES

setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("marketplace.api")

CATEGORIES = [c.title() for c in CATEGORY_ATTRIBUTES]

# Deterministic check name -> listing field (for revised text + compare view).
CHECK_FIELD = {
    "required_fields": "title",
    "title_length": "title",
    "description_length": "description",
    "price_format": "price",
    "price_range": "price",
    "category_supported": "category",
    "required_attributes": "attributes",
    "condition_value": "attributes",
    "tags": "tags",
    "contact_details": "description",
    "exact_duplicate": "title",
    "near_duplicate": "title",
    "keyword_stuffing": "title",
    "caps_and_symbols": "title",
}

app = FastAPI(title="Marketplace Listing Quality Reviewer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_state = {"keyword": None, "hybrid": None, "loaded": False}
_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = store.get_db()
    return _conn


def require_models():
    if not _state["loaded"]:
        raise HTTPException(status_code=409, detail="Models not initialized. Call POST /api/init first.")


def parse_attributes(text):
    attrs = {}
    for part in str(text or "").replace(";", "\n").splitlines():
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip():
                attrs[k.strip()] = v.strip()
    return attrs


def field_text(listing, field):
    if field == "attributes":
        return "\n".join(f"{k}: {v}" for k, v in (listing.get("attributes") or {}).items())
    if field == "tags":
        tags = listing.get("tags") or []
        return ", ".join(tags) if isinstance(tags, list) else str(tags)
    return str(listing.get(field) or "")


def is_self_review(reviewer, seller):
    return bool(reviewer.strip()) and reviewer.strip().lower() == str(seller or "").strip().lower()


def current_outcome(finding_rows, decisions):
    items = [
        {"severity": f.get("severity", "Major"),
         "resolved": decisions.get(f["id"], {}).get("action") in ("approve", "edit")}
        for f in finding_rows
    ]
    return store.compute_outcome(items) if items else "Approved"


def target_field(f):
    if f["kind"] == "ai":
        return f["field"] if f["field"] in ("title", "description", "tags") else "description"
    return CHECK_FIELD.get(f["field"], "title")


def original_text_for(listing, f):
    if f.get("quote"):
        return f["quote"]
    field = f["field"] if f["kind"] == "ai" else CHECK_FIELD.get(f["field"], "title")
    return field_text(listing, field)


def build_revised(listing, result, findings, decisions):
    """Revised text from reviewer decisions; undecided fields keep the original."""
    revised = {k: field_text(listing, k) for k in ("title", "description", "tags")}
    ai_rev = (result.get("ai") or {}).get("revised_listing") or {}
    manual, ai_ok = {}, set()
    by_id = {f["id"]: f for f in findings}
    for fid, d in decisions.items():
        f = by_id.get(fid)
        if not f:
            continue
        fld = target_field(f)
        text = str(d.get("revised") or "").strip()
        if d["action"] == "edit":
            if text:
                manual[fld] = text
        elif d["action"] == "approve":
            # Reviewer-typed text wins; a bare quote is not a field rewrite.
            if text and text != str(f.get("quote") or "").strip():
                manual[fld] = text
            else:
                ai_ok.add(fld)
    for fld in ("title", "description", "tags"):
        if fld in manual:
            revised[fld] = manual[fld]
        elif fld in ai_ok and ai_rev.get(fld):
            v = ai_rev[fld]
            revised[fld] = v if isinstance(v, str) else ", ".join(v)
    return revised


def serialize_retrieved(retrieved):
    out = []
    for score, item in retrieved or []:
        meta = item_meta(item)
        out.append({
            "score": score if isinstance(score, (int, float)) else None,
            "via": item.get("via", "direct") if isinstance(item, dict) else "direct",
            "label": meta.get("rule_id") or meta.get("chunk_type") or "chunk",
            "text": item_text(item),
            "metadata": {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))},
        })
    return out


def decisions_for_review(review_id):
    rows = [d for d in store.get_decisions(get_conn()) if d["review_id"] == review_id]
    latest = {}
    for d in rows:
        if d.get("finding_id") is not None:
            latest[d["finding_id"]] = {"action": d["action"], "revised": d["revised_text"]}
    return latest


# Request models.
class Listing(BaseModel):
    title: str = ""
    description: str = ""
    category: str = ""
    price: str = ""
    attributes: dict = Field(default_factory=dict)
    seller: str = ""
    tags: list = Field(default_factory=list)


class ReviewRequest(BaseModel):
    listing: Listing
    others: list = Field(default_factory=list)
    reviewer: str = ""
    top_n: int = 6


class DecisionRequest(BaseModel):
    review_id: int
    finding_id: int
    action: str
    revised_text: str = ""
    reviewer: str


class AskRequest(BaseModel):
    query: str
    top_n: int = 6


@app.get("/api/health")
def health():
    return {"status": "ok", "models_loaded": _state["loaded"]}


@app.get("/api/categories")
def categories():
    return {"categories": CATEGORIES}


@app.post("/api/init")
def init_models():
    from pro.hybrid import CombinedSearch
    from pro.semantic import SemanticSearch

    if not os.path.exists("data/bm25.pkl"):
        raise HTTPException(status_code=500, detail="data/bm25.pkl not found. Run ingest.py first.")
    with open("data/bm25.pkl", "rb") as f:
        keyword = pickle.load(f)
    semantic = SemanticSearch()
    _state.update(keyword=keyword, hybrid=CombinedSearch(keyword, semantic), loaded=True)
    logger.info("models_initialized")
    return {"status": "ok"}


@app.post("/api/reviews")
def create_review(req: ReviewRequest):
    require_models()
    listing = req.listing.model_dump()
    result = review_listing_with_ai(
        listing, req.others, _state["keyword"], _state["hybrid"], top_n=req.top_n)
    conn = get_conn()
    listing_id = store.save_listing(conn, listing)
    review_id = store.save_review(conn, listing_id, reviewer=req.reviewer,
                                  error=result.get("error") or "")
    store.save_failed_checks(conn, review_id, result.get("failed"))
    if result.get("ai"):
        store.save_ai_findings(conn, review_id, result["ai"].get("findings"))
        store.save_ai_revision(conn, review_id, result["ai"].get("revised_listing"))
    findings = store.get_findings(conn, review_id)
    outcome = current_outcome(findings, {})
    store.set_review_outcome(conn, review_id, outcome, req.reviewer)
    logger.info("review_created", extra={"extra_data": {
        "review_id": review_id, "failed": len(result["failed"]),
        "ai_findings": len((result.get("ai") or {}).get("findings", []))}})
    return {
        "listing_id": listing_id, "review_id": review_id, "outcome": outcome,
        "original": {k: field_text(listing, k) for k in ("title", "description", "tags")},
        "checks": result["checks"], "failed": result["failed"],
        "triggers": result["triggers"], "ai": result["ai"], "error": result["error"],
        "findings": findings, "decisions": {},
        "retrieved": serialize_retrieved(result.get("retrieved")),
    }


@app.get("/api/reviews/{review_id}")
def get_review(review_id: int):
    conn = get_conn()
    reviews = store.get_reviews(conn)
    review = next((r for r in reviews if r["id"] == review_id), None)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found.")
    listings = {l["id"]: l for l in store.get_listings(conn)}
    findings = store.get_findings(conn, review_id)
    decisions = decisions_for_review(review_id)
    outcome = current_outcome(findings, decisions)
    listing = listings.get(review["listing_id"], {})
    original = {k: field_text(listing, k) for k in ("title", "description", "tags")}
    revised = build_revised(
        listing,
        {"ai": {"revised_listing": store.get_ai_revision(conn, review_id)}},
        findings,
        decisions,
    )
    return {
        "review": review, "listing": listing, "findings": findings,
        "decisions": decisions, "outcome": outcome,
        "original": original, "revised": revised,
    }


@app.get("/api/listings")
def list_listings():
    return {"listings": store.get_listings(get_conn())}


@app.get("/api/reviews")
def list_reviews(listing_id: int | None = None):
    return {"reviews": store.get_reviews(get_conn(), listing_id)}


@app.get("/api/decisions")
def list_decisions(listing_id: int | None = None):
    return {"decisions": store.get_decisions(get_conn(), listing_id)}


@app.post("/api/decisions")
def record_decision(req: DecisionRequest):
    conn = get_conn()
    findings = store.get_findings(conn, req.review_id)
    finding = next((f for f in findings if f["id"] == req.finding_id), None)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found.")
    action = req.action.lower().strip()
    if action not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="Action must be approve, edit, or reject.")
    if not req.reviewer.strip():
        raise HTTPException(status_code=400, detail="Reviewer name is required.")
    reviews = store.get_reviews(conn)
    review = next((r for r in reviews if r["id"] == req.review_id), None)
    listings = {l["id"]: l for l in store.get_listings(conn)}
    listing = listings.get(review["listing_id"], {}) if review else {}
    if is_self_review(req.reviewer, listing.get("seller")):
        raise HTTPException(status_code=403, detail="Self-review is blocked: reviewer must differ from seller.")
    revised = req.revised_text if action in ("approve", "edit") else original_text_for(listing, finding)
    store.log_decision(conn, review["listing_id"], req.review_id, field=finding["field"],
                       original_text=original_text_for(listing, finding),
                       revised_text=revised or "", reviewer_name=req.reviewer,
                       action=action, finding_id=finding["id"])
    decisions = decisions_for_review(req.review_id)
    outcome = current_outcome(findings, decisions)
    store.set_review_outcome(conn, req.review_id, outcome, req.reviewer)
    logger.info("decision_recorded", extra={"extra_data": {
        "review_id": req.review_id, "finding_id": req.finding_id, "action": action}})
    return {"status": "ok", "outcome": outcome, "decisions": decisions}


@app.post("/api/ask")
def ask_policy(req: AskRequest):
    require_models()
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query is required.")
    results = _state["hybrid"].search(query=req.query, top_n=req.top_n)
    answer = generate_answer(req.query, format_context(results))
    return {"answer": answer, "chunks": serialize_retrieved(results)}
