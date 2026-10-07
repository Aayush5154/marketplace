"""
store.py

SQLite storage for the Marketplace Listing Quality Reviewer.

Tables:
  listings   - one row per reviewed listing
  reviews    - one row per review run (deterministic + AI results)
  findings   - one row per deterministic failure / AI finding (rule IDs kept)
  decisions  - APPEND-ONLY audit log of reviewer actions.
               Rows are only ever INSERTed, never UPDATEd or DELETEd.

Each decision records: listing id, field, original text, revised text,
reviewer name, action (approve / edit / reject), timestamp.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

DEFAULT_DB = str(Path(__file__).parent / "data" / "reviews.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    price       TEXT NOT NULL DEFAULT '',
    attributes  TEXT NOT NULL DEFAULT '{}',
    seller      TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id),
    reviewer    TEXT NOT NULL DEFAULT '',
    outcome     TEXT NOT NULL DEFAULT 'Pending',
    error       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id         INTEGER NOT NULL REFERENCES reviews(id),
    kind              TEXT NOT NULL,          -- 'deterministic' or 'ai'
    field             TEXT NOT NULL DEFAULT '',
    quote             TEXT NOT NULL DEFAULT '',
    issue_type        TEXT NOT NULL DEFAULT '',
    severity          TEXT NOT NULL DEFAULT 'Major',
    explanation       TEXT NOT NULL DEFAULT '',
    rule_ids          TEXT NOT NULL DEFAULT '[]',   -- JSON list, never dropped
    suggested_wording TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id    INTEGER NOT NULL REFERENCES listings(id),
    review_id     INTEGER NOT NULL REFERENCES reviews(id),
    finding_id    INTEGER REFERENCES findings(id),
    field         TEXT NOT NULL DEFAULT '',
    original_text TEXT NOT NULL DEFAULT '',
    revised_text  TEXT NOT NULL DEFAULT '',
    reviewer_name TEXT NOT NULL DEFAULT '',
    action        TEXT NOT NULL,              -- 'approve' / 'edit' / 'reject'
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_revisions (
    review_id     INTEGER PRIMARY KEY REFERENCES reviews(id),
    revised_json  TEXT NOT NULL DEFAULT '{}'
);
"""

ACTIONS = ("approve", "edit", "reject")

# Shared connection may be used from multiple threads, so serialize DB access.
_lock = threading.RLock()


def _sync(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db(path=DEFAULT_DB):
    """Open (creating dirs + schema) and return a sqlite3 connection."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False so a cached connection can be reused across threads.
    # Writes are sequential; each write commits.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------
@_sync
def save_listing(conn, listing):
    cur = conn.execute(
        "INSERT INTO listings (title, description, category, price, attributes, seller, tags, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(listing.get("title") or ""),
            str(listing.get("description") or ""),
            str(listing.get("category") or ""),
            str(listing.get("price") or ""),
            json.dumps(listing.get("attributes") or {}, ensure_ascii=False),
            str(listing.get("seller") or ""),
            json.dumps(listing.get("tags") or [], ensure_ascii=False),
            _now(),
        ),
    )
    conn.commit()
    return cur.lastrowid


@_sync
def save_review(conn, listing_id, reviewer="", outcome="Pending", error=""):
    cur = conn.execute(
        "INSERT INTO reviews (listing_id, reviewer, outcome, error, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (listing_id, reviewer, outcome, error or "", _now()),
    )
    conn.commit()
    return cur.lastrowid


@_sync
def save_finding(conn, review_id, kind, field="", quote="", issue_type="",
                 severity="Major", explanation="", rule_ids=None, suggested_wording=""):
    cur = conn.execute(
        "INSERT INTO findings (review_id, kind, field, quote, issue_type, severity,"
        " explanation, rule_ids, suggested_wording)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            review_id, kind, field, quote, issue_type, severity,
            explanation, json.dumps(rule_ids or [], ensure_ascii=False),
            suggested_wording,
        ),
    )
    conn.commit()
    return cur.lastrowid


@_sync
def save_failed_checks(conn, review_id, failed):
    """Persist deterministic failures as findings (severity Major, rule IDs kept)."""
    ids = []
    for c in failed or []:
        ids.append(save_finding(
            conn, review_id, kind="deterministic",
            field=c.get("check", ""), quote="",
            issue_type="incomplete", severity="Major",
            explanation=c.get("message", ""),
            rule_ids=list(c.get("rules") or []),
            suggested_wording="",
        ))
    return ids


@_sync
def save_ai_findings(conn, review_id, findings):
    ids = []
    for f in findings or []:
        ids.append(save_finding(
            conn, review_id, kind="ai",
            field=f.get("field", ""), quote=f.get("quote", ""),
            issue_type=f.get("issue_type", ""), severity=f.get("severity", "Minor"),
            explanation=f.get("explanation", ""),
            rule_ids=list(f.get("rule_ids") or []),
            suggested_wording=f.get("suggested_wording", ""),
        ))
    return ids


@_sync
def save_ai_revision(conn, review_id, revised_listing):
    """Persist the AI's suggested revised listing so Compare can rebuild it later."""
    conn.execute(
        "INSERT OR REPLACE INTO ai_revisions (review_id, revised_json) VALUES (?, ?)",
        (review_id, json.dumps(revised_listing or {}, ensure_ascii=False)),
    )
    conn.commit()


@_sync
def get_ai_revision(conn, review_id):
    row = conn.execute(
        "SELECT revised_json FROM ai_revisions WHERE review_id = ?", (review_id,)
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["revised_json"]) or {}
    except (ValueError, TypeError):
        return {}


@_sync
def set_review_outcome(conn, review_id, outcome, reviewer=""):
    """Update a review's outcome/reviewer. (Reviews are mutable; the DECISIONS log is not.)"""
    if reviewer:
        conn.execute("UPDATE reviews SET outcome = ?, reviewer = ? WHERE id = ?",
                     (outcome, reviewer, review_id))
    else:
        conn.execute("UPDATE reviews SET outcome = ? WHERE id = ?", (outcome, review_id))
    conn.commit()


@_sync
def log_decision(conn, listing_id, review_id, field, original_text, revised_text,
                 reviewer_name, action, finding_id=None):
    """
    Append one reviewer decision to the audit log.
    No UPDATE or DELETE is ever performed on this table.
    """
    action = str(action).lower().strip()
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}")
    if not str(reviewer_name).strip():
        raise ValueError("reviewer_name is required")
    cur = conn.execute(
        "INSERT INTO decisions (listing_id, review_id, finding_id, field,"
        " original_text, revised_text, reviewer_name, action, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (listing_id, review_id, finding_id, field,
         original_text or "", revised_text or "",
         reviewer_name.strip(), action, _now()),
    )
    conn.commit()
    return cur.lastrowid


