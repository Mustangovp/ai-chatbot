"""
BUILD-004 — Human Trajectory Engine: trend/velocity/volatility/direction/risk over
the existing human_state_events history, plus Adaptive Coach integration.
"""
import datetime as _dt

from human_state import trajectory
import coaching
from coaching import adaptive
import db as store
from brain import cascade, enforcement
from brain.types import (Decision, Verdict, Intervention, S2State, ConstraintSet, CapacityEnvelope)

UTC = _dt.timezone.utc
_NOW = _dt.datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)


def _event(subject, key, value, days_ago):
    with store.engine.begin() as c:
        c.execute(store.insert(store.human_state_events).values(
            id=store.uuid.uuid4(), subject=subject, message="m",
            transitions=[{"key": key, "extracted_value": value, "confidence": 0.8}],
            latency_ms=1.0, created_at=_NOW - _dt.timedelta(days=days_ago)))


def _decision(gen=True):
    return Decision(verdict=Verdict.MODIFY, intervention=Intervention("training", "k"),
                    generate_training=gen, halt=False, verdict_confidence=0.6, constraints=ConstraintSet(),
                    envelope=CapacityEnvelope(0.5, 0.5, 0.5, False, 0.6),
                    s2=S2State(readiness=0.6, readiness_conf=0.6, red_flags=[], halt=False),
                    need_vector=[], decision_id="d", model=None)


# ── velocity / volatility / direction ────────────────────────────────────────
def test_slope_and_direction():
    pts = [(0, 0.0), (5, 0.5), (10, 1.0)]                 # rising
    assert trajectory._slope(pts) > 0
    assert trajectory._direction("motivation", trajectory._slope(pts)) == "improving"  # +polarity
    assert trajectory._direction("fatigue", trajectory._slope(pts)) == "declining"     # -polarity


def test_volatility_reflects_spread():
    steady = trajectory._stdev([(0, 0.5), (1, 0.5), (2, 0.5)])
    erratic = trajectory._stdev([(0, 0.0), (1, 1.0), (2, 0.0)])
    assert steady == 0.0 and erratic > steady


# ── longitudinal: rising fatigue → recovery declining + risk ────────────────
def test_longitudinal_declining_recovery():
    s = "device:tj1"
    _event(s, "fatigue", "low", 10)
    _event(s, "fatigue", "moderate", 6)
    _event(s, "fatigue", "high", 2)
    _event(s, "fatigue", "high", 0)
    t = trajectory.compute(s, now=_NOW)
    assert t["ok"] and t["sufficient"]
    assert t["recovery_direction"] == "declining"
    assert "fatigue rising" in t["risk"]["reasons"]
    assert t["per_key"]["fatigue"]["points"] == 4


def test_longitudinal_improving_adherence():
    s = "device:tj2"
    for v, d in [("missed", 12), ("gap", 8), ("note", 4), ("note", 1)]:
        _event(s, "adherence", v, d)
    t = trajectory.compute(s, now=_NOW)
    assert t["adherence_direction"] == "improving" and t["trajectory"] in ("improving", "mixed")


# ── insufficient data ────────────────────────────────────────────────────────
def test_insufficient_history():
    s = "device:tj3"
    _event(s, "sleep", "4", 1)                            # only 1 point
    t = trajectory.compute(s, now=_NOW)
    assert t["ok"] and t["sufficient"] is False and t["trajectory"] == "unknown"


# ── replay determinism ───────────────────────────────────────────────────────
def test_replay_deterministic():
    s = "device:tj4"
    for v, d in [("high", 9), ("moderate", 6), ("low", 3), ("low", 0)]:
        _event(s, "stress", v, d)
    a = trajectory.compute(s, now=_NOW)
    b = trajectory.compute(s, now=_NOW)
    assert a == b


# ── read-only / Brain regression ─────────────────────────────────────────────
def test_trajectory_is_read_only_and_brain_untouched():
    s = "device:tj5"
    for v, d in [("high", 6), ("high", 3), ("moderate", 0)]:
        _event(s, "fatigue", v, d)
    before = cascade.decide({"goal": "strength"}, message="give me a workout")
    trajectory.compute(s, now=_NOW)
    after = cascade.decide({"goal": "strength"}, message="give me a workout")
    assert (before.verdict, before.halt) == (after.verdict, after.halt)
    assert store.hs_get_all(s) == []                     # computed nothing into current state


# ── Adaptive Coach integration ───────────────────────────────────────────────
def test_adaptive_uses_trajectory_when_enabled(monkeypatch):
    s = "device:tj6"
    for v, d in [("low", 10), ("moderate", 6), ("high", 2), ("high", 0)]:
        _event(s, "fatigue", v, d)                        # declining recovery
    d_, dir_ = _decision(), enforcement.render(_decision())
    monkeypatch.setenv("HSE_TRAJECTORY", "1")
    res = adaptive.adapt(s, "what should I do", d_, dir_, now=_NOW)
    variables = {a["variable"] for a in res["adaptations"]}
    assert "recovery_trend" in variables
    # trajectory adaptation still cites all four fields
    rt = next(a for a in res["adaptations"] if a["variable"] == "recovery_trend")
    assert rt["reason"] and rt["rule"] and rt["principle"]


def test_adaptive_ignores_trajectory_when_disabled(monkeypatch):
    s = "device:tj7"
    for v, d in [("low", 10), ("high", 2), ("high", 0)]:
        _event(s, "fatigue", v, d)
    monkeypatch.delenv("HSE_TRAJECTORY", raising=False)
    res = adaptive.adapt(s, "what should I do", _decision(), enforcement.render(_decision()), now=_NOW)
    assert not any(a["variable"].endswith("_trend") for a in res["adaptations"])


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("HSE_TRAJECTORY", raising=False)
    assert trajectory.enabled() is False
