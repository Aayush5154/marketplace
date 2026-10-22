"""Focused tests: SQLite storage, outcome rules, append-only audit log."""

import store


def _db(tmp_path):
    return store.get_db(str(tmp_path / "t.db"))


def test_outcome_rules():
    assert store.compute_outcome([{"severity": "Critical", "resolved": False}]) == "Rejected"
    assert store.compute_outcome([{"severity": "Critical", "resolved": True}]) == "Approved"
    assert store.compute_outcome([{"severity": "Major", "resolved": False}]) == "Needs changes"
    assert store.compute_outcome([{"severity": "Minor", "resolved": False}]) == "Approved"
    assert store.compute_outcome([]) == "Approved"


def test_review_flow_and_audit_log(tmp_path):
    conn = _db(tmp_path)
    lid = store.save_listing(conn, {"title": "t", "description": "d", "category": "Electronics",
                                    "price": "10", "attributes": {}, "seller": "Shop", "tags": []})
    rid = store.save_review(conn, lid, reviewer="Reviewer")
    fid = store.save_finding(conn, rid, "ai", field="description", quote="cures pain",
                             issue_type="prohibited", severity="Critical",
                             explanation="medical claim", rule_ids=["POL-6.2"],
                             suggested_wording="may help")
    assert len(store.get_findings(conn, rid)) == 1
    store.log_decision(conn, lid, rid, "description", "cures pain", "may help",
                       "Reviewer", "reject", fid)
    decisions = store.get_decisions(conn, lid)
    assert len(decisions) == 1 and decisions[0]["action"] == "reject"


def test_decision_validation(tmp_path):
    conn = _db(tmp_path)
    try:
        store.log_decision(conn, 1, 1, "title", "a", "b", "", "approve", None)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        store.log_decision(conn, 1, 1, "title", "a", "b", "R", "maybe", None)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