# ----------------------------------------------------------------------
# Outcome
# ----------------------------------------------------------------------
def compute_outcome(items):
    """
    items: list of {"severity": Critical|Major|Minor|Info, "resolved": bool}.
    A finding is resolved when the reviewer approved or edited it;
    rejected / undecided findings remain.

      Rejected     = a Critical finding remains
      Needs changes = a Major finding remains (incl. a rejected Major fix)
      Approved     = no Critical or Major findings left
    """
    open_items = [i for i in items if not i.get("resolved")]
    if any(str(i.get("severity", "")).capitalize() == "Critical" for i in open_items):
        return "Rejected"
    if any(str(i.get("severity", "")).capitalize() == "Major" for i in open_items):
        return "Needs changes"
    return "Approved"


# ----------------------------------------------------------------------
# Reads (history tab)
# ----------------------------------------------------------------------
@_sync
def get_listings(conn):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM listings ORDER BY id DESC").fetchall()]


@_sync
def get_reviews(conn, listing_id=None):
    if listing_id:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM reviews WHERE listing_id = ? ORDER BY id DESC", (listing_id,)).fetchall()]
    return [dict(r) for r in conn.execute(
        "SELECT * FROM reviews ORDER BY id DESC").fetchall()]


@_sync
def get_findings(conn, review_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM findings WHERE review_id = ? ORDER BY id", (review_id,)).fetchall()]


@_sync
def get_decisions(conn, listing_id=None):
    if listing_id:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM decisions WHERE listing_id = ? ORDER BY id", (listing_id,)).fetchall()]
    return [dict(r) for r in conn.execute(
        "SELECT * FROM decisions ORDER BY id DESC LIMIT 500").fetchall()]


if __name__ == "__main__":
    # Tiny self-check: append-only audit log + outcome rules.
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), "reviewer_selfcheck.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    c = get_db(tmp)
    lid = save_listing(c, {"title": "t", "description": "d", "category": "Electronics",
                           "price": "10", "attributes": {}, "seller": "Seller A", "tags": []})
    rid = save_review(c, lid, reviewer="Ravi")
    fid = save_finding(c, rid, "ai", field="description", quote="cures pain",
                       issue_type="prohibited", severity="Critical",
                       explanation="medical claim", rule_ids=["POL-6.2"],
                       suggested_wording="may help with comfort")
    assert compute_outcome([{"severity": "Critical", "resolved": False}]) == "Rejected"
    assert compute_outcome([{"severity": "Critical", "resolved": True}]) == "Approved"
    assert compute_outcome([{"severity": "Major", "resolved": False}]) == "Needs changes"
    assert compute_outcome([{"severity": "Minor", "resolved": False}]) == "Approved"
    log_decision(c, lid, rid, "description", "cures pain", "may help", "Ravi", "reject", fid)
    ds = get_decisions(c, lid)
    assert len(ds) == 1 and ds[0]["action"] == "reject"
    assert not hasattr(log_decision, "update")  # no update path exists
    print("store.py self-check OK")
