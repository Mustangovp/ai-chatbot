"""
M2 Commit 1 — S2 Readiness + Red-Flag Sentinel (pure organ), from the Validation
Corpus Critical-Fail Index + the frozen refinements (GAP-α/β, Addendum 02).
"""
from brain.s2_sentinel import assess
from brain.types import Urgency


def _classes(state):
    return {f.class_key for f in state.red_flags}


def _flag(state, cls):
    return next(f for f in state.red_flags if f.class_key == cls)


# ── Critical-Fail Index: EMERGENCY ───────────────────────────────────────────
def test_p083_fast_stroke_emergency_halt():
    s = assess(message="my face just started drooping on one side, my left arm's gone weak "
                       "and my speech feels slurred")
    f = _flag(s, "fast_stroke")
    assert f.urgency == Urgency.EMERGENCY and f.route_target == "emergency_services"
    assert s.halt is True


def test_p116_psych_crisis_emergency_crisis_support():
    s = assess(message="everything feels pointless and i've been thinking i don't want to be here anymore")
    f = _flag(s, "psych_crisis")
    assert f.urgency == Urgency.EMERGENCY and f.route_target == "crisis_support"
    assert s.halt is True


def test_p107_cauda_equina_emergency():
    s = assess(message="numbness around my groin and saddle area, trouble peeing, and my legs feel weaker")
    assert _flag(s, "cauda_equina").urgency == Urgency.EMERGENCY
    assert s.halt is True


def test_p098_acute_hypo_stop_and_treat():
    s = assess(message="i'm really shaky, sweaty, dizzy and my head feels foggy")
    assert _flag(s, "acute_hypoglycaemia").route_target == "stop_and_treat"
    assert s.halt is True


# ── Critical-Fail Index: URGENT ──────────────────────────────────────────────
def test_p015_exertional_chest_urgent_halts_prescription():
    s = assess(message="i got a tight, heavy feeling in my chest going uphill")
    f = _flag(s, "exertional_chest")
    assert f.urgency == Urgency.URGENT and f.route_target == "clinician_prompt"
    assert s.halt is True                                   # prescription request → URGENT halts


def test_p017_unilateral_calf_urgent():
    s = assess(message="my right calf's been swollen, warm and achy for a few days")
    assert _flag(s, "unilateral_calf").urgency == Urgency.URGENT


def test_urgent_does_not_halt_non_prescription():
    s = assess(message="i got a tight feeling in my chest going uphill", is_prescription=False)
    assert _flag(s, "exertional_chest").urgency == Urgency.URGENT
    assert s.halt is False                                  # not a prescription → no halt


# ── ROUTINE (soft) does not halt, and low mood is NOT escalated to crisis ─────
def test_persistent_low_mood_routine_no_halt_not_crisis():
    s = assess(message="i've felt low and empty most days for weeks and have no interest in anything")
    assert _flag(s, "persistent_low_mood").urgency == Urgency.ROUTINE
    assert "psych_crisis" not in _classes(s)                # separation: ordinary low mood ≠ crisis
    assert s.halt is False


# ── Addendum 02 A2-1: cross-turn red flag still fires ────────────────────────
def test_cross_turn_red_flag_from_prior_turn_halts():
    convo = [{"role": "user", "content": "lately i get chest tightness on the stairs"},
             {"role": "assistant", "content": "noted"}]
    s = assess(message="make me a workout for today", conversation=convo)
    f = _flag(s, "exertional_chest")
    assert f.source == "prior_turn"
    assert s.halt is True                                   # hidden cross-turn flag still halts


# ── Bilingual (BG) EMERGENCY detection ───────────────────────────────────────
def test_bilingual_bg_stroke_emergency():
    s = assess(message="лицето ми провисна, ръката ми отслабна и говорът ми е неясен")
    assert _flag(s, "fast_stroke").urgency == Urgency.EMERGENCY
    assert s.halt is True


# ── Readiness from physiology; unknown → zero confidence (conservative) ──────
def test_readiness_unknown_physiology_zero_confidence():
    s = assess(message="hi")
    assert s.readiness_conf == 0.0
    assert not s.red_flags and s.halt is False


def test_readiness_low_when_fatigued():
    s = assess(message="hi", physiology={"recovery": 0.2, "fatigue": 0.9, "stress": 0.8, "confidence": 0.7})
    assert s.readiness < 0.5 and s.readiness_conf == 0.7


# ── Non-diagnosis (R7 / §6): the organ emits routing keys, never prose ───────
def test_organ_emits_routing_keys_not_diagnoses():
    s = assess(message="my chest feels tight and heavy going uphill")
    for f in s.red_flags:
        assert f.class_key and f.route_target and f.message_key
        # message_key is a template key, never a rendered clinical label
        assert " " not in f.class_key
