"""
APEX — M5 Brain Observatory (analytics only).

A failure-isolated observability layer AROUND the Brain. It reads the enforcement
decision that the pipeline already produced and records it for the /admin/brain
dashboard. It contains NO Brain logic, imports no organ, and can never affect a
decision, a prompt, generation, or a reply. First-party only — no third-party
analytics; everything lives in APEX's own Postgres.
"""
import hashlib

import db as store

_VERDICTS = ("GO", "MODIFY", "NOT_YET", "NO_TRAIN")
# Interventions surfaced on the dashboard (roadmap list), in display order.
_INTERVENTIONS = ("training", "recovery", "nutrition", "sleep", "stress_reduction",
                  "conversation", "medical_followup")


def anon_id(subject) -> str:
    """One-way, non-reversible id for a subject ('user:<id>' / 'device:<id>' / ip).
    Never stores the raw identifier."""
    raw = ":".join(str(p) for p in subject) if isinstance(subject, (tuple, list)) else str(subject)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def record(subject, decision_event, latency_ms):
    """Persist one analytics row from the enforcement decision_event. Failure-isolated —
    never raises to the caller (a Brain/analytics error must never break a reply)."""
    try:
        ev = decision_event or {}
        store.log_brain_event(
            anon_id=anon_id(subject),
            verdict=ev.get("verdict"),
            urgency=ev.get("urgency"),
            intervention=ev.get("intervention"),
            route=ev.get("route"),
            cold_start=bool(ev.get("cold_start")),
            enforcement_generate=bool(ev.get("generate")),
            latency_ms=int(latency_ms) if latency_ms is not None else None,
        )
    except Exception as e:
        print(f"[analytics] record failed: {e}")


def _pct(counts: dict, total: int) -> dict:
    return {k: round(100.0 * counts.get(k, 0) / total, 1) if total else 0.0 for k in _VERDICTS}


def detect_anomalies(recent: dict, baseline: dict) -> list:
    """Compare a short recent window to a longer baseline and flag the four M5 rules.
    Requires a minimum recent sample so a cold start / low traffic isn't flagged as noise."""
    alerts = []
    r_total, b_total = recent["total"], baseline["total"]
    if r_total < 10:
        return alerts                              # not enough recent signal to judge

    r_v, b_v = _pct(recent["verdicts"], r_total), _pct(baseline["verdicts"], b_total)

    # NO_TRAIN spike — recent share ≥ 2× baseline and materially present.
    if r_v["NO_TRAIN"] >= 10.0 and r_v["NO_TRAIN"] >= 2.0 * max(b_v["NO_TRAIN"], 0.1):
        alerts.append(f"NO_TRAIN spike: {r_v['NO_TRAIN']}% recent vs {b_v['NO_TRAIN']}% baseline")

    # medical_followup spike — recent intervention share ≥ 2× baseline.
    r_med = 100.0 * recent["interventions"].get("medical_followup", 0) / r_total
    b_med = 100.0 * baseline["interventions"].get("medical_followup", 0) / b_total if b_total else 0.0
    if r_med >= 10.0 and r_med >= 2.0 * max(b_med, 0.1):
        alerts.append(f"medical_followup spike: {round(r_med,1)}% recent vs {round(b_med,1)}% baseline")

    # Latency doubled vs baseline.
    if baseline["avg_latency_ms"] > 0 and recent["avg_latency_ms"] >= 2 * baseline["avg_latency_ms"]:
        alerts.append(f"latency doubled: {recent['avg_latency_ms']}ms recent vs {baseline['avg_latency_ms']}ms baseline")

    # Cold-start rate above 80%.
    if recent["cold_start_rate"] > 0.80:
        alerts.append(f"cold_start high: {round(recent['cold_start_rate']*100,1)}% of recent decisions")

    return alerts


def observatory():
    """Assemble the full dashboard payload from the analytics store."""
    try:
        recent = store.brain_events_stats(hours=1)
        window = store.brain_events_stats(hours=24)
        baseline = store.brain_events_stats(hours=24)   # 24h baseline for anomaly comparison
        daily = store.brain_events_daily(days=7)
        total = window["total"]
        interventions = [(k, window["interventions"].get(k, 0)) for k in _INTERVENTIONS]
        # include any intervention seen but not in the canonical list
        for k, v in window["interventions"].items():
            if k not in _INTERVENTIONS:
                interventions.append((k, v))
        interventions.sort(key=lambda kv: kv[1], reverse=True)
        return {
            "ok": True,
            "total_24h": total,
            "verdict_pct": _pct(window["verdicts"], total),
            "verdict_counts": {k: window["verdicts"].get(k, 0) for k in _VERDICTS},
            "interventions": interventions,
            "cold_start_rate": round(window["cold_start_rate"] * 100, 1),
            "avg_latency_ms": window["avg_latency_ms"],
            "daily": daily,
            "recent_1h": recent["total"],
            "anomalies": detect_anomalies(recent, baseline),
        }
    except Exception as e:
        print(f"[analytics] observatory failed: {e}")
        return {"ok": False, "error": str(e)}
