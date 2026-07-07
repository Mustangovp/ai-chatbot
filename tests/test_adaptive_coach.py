"""
BUILD-003 — Adaptive Coach: adaptation from Human State + explainability + the
production-safety guarantees (never override safety / withheld workout / raise load).
"""
import datetime as _dt

import coaching
from coaching import adaptive
import human_state
from human_state import engine, extractor
import db as store
from brain import cascade, enforcement
from brain.types import (Decision, Verdict, Intervention, S2State, ConstraintSet,
                         Constraint, ConstraintTier, CapacityEnvelope)

UTC = _dt.timezone.utc
def _now(**kw):
    return _dt.datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC) + _dt.timedelta(**kw)


def _decision(verdict=Verdict.MODIFY, halt=False, intervention="training", gen=True, constraints=()):
    cs = ConstraintSet()
    for m in constraints:
        cs.add(Constraint(m, ConstraintTier.RELATIVE, "k"))
    return Decision(verdict=verdict, intervention=Intervention(intervention, "k"),
                    generate_training=gen, halt=halt, verdict_confidence=0.6, constraints=cs,
                    envelope=CapacityEnvelope(0.5, 0.5, 0.5, False, 0.6),
                    s2=S2State(readiness=0.6, readiness_conf=0.6, red_flags=[], halt=halt),
                    need_vector=[], decision_id="d", model=None)


def _vars(res):
    return {a["variable"] for a in res["adaptations"]}


# ── Adaptation from state ────────────────────────────────────────────────────
def test_adapts_to_fatigue_and_time_when_generating():
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c1", "I'm exhausted and I only have 15 minutes", d, dir_, now=_now())
    assert res["applied"]
    assert {"fatigue", "time_availability"} <= _vars(res)
    assert "15 minutes" in res["addendum"]


def test_low_motivation_is_supportive():
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c2", "I have no motivation lately", d, dir_, now=_now())
    assert "motivation" in _vars(res) and res["style"] == "supportive"


def test_pain_uses_pain_free_rule():
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c3", "my knee hurts today", d, dir_, now=_now())
    pain = next(a for a in res["adaptations"] if a["variable"] == "pain")
    assert "MOV" in pain["principle"] and "pain-free" in res["addendum"].lower()


# ── Explainability ───────────────────────────────────────────────────────────
def test_every_adaptation_cites_all_four():
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c4", "I'm exhausted, stressed, no motivation, only 20 minutes",
                         d, dir_, profile={"goal": "strength"}, now=_now())
    assert res["applied"]
    for a in res["adaptations"]:
        assert a["variable"] and a["reason"] and a["rule"] and a["principle"]


# ── Persistent state (memory) drives adaptation ──────────────────────────────
def test_persistent_state_used_across_turns():
    now = _now()
    engine.apply("device:c5", extractor.extract("I'm exhausted", now=now), now=now)   # stored earlier
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c5", "what should I do today", d, dir_, now=now)      # benign message
    assert "fatigue" in _vars(res)                                                     # memory recalled


# ── PRODUCTION SAFETY ────────────────────────────────────────────────────────
def test_no_workout_shaping_when_generation_withheld():
    halt = _decision(verdict=Verdict.NOT_YET, halt=True, intervention="medical_followup", gen=False)
    dir_ = enforcement.render(halt)
    assert dir_["should_generate_workout"] is False
    res = adaptive.adapt("device:c6", "I'm exhausted, only 15 minutes, I'm travelling", halt, dir_, now=_now())
    # workout-shaping variables must NOT fire when a workout was withheld
    assert not ({"time_availability", "travel", "equipment", "fatigue"} & _vars(res))
    # and the enforcement directive is untouched (adaptation never overrides it)
    assert dir_["should_generate_workout"] is False and dir_["mode"] == "route"


def test_addendum_never_increases_load_and_keeps_clamp():
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c7", "I'm exhausted and stressed", d, dir_, now=_now())
    low = res["addendum"].lower()
    # the clamp is always present (negated "do not increase …")
    assert "do not override the safety directive" in low and "do not add a workout" in low
    # the adaptation BODY (after the clamp) must never affirmatively raise load
    body = low.split("adapt as follows:", 1)[1]
    for banned in ("increase", "heavier", "more intense", "push harder", "harder", "add volume"):
        assert banned not in body


def test_adaptation_is_read_only_brain_and_state_untouched():
    profile = {"healthNotes": "high blood pressure", "goal": "strength"}
    before = cascade.decide(profile, message="give me a workout")
    d = _decision(); dir_ = enforcement.render(d)
    adaptive.adapt("device:c8", "I'm exhausted, my knee hurts, no motivation", d, dir_, now=_now())
    after = cascade.decide(profile, message="give me a workout")
    assert (before.verdict, before.halt, before.generate_training) == \
           (after.verdict, after.halt, after.generate_training)          # Brain unchanged
    assert store.hs_get_all("device:c8") == []                            # adapt persists nothing


# ── Flag + determinism ───────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("HSE_CONSUMER", raising=False)
    assert coaching.enabled() is False
    monkeypatch.setenv("HSE_CONSUMER", "1")
    assert coaching.enabled() is True


def test_replay_deterministic():
    d = _decision(); dir_ = enforcement.render(d)
    args = ("device:c9", "I'm exhausted and stressed, only 15 minutes")
    a = adaptive.adapt(*args, d, dir_, now=_now())
    b = adaptive.adapt(*args, d, dir_, now=_now())
    assert a == b


def test_no_state_no_adaptation():
    d = _decision(); dir_ = enforcement.render(d)
    res = adaptive.adapt("device:c10", "hello there", d, dir_, now=_now())
    assert res["applied"] is False and res["adaptations"] == []
