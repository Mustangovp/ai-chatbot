"""
M4 Commit 1 — Safety-Front renderer (pure). Decision → enforcement directive.
No app.py, no flags, no I/O. Asserts: halt never generates, refusals never
generate, GO/MODIFY generate with constraints injected, and non-diagnosis holds.
"""
from brain import cascade
from brain.enforcement import render
from brain.types import (Decision, Verdict, Intervention, S2State, RedFlag, Urgency,
                         ConstraintSet, Constraint, ConstraintTier, CapacityEnvelope)


def _decision(verdict, *, halt=False, flags=(), intervention="training",
              constraints=(), gen=False):
    cs = ConstraintSet()
    for m in constraints:
        cs.add(Constraint(m, ConstraintTier.RELATIVE, "x"))
    return Decision(
        verdict=verdict, intervention=Intervention(intervention, "k"),
        generate_training=gen, halt=halt, verdict_confidence=0.5,
        constraints=cs, envelope=CapacityEnvelope(0.4, 0.4, 0.4, True, 0.6),
        s2=S2State(readiness=0.5, readiness_conf=0.5, red_flags=list(flags), halt=halt),
        need_vector=[], decision_id="d", model=None)


# ── Halt → route, never a workout ────────────────────────────────────────────
def test_emergency_halt_routes_and_blocks_generation():
    d = _decision(Verdict.NOT_YET, halt=True, intervention="medical_followup",
                  flags=[RedFlag("fast_stroke", Urgency.EMERGENCY, "emergency_services", "k")])
    r = render(d)
    assert r["mode"] == "route"
    assert r["should_generate_workout"] is False
    assert r["decision_event"]["route"] == "emergency_services"
    assert r["decision_event"]["urgency"] == "EMERGENCY_now"
    assert "emergency" in r["system_prompt_addendum"].lower()


def test_crisis_halt_uses_crisis_route():
    d = _decision(Verdict.NOT_YET, halt=True, intervention="crisis_support",
                  flags=[RedFlag("psych_crisis", Urgency.EMERGENCY, "crisis_support", "k")])
    r = render(d)
    assert r["should_generate_workout"] is False
    assert "crisis" in r["system_prompt_addendum"].lower()


# ── Refuse / defer → no workout, with an alternative ─────────────────────────
def test_no_train_refuses_generation():
    d = _decision(Verdict.NO_TRAIN, intervention="recovery")
    r = render(d)
    assert r["mode"] == "refuse" and r["should_generate_workout"] is False


def test_not_yet_defers_generation():
    d = _decision(Verdict.NOT_YET, intervention="sleep")
    r = render(d)
    assert r["mode"] == "defer" and r["should_generate_workout"] is False
    assert "sleep" in r["system_prompt_addendum"].lower()


# ── GO / MODIFY → generate, constraints injected ─────────────────────────────
def test_go_proceeds_generation():
    d = _decision(Verdict.GO, intervention="training", gen=True)
    r = render(d)
    assert r["mode"] == "proceed" and r["should_generate_workout"] is True


def test_modify_injects_constraints():
    d = _decision(Verdict.MODIFY, intervention="training", gen=True, constraints=["valsalva", "high_impact"])
    r = render(d)
    assert r["should_generate_workout"] is True
    add = r["system_prompt_addendum"]
    assert "valsalva" in add and "high_impact" in add and "0.4" in add


# ── Non-diagnosis is structural ──────────────────────────────────────────────
def test_no_diagnosis_language_in_safety_overrides():
    for d in [_decision(Verdict.NOT_YET, halt=True, intervention="medical_followup",
                        flags=[RedFlag("exertional_chest", Urgency.URGENT, "clinician_prompt", "k")]),
              _decision(Verdict.NO_TRAIN, intervention="recovery")]:
        add = render(d)["system_prompt_addendum"].lower()
        assert "do not" in add and "diagnos" in add          # explicit no-diagnosis instruction
        # the internal class_key must never be leaked into the directive
        assert "exertional_chest" not in add


# ── End-to-end: a real cascade Decision renders safely ───────────────────────
def test_renders_a_live_cascade_halt_decision():
    d = cascade.decide({}, message="my chest feels tight and heavy going uphill")
    r = render(d)
    assert d.halt is True and r["should_generate_workout"] is False and r["mode"] == "route"
