"""
M3 Commit 2 — S4 Appropriateness Gate (pure organ). One verdict per reachable
cell of the frozen S4 Truth Table; halt is defense-in-depth (contract C2).
"""
from brain.s4_gate import decide
from brain.types import Verdict, ConstraintSet, Constraint, ConstraintTier, CapacityEnvelope, S2State


def _cs(*movements):
    cs = ConstraintSet()
    for m in movements:
        cs.add(Constraint(m, ConstraintTier.RELATIVE, "x"))
    return cs


def _env(conf=0.6, intensity=0.6):
    return CapacityEnvelope(intensity, intensity, intensity, False, conf)


def _s2(halt=False, conf=0.6):
    return S2State(readiness=0.6, readiness_conf=conf, red_flags=[], halt=halt)


def _nv(top):
    return [(top, 0.9), ("gentle_movement", 0.5), ("nutrition", 0.4)]


def _v(**kw):
    return decide(**kw)[0]


# ── Reachable cells of the truth table ───────────────────────────────────────
def test_clear_training_go():
    assert _v(constraints=_cs(), envelope=_env(), s2=_s2(), need_vector=_nv("training")) == Verdict.GO


def test_clear_recovery_not_yet():
    assert _v(constraints=_cs(), envelope=_env(), s2=_s2(), need_vector=_nv("recovery")) == Verdict.NOT_YET


def test_modify_training_modify():
    assert _v(constraints=_cs("valsalva"), envelope=_env(), s2=_s2(),
              need_vector=_nv("training")) == Verdict.MODIFY


def test_modify_recovery_not_yet():
    assert _v(constraints=_cs("valsalva"), envelope=_env(), s2=_s2(),
              need_vector=_nv("recovery")) == Verdict.NOT_YET


def test_modify_soft_modify():
    assert _v(constraints=_cs("high_impact"), envelope=_env(), s2=_s2(),
              need_vector=_nv("gentle_movement")) == Verdict.MODIFY


# ── Companion rules ──────────────────────────────────────────────────────────
def test_halt_is_defense_in_depth_never_trains():
    # Even with a "training" need + no constraints, a halt can never yield GO/MODIFY.
    assert _v(constraints=_cs(), envelope=_env(), s2=_s2(halt=True),
              need_vector=_nv("training")) == Verdict.NOT_YET


def test_low_confidence_defers():
    assert _v(constraints=_cs(), envelope=_env(conf=0.0), s2=_s2(conf=0.0),
              need_vector=_nv("training")) == Verdict.NOT_YET


def test_medical_dominant_defers_defense_in_depth():
    assert _v(constraints=_cs(), envelope=_env(), s2=_s2(),
              need_vector=_nv("medical_followup")) == Verdict.NOT_YET


# ── Seed libraries never BLOCK → heavy constraints are MODIFY, not NO_TRAIN ───
def test_heavy_constraints_are_modify_not_no_train():
    assert _v(constraints=_cs("valsalva", "maximal_exertion", "unsupported_balance", "high_impact"),
              envelope=_env(intensity=0.1), s2=_s2(),
              need_vector=_nv("gentle_movement")) == Verdict.MODIFY


# ── Determinism ──────────────────────────────────────────────────────────────
def test_deterministic():
    args = dict(constraints=_cs("valsalva"), envelope=_env(), s2=_s2(), need_vector=_nv("training"))
    assert decide(**args) == decide(**args)
