"""
BUILD-002 — Human State Observatory (internal validation, admin-gated).

Captures the FULL extraction transition for every ingested message (message →
entities → confidence → TTL → prev → updated → conflict resolution → final state),
and computes engineering metrics from reviewer marks. Not a user feature. Adds no
Brain / Coaching / Constitution / Genome behavior.
"""
import time
from collections import Counter, defaultdict

import db as store
from human_state import extractor, engine
from human_state.config import audit_enabled

_ACTUAL = {"correct", "incorrect", "partial", "false_extraction"}   # reviews of a real extraction
_WRONG = {"incorrect", "false_extraction"}
_CONF_BUCKETS = [("≥0.85", 0.85), ("0.65–0.85", 0.65), ("0.45–0.65", 0.45), ("<0.45", 0.0)]


def enabled() -> bool:
    return audit_enabled()


def capture(subject, message, now=None):
    """Extract + ingest + record the full transition. Failure-isolated; returns the
    apply result (also writes human_state, since audit implies ingestion)."""
    t0 = time.perf_counter()
    readings = extractor.extract(message, now=now)
    res = engine.apply(subject, readings, now=now)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    try:
        store.hse_log_event(subject, message, res.get("transitions", []), latency_ms)
    except Exception as e:
        print(f"[hse-obs] log failed: {e}")
    return res


def _bucket(conf):
    for label, lo in _CONF_BUCKETS:
        if conf is not None and conf >= lo:
            return label
    return "<0.45"


def metrics(events, reviews):
    tp = fp = fn = half = correct = 0
    # index each event's extracted confidence per key (for calibration)
    conf_by = {}
    for e in events:
        for tr in (e.get("transitions") or []):
            conf_by[(e["id"], tr["key"])] = tr.get("confidence")
    calib = defaultdict(lambda: [0, 0])   # bucket -> [reviewed, correct]
    for r in reviews:
        v = r.get("verdict")
        if v == "correct":
            tp += 1; correct += 1
        elif v == "partial":
            half += 1; correct += 0
        elif v in _WRONG:
            fp += 1
        elif v == "missed":
            fn += 1
        if v in _ACTUAL:
            b = _bucket(conf_by.get((r.get("event_id"), r.get("key"))))
            calib[b][0] += 1
            if v == "correct":
                calib[b][1] += 1
    eff_tp = tp + 0.5 * half
    precision = round(eff_tp / (eff_tp + fp), 3) if (eff_tp + fp) else None
    recall = round(eff_tp / (eff_tp + fn), 3) if (eff_tp + fn) else None
    total_rev = len(reviews)
    agreement = round(correct / total_rev, 3) if total_rev else None
    lat = [e.get("latency_ms") for e in events if e.get("latency_ms") is not None]
    calibration = {b: {"reviewed": n, "accuracy": round(c / n, 3) if n else None}
                   for b, (n, c) in calib.items()}
    return {
        "precision": precision, "recall": recall, "agreement_rate": agreement,
        "avg_latency_ms": round(sum(lat) / len(lat), 2) if lat else None,
        "reviews": total_rev, "tp": tp, "fp": fp, "fn": fn, "partial": half,
        "calibration": calibration,
    }


def analytics(events, reviews):
    detected = Counter()
    conf_sum, conf_n = defaultdict(float), Counter()
    for e in events:
        for tr in (e.get("transitions") or []):
            k = tr["key"]
            detected[k] += 1
            if tr.get("confidence") is not None:
                conf_sum[k] += tr["confidence"]; conf_n[k] += 1
    avg_conf = {k: round(conf_sum[k] / conf_n[k], 3) for k in conf_n}
    missed = Counter(r["key"] for r in reviews if r.get("verdict") == "missed")
    corrected = Counter(r["key"] for r in reviews if r.get("verdict") in _WRONG or r.get("verdict") == "partial")
    return {
        "detected": detected.most_common(),
        "top_missed": missed.most_common(10),
        "most_corrected": corrected.most_common(10),
        "most_uncertain": sorted(avg_conf.items(), key=lambda kv: kv[1])[:10],
        "lowest_confidence_categories": sorted(avg_conf.items(), key=lambda kv: kv[1])[:10],
    }


def report(subject=None, limit=60):
    """Full dashboard payload. Read-only."""
    try:
        events = store.hse_recent_events(limit=limit)          # recent, all subjects
        reviews = store.hse_all_reviews()
        timeline = store.hse_recent_events(limit=200, subject=subject) if subject else []
        return {
            "ok": True,
            "total_events": store.hse_event_count(),
            "events": events,
            "timeline": timeline,
            "timeline_subject": subject,
            "metrics": metrics(events, reviews),
            "analytics": analytics(events, reviews),
        }
    except Exception as e:
        print(f"[hse-obs] report failed: {e}")
        return {"ok": False, "error": str(e)}
