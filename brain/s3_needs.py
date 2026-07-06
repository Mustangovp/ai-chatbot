"""
APEX Brain — Station S3: the Need Vector (frozen E1 Stakes Arbiter).

Computes *what matters most today* — a ranked vector over the full need space —
BEFORE deciding to train. Pure function; deterministic with a stable tie-break
(replay-safe, per the cascade determinism guardrail). No Flask, no DB, no OpenAI.
Reads S1's envelope + S2's readiness/red-flags + profile goal + (optional)
Athlete Model state. Training is one need among many and frequently not the top.

Stakes order (frozen): safety > relationship > habit > adaptation > today, with
feed-the-scarcer-account resolving ties (spend the abundant account, protect the
scarce one). This organ ranks; it never decides — S4 owns the verdict.
"""
from brain.types import Urgency

NEEDS = ("medical_followup", "recovery", "sleep", "stress_reduction",
         "gentle_movement", "nutrition", "conversation", "training")

_URGENCY_WEIGHT = {Urgency.EMERGENCY: 1.0, Urgency.URGENT: 0.85, Urgency.ROUTINE: 0.5}


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _state_var(athlete_state, name, default):
    try:
        return float(athlete_state["vars"][name]["value"])
    except (KeyError, TypeError, ValueError):
        return default


def rank(*, envelope, s2, profile=None, athlete_state=None):
    """Return a ranked [(need, weight)] list, highest need first. Deterministic:
    ordered by weight desc, then need name asc (stable tie-break)."""
    profile = profile or {}
    goal = str(profile.get("goal") or "").lower()
    readiness = float(getattr(s2, "readiness", 0.5))
    halt = bool(getattr(s2, "halt", False))
    flags = getattr(s2, "red_flags", []) or []

    # Safety (top of the stakes order): medical follow-up scales with the
    # strongest red flag present.
    med = max((_URGENCY_WEIGHT[f.urgency] for f in flags), default=0.0)

    # Scarce accounts — recovery / sleep / stress. Prefer the Athlete Model when
    # available; else fall back to readiness-derived estimates.
    fatigue = _state_var(athlete_state, "physical_fatigue", _clamp(1.0 - readiness))
    sleep_q = _state_var(athlete_state, "sleep_quality", readiness)
    stress = _state_var(athlete_state, "stress", 0.3)

    scores = {
        "medical_followup": med,
        "recovery": _clamp(0.30 + fatigue * 0.60),
        "sleep": _clamp(0.30 + (1.0 - sleep_q) * 0.60),
        "stress_reduction": _clamp(0.20 + stress * 0.60),
        "gentle_movement": _clamp(0.50 + (0.25 if envelope.intensity_ceiling < 0.40 else 0.0)),
        "nutrition": _clamp(0.40 + (0.15 if goal == "fat_loss" else 0.0)),
        "conversation": 0.30,
        # Adaptation / today — training only ranks when it's earned; zero on a halt.
        "training": 0.0 if halt else _clamp(
            readiness * envelope.intensity_ceiling
            + (0.15 if goal in ("muscle_gain", "strength", "endurance") else 0.0)),
    }
    return sorted(scores.items(), key=lambda kv: (-round(kv[1], 6), kv[0]))
