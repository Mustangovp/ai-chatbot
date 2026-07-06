"""
ADR-001 — cold-start policy exception (enforcement layer ONLY).

Proves a healthy anonymous first-timer receives a conservative beginner workout,
while EVERY existing safety behaviour is preserved, and the cascade / replay /
ledger are untouched (the Decision stays truthfully NOT_YET).
"""
from brain import cascade, replay
from brain.enforcement import render, _is_cold_start
from brain.types import (Decision, Verdict, Intervention, S2State, RedFlag, Urgency,
                         ConstraintSet, Constraint, ConstraintTier, CapacityEnvelope)


def _decision(verdict, *, halt=False, flags=(), constraints=(), readiness_conf=0.0,
              intervention="training"):
    cs = ConstraintSet()
    for m in constraints:
        cs.add(Constraint(m, ConstraintTier.RELATIVE, "x"))
    return Decision(
        verdict=verdict, intervention=Intervention(intervention, "k"),
        generate_training=False, halt=halt, verdict_confidence=0.0,
        constraints=cs, envelope=CapacityEnvelope(0.35, 0.35, 0.35, True, 0.0),
        s2=S2State(readiness=0.5, readiness_conf=readiness_conf, red_flags=list(flags), halt=halt),
        need_vector=[], decision_id="d", model=None)


# ── 1. Healthy cold-start → conservative beginner workout (REAL cascade) ──────
def test_healthy_cold_start_generates_conservative_workout():
    d = cascade.decide({}, message="I'm healthy, give me a workout for today")
    # Precondition: the real cascade yields exactly the cold-start shape.
    assert d.verdict is Verdict.NOT_YET and not d.halt and not d.s2.red_flags
    assert d.constraints.is_empty() and d.s2.readiness_conf == 0.0
    r = render(d)
    assert r["mode"] == "cold_start" and r["should_generate_workout"] is True
    assert r["decision_event"]["cold_start"] is True
    assert r["decision_event"]["verdict"] == "NOT_YET"      # Decision remains truthful
    assert "beginner" in r["system_prompt_addendum"].lower()


def test_healthy_73yo_cold_start_generates_workout():
    d = cascade.decide({}, message="I'm 73, healthy and active — give me a strength workout")
    r = render(d)
    assert r["mode"] == "cold_start" and r["should_generate_workout"] is True


# ── 2. Chest pain STILL routes — cold-start never masks a halt (REAL cascade) ─
def test_chest_pain_still_routes():
    d = cascade.decide({}, message="my chest feels tight and heavy going uphill")
    assert d.halt is True
    r = render(d)
    assert r["mode"] == "route" and r["should_generate_workout"] is False
    assert r["decision_event"]["cold_start"] is False


# ── 3. Acute stroke symptoms STILL route (REAL cascade) ──────────────────────
def test_acute_stroke_still_routes():
    d = cascade.decide({}, message="the right side of my face has drooped and my speech is slurred")
    assert d.halt is True
    r = render(d)
    assert r["mode"] == "route" and r["should_generate_workout"] is False
    assert r["decision_event"]["cold_start"] is False


# ── 4. Constraints STILL handled by the normal path — not cold-started ────────
def test_constraint_profile_is_not_cold_started():
    # A known condition (hypertension) → S1 constraints → MODIFY (constraint-aware
    # workout), NOT a generic beginner plan.
    d = cascade.decide({"healthNotes": "high blood pressure"}, message="give me a workout")
    assert not d.constraints.is_empty()
    assert _is_cold_start(d) is False
    r = render(d)
    assert r["mode"] != "cold_start"
    assert "valsalva" in r["system_prompt_addendum"]          # the constraint is honoured


def test_not_yet_with_constraints_defers_not_cold_start():
    # A NOT_YET that carries constraints must DEFER, never cold-start.
    d = _decision(Verdict.NOT_YET, constraints=("valsalva",))
    assert _is_cold_start(d) is False
    r = render(d)
    assert r["mode"] == "defer" and r["should_generate_workout"] is False


# ── 5. Gate integrity — every disqualifier blocks cold-start ─────────────────
def test_routine_red_flag_blocks_cold_start():
    d = _decision(Verdict.NOT_YET, flags=[RedFlag("persistent_low_mood", Urgency.ROUTINE, "gp_soft", "k")])
    assert _is_cold_start(d) is False
    assert render(d)["should_generate_workout"] is False


def test_athlete_model_user_is_never_cold_started():
    # A KNOWN user (readiness_conf > 0) who defers — e.g. genuinely depleted — must
    # NOT be handed a workout. Cold-start applies ONLY to the no-data case.
    d = _decision(Verdict.NOT_YET, readiness_conf=0.6)
    assert _is_cold_start(d) is False
    assert render(d)["mode"] == "defer" and render(d)["should_generate_workout"] is False


def test_no_train_is_never_cold_started():
    d = _decision(Verdict.NO_TRAIN)          # categorical refusal, even with no data
    assert _is_cold_start(d) is False
    assert render(d)["should_generate_workout"] is False


# ── 6. Replay determinism unchanged (cascade untouched by the policy change) ──
def test_replay_determinism_unchanged():
    ev = {"profile": {}, "message": "I'm healthy, give me a workout"}
    base = replay._run(ev)
    rr = replay.replay(ev, base)
    assert rr["classification"] == replay.IDENTICAL and rr["first_divergence"] is None
    assert base["cascade"]["verdict"] == "NOT_YET"            # logged verdict still NOT_YET


# ── 7. Ledger / Decision unchanged — render() must not mutate the Decision ────
def test_enforcement_does_not_mutate_the_decision_or_trace():
    d = cascade.decide({}, message="I'm healthy, give me a workout")
    before = (d.verdict, d.halt, d.generate_training, dict(d.trace_core["cascade"]))
    render(d)                                                  # render must be side-effect free
    assert (d.verdict, d.halt, d.generate_training, dict(d.trace_core["cascade"])) == before
    # what the ledger stores (trace cascade block) is byte-identical, verdict still NOT_YET
    assert d.trace_core["cascade"]["verdict"] == "NOT_YET"
