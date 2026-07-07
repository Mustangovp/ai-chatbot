"""
M5 Brain Observatory — analytics layer (no Brain logic). Verifies the write →
aggregate → observatory → anomaly path against the isolated test DB.
"""
import brain_analytics as ba
import db as store


def _seed(n, **kw):
    for _ in range(n):
        store.log_brain_event(anon_id="anon", **kw)


def test_anon_id_is_stable_and_non_reversible():
    a = ba.anon_id(("device", "abc"))
    assert a == ba.anon_id(("device", "abc")) and len(a) == 32 and "abc" not in a


def test_record_and_stats_roundtrip():
    ba.record(("device", "d1"), {"verdict": "GO", "urgency": None, "route": None,
                                 "intervention": "training", "generate": True, "cold_start": False}, 120)
    s = store.brain_events_stats(hours=24)
    assert s["total"] == 1 and s["verdicts"].get("GO") == 1
    assert s["interventions"].get("training") == 1 and s["avg_latency_ms"] == 120


def test_observatory_shape():
    _seed(3, verdict="GO", intervention="training", latency_ms=100)
    _seed(1, verdict="NOT_YET", intervention="recovery", cold_start=True, latency_ms=100)
    o = ba.observatory()
    assert o["ok"] and o["total_24h"] == 4
    assert o["verdict_pct"]["GO"] == 75.0 and o["verdict_pct"]["NOT_YET"] == 25.0
    assert o["cold_start_rate"] == 25.0
    assert ("training", 3) in o["interventions"]


def test_anomaly_cold_start_high():
    recent = {"total": 20, "verdicts": {"NOT_YET": 20}, "interventions": {},
              "cold_start_rate": 0.95, "avg_latency_ms": 100}
    base = {"total": 100, "verdicts": {"GO": 100}, "interventions": {},
            "cold_start_rate": 0.1, "avg_latency_ms": 100}
    alerts = ba.detect_anomalies(recent, base)
    assert any("cold_start high" in a for a in alerts)


def test_anomaly_no_train_and_medical_and_latency():
    recent = {"total": 40, "verdicts": {"NO_TRAIN": 20, "GO": 20},
              "interventions": {"medical_followup": 20}, "cold_start_rate": 0.1, "avg_latency_ms": 800}
    base = {"total": 400, "verdicts": {"NO_TRAIN": 8, "GO": 392},
            "interventions": {"medical_followup": 8}, "cold_start_rate": 0.1, "avg_latency_ms": 300}
    alerts = " | ".join(ba.detect_anomalies(recent, base))
    assert "NO_TRAIN spike" in alerts and "medical_followup spike" in alerts and "latency doubled" in alerts


def test_low_sample_suppresses_anomalies():
    recent = {"total": 3, "verdicts": {"NO_TRAIN": 3}, "interventions": {},
              "cold_start_rate": 1.0, "avg_latency_ms": 999}
    base = {"total": 100, "verdicts": {"GO": 100}, "interventions": {}, "cold_start_rate": 0.0, "avg_latency_ms": 100}
    assert ba.detect_anomalies(recent, base) == []
