"""
BUILD-002 — Human State Observatory: capture, audit traceability, analytics,
engineering metrics (precision/recall/calibration), timeline/replay, reviewer mode.
"""
import datetime as _dt

from human_state import observatory as obs
from human_state import engine, extractor
from human_state.schema import Reading
import db as store

UTC = _dt.timezone.utc
def _t(**kw):
    return _dt.datetime(2026, 7, 7, 10, 0, 0, tzinfo=UTC) + _dt.timedelta(**kw)


# ── capture writes a full, traceable transition ──────────────────────────────
def test_capture_records_traceable_transition():
    obs.capture("device:o1", "I'm exhausted", now=_t())
    ev = store.hse_recent_events(limit=5)
    assert ev and ev[0]["subject"] == "device:o1"
    tr = ev[0]["transitions"][0]
    # every field needed to explain the update is present (no hidden inference)
    for f in ("key", "extracted_value", "confidence", "ttl_seconds", "prev_value",
              "prev_effective", "action", "final_value"):
        assert f in tr
    assert tr["key"] == "fatigue" and tr["action"] == "insert"
    # capture also ingested → state is written
    assert store.hs_get("device:o1", "fatigue")["value"] == "high"


def test_transition_shows_conflict_resolution():
    now = _t()
    obs.capture("device:o2", "I'm exhausted", now=now)                     # high conf insert
    obs.capture("device:o2", "kind of tired", now=now + _dt.timedelta(minutes=5))  # hedged -> keep
    ev = store.hse_recent_events(limit=1, subject=None)
    # most recent event's transition should show action=keep (never-downgrade)
    last = store.hse_recent_events(limit=5)[0]
    assert last["transitions"][0]["action"] == "keep"
    assert last["transitions"][0]["prev_value"] == "high"


# ── engine.apply audit is additive (BUILD-001 behavior unchanged) ────────────
def test_apply_return_is_backward_compatible():
    res = engine.apply("device:o3", extractor.extract("I'm exhausted", now=_t()), now=_t())
    assert "applied" in res and "kept" in res and "transitions" in res     # enriched, not broken


# ── metrics from reviewer marks ──────────────────────────────────────────────
def test_metrics_precision_recall_from_reviews():
    eid = store.hse_log_event("device:o4", "msg",
                              [{"key": "sleep", "extracted_value": "4", "confidence": 0.9,
                                "ttl_seconds": 3600, "prev_value": None, "prev_effective": 0.0,
                                "action": "insert", "final_value": "4"}], 3.2)
    store.hse_add_review(eid, "sleep", "correct")          # TP
    store.hse_add_review(eid, "stress", "false_extraction")  # FP
    store.hse_add_review(eid, "pain", "missed")            # FN
    r = obs.report()
    m = r["metrics"]
    assert m["tp"] == 1 and m["fp"] == 1 and m["fn"] == 1
    assert m["precision"] == 0.5 and m["recall"] == 0.5    # 1/(1+1)
    assert m["agreement_rate"] == round(1/3, 3)


def test_calibration_buckets_by_extractor_confidence():
    eid = store.hse_log_event("device:o5", "m",
                              [{"key": "sleep", "extracted_value": "5", "confidence": 0.9,
                                "ttl_seconds": 3600, "prev_value": None, "prev_effective": 0.0,
                                "action": "insert", "final_value": "5"}], 2.0)
    store.hse_add_review(eid, "sleep", "correct")
    cal = obs.report()["metrics"]["calibration"]
    assert "≥0.85" in cal and cal["≥0.85"]["accuracy"] == 1.0


# ── analytics ────────────────────────────────────────────────────────────────
def test_analytics_missed_and_uncertain():
    eid = store.hse_log_event("device:o6", "m",
                              [{"key": "motivation", "extracted_value": "low", "confidence": 0.55,
                                "ttl_seconds": 3600, "prev_value": None, "prev_effective": 0.0,
                                "action": "insert", "final_value": "low"}], 1.0)
    store.hse_add_review(eid, "energy", "missed")
    a = obs.report()["analytics"]
    assert ("energy", 1) in a["top_missed"]
    assert any(k == "motivation" for k, _ in a["most_uncertain"])


# ── timeline / replay ────────────────────────────────────────────────────────
def test_timeline_is_chronological_for_subject():
    now = _t()
    obs.capture("device:o7", "I'm sick", now=now)
    obs.capture("device:o7", "I'm travelling", now=now + _dt.timedelta(minutes=1))
    r = obs.report(subject="device:o7")
    msgs = [e["message"] for e in r["timeline"]]
    assert msgs == ["I'm sick", "I'm travelling"]           # ascending order


# ── reviewer mode persists ───────────────────────────────────────────────────
def test_review_persists():
    eid = store.hse_log_event("device:o8", "m", [], 0.0)
    store.hse_add_review(eid, "sleep", "partial", note="close")
    revs = store.hse_all_reviews()
    assert any(rv["verdict"] == "partial" and rv["key"] == "sleep" for rv in revs)
