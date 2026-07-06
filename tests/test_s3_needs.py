"""
M3 Commit 1 — S3 Need Vector (pure organ). Frozen E1 stakes; deterministic.
"""
from brain.s3_needs import rank
from brain.types import S2State, RedFlag, Urgency, CapacityEnvelope


def _env(intensity):
    return CapacityEnvelope(intensity, intensity, intensity, False, 0.5)


def _s2(readiness, flags=(), halt=False):
    return S2State(readiness=readiness, readiness_conf=0.5, red_flags=list(flags), halt=halt)


# ── P-035: red flag + low readiness → medical follow-up top, training bottom ──
def test_p035_medical_top_training_bottom():
    s2 = _s2(0.2, [RedFlag("worsening_dyspnea", Urgency.URGENT, "clinician_prompt", "x")], halt=True)
    ranked = rank(envelope=_env(0.15), s2=s2, profile={"goal": "general"})
    needs = [n for n, _ in ranked]
    assert needs[0] == "medical_followup"
    assert needs[-1] == "training"


# ── P-036: healthy, ready, no flags, adaptation goal → training top ──────────
def test_p036_training_top_no_medical():
    s2 = _s2(0.85, [], halt=False)
    ranked = rank(envelope=_env(0.90), s2=s2, profile={"goal": "strength"})
    assert ranked[0][0] == "training"
    assert dict(ranked)["medical_followup"] == 0.0


# ── A halt zeroes training regardless of readiness/envelope ──────────────────
def test_halt_zeroes_training_and_maxes_medical():
    s2 = _s2(0.9, [RedFlag("fast_stroke", Urgency.EMERGENCY, "emergency_services", "x")], halt=True)
    d = dict(rank(envelope=_env(0.9), s2=s2, profile={"goal": "strength"}))
    assert d["training"] == 0.0
    assert d["medical_followup"] == 1.0


# ── Deterministic + stable tie-break (replay-safe) ───────────────────────────
def test_deterministic_stable_order():
    s2 = _s2(0.5, [], halt=False)
    a = rank(envelope=_env(0.5), s2=s2, profile={})
    b = rank(envelope=_env(0.5), s2=s2, profile={})
    assert a == b
    # ties resolve alphabetically by need name
    weights = [w for _, w in a]
    assert weights == sorted(weights, reverse=True)


# ── Covers the whole need space, weights in range ────────────────────────────
def test_full_need_space_and_bounds():
    ranked = dict(rank(envelope=_env(0.6), s2=_s2(0.6), profile={"goal": "fat_loss"}))
    assert set(ranked) == {"medical_followup", "recovery", "sleep", "stress_reduction",
                           "gentle_movement", "nutrition", "conversation", "training"}
    assert all(0.0 <= w <= 1.0 for w in ranked.values())
    assert ranked["nutrition"] > 0.4          # fat_loss goal lifts nutrition
