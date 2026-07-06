"""
M3 Commit 3 — S5 Intervention Selector (pure organ). Training is one of ~ten
interventions and often not the winner; generation is gated behind it.
"""
from brain.s5_selector import select, generate_training
from brain.types import Verdict, RedFlag, Urgency, S2State


def _s2(halt=False, flags=()):
    return S2State(readiness=0.6, readiness_conf=0.6, red_flags=list(flags), halt=halt)


def _nv(*needs):
    return [(n, 1.0 - i * 0.1) for i, n in enumerate(needs)]


# ── Halt → route to the strongest flag's target ──────────────────────────────
def test_halt_crisis_selects_crisis_support():
    s2 = _s2(halt=True, flags=[RedFlag("psych_crisis", Urgency.EMERGENCY, "crisis_support", "k")])
    iv = select(verdict=Verdict.NOT_YET, s2=s2, need_vector=_nv("medical_followup"))
    assert iv.kind == "crisis_support"


def test_halt_emergency_selects_medical_followup():
    s2 = _s2(halt=True, flags=[RedFlag("fast_stroke", Urgency.EMERGENCY, "emergency_services", "k")])
    iv = select(verdict=Verdict.NOT_YET, s2=s2, need_vector=_nv("medical_followup"))
    assert iv.kind == "medical_followup"


def test_halt_prefers_strongest_flag():
    s2 = _s2(halt=True, flags=[
        RedFlag("persistent_low_mood", Urgency.ROUTINE, "gp_soft", "k"),
        RedFlag("psych_crisis", Urgency.EMERGENCY, "crisis_support", "k")])
    assert select(verdict=Verdict.NOT_YET, s2=s2, need_vector=_nv("training")).kind == "crisis_support"


# ── GO / MODIFY → training when it's the top need ─────────────────────────────
def test_go_training_top_selects_training():
    iv = select(verdict=Verdict.GO, s2=_s2(), need_vector=_nv("training", "gentle_movement"))
    assert iv.kind == "training"
    assert generate_training(Verdict.GO, iv) is True


def test_modify_training_top_still_generates_training():
    iv = select(verdict=Verdict.MODIFY, s2=_s2(), need_vector=_nv("training", "nutrition"))
    assert iv.kind == "training" and generate_training(Verdict.MODIFY, iv) is True


# ── The coach move: permitted to train, but a non-training need is more valuable
def test_modify_soft_top_selects_non_training():
    iv = select(verdict=Verdict.MODIFY, s2=_s2(), need_vector=_nv("gentle_movement", "training"))
    assert iv.kind == "walk"
    assert generate_training(Verdict.MODIFY, iv) is False


# ── Defer / refuse → best non-training alternative; no generation ────────────
def test_not_yet_recovery_selects_recovery_no_generation():
    iv = select(verdict=Verdict.NOT_YET, s2=_s2(), need_vector=_nv("recovery", "training"))
    assert iv.kind == "recovery"
    assert generate_training(Verdict.NOT_YET, iv) is False


def test_not_yet_with_routine_flag_routes_to_medical():
    s2 = _s2(flags=[RedFlag("disproportionate_fatigue", Urgency.ROUTINE, "gp_soft", "k")])
    iv = select(verdict=Verdict.NOT_YET, s2=s2, need_vector=_nv("recovery"))
    assert iv.kind == "medical_followup"


def test_no_train_never_generates_training():
    iv = select(verdict=Verdict.NO_TRAIN, s2=_s2(), need_vector=_nv("gentle_movement"))
    assert iv.kind != "training"
    assert generate_training(Verdict.NO_TRAIN, iv) is False


# ── Determinism ──────────────────────────────────────────────────────────────
def test_deterministic():
    args = dict(verdict=Verdict.MODIFY, s2=_s2(), need_vector=_nv("gentle_movement", "training"))
    assert select(**args) == select(**args)
