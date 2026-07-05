"""
APEX Brain — Station S1: the Somatic Constraint Model.

Converts who-this-human-is into what-is-safe-and-possible: a ConstraintSet
(movements, never diagnoses) and a Capacity Envelope (intensity/complexity/
volume ceilings + supported + confidence).

Pure function over the profile (+ optional Athlete Model state). No Flask, no
DB, no OpenAI. Reads the free-text `healthNotes` field (legacy: `injuries`)
via the curated Constraint Library. In M1 this runs SHADOW-ONLY.

Envelope is a function of EVIDENCE, not of age/disability labels: an absence of
constraints in a trained/active person yields a WIDE envelope (the
anti-infantilization guard — Final Review CONCERN-ledger A). Sparse profiles
yield LOW confidence, which biases later stations conservative.
"""
from brain.types import ConstraintSet, CapacityEnvelope, ConstraintTier
from brain.constraint_library import detect_conditions, constraints_for

_KEY_FIELDS = ("age", "level", "activityLevel", "equipment", "goal", "healthNotes")


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _completeness(profile: dict) -> float:
    present = sum(1 for k in _KEY_FIELDS if str(profile.get(k) or "").strip())
    return present / len(_KEY_FIELDS)


def build(profile: dict, athlete_state: dict | None = None, history: list | None = None):
    """Return (ConstraintSet, CapacityEnvelope) for this human. Never raises on
    a sparse/missing profile — it degrades to an empty set + low confidence."""
    profile = profile or {}

    # ── Constraint Set ────────────────────────────────────────────────────────
    cset = ConstraintSet()
    health_text = str(profile.get("healthNotes") or profile.get("injuries") or "")
    detected = detect_conditions(health_text)
    for key in detected:
        for c in constraints_for(key):
            cset.add(c)

    # ── Capacity Envelope ─────────────────────────────────────────────────────
    level = str(profile.get("level") or "").lower()
    activity = str(profile.get("activityLevel") or "").lower()
    age = _int(profile.get("age"))

    base = 0.60                                        # unknown capacity → moderate
    if level.startswith(("beginner", "начина")):
        base = 0.55
    elif level.startswith(("advanced", "напред")):
        base = 0.90
    if activity in ("sedentary", "заседнала", "заседнал"):
        base = min(base, 0.50)
    elif activity in ("active", "very_active"):
        base = max(base, 0.85)

    intensity = complexity = volume = base

    # Age tempers the ceiling — a factor, never a veto.
    if age is not None:
        if age >= 75:
            intensity, complexity = min(intensity, 0.45), min(complexity, 0.50)
        elif age >= 65:
            intensity, complexity = min(intensity, 0.60), min(complexity, 0.65)

    # Condition load narrows the envelope.
    n_abs = len(cset.movements(ConstraintTier.ABSOLUTE))
    n_rel = len(cset.movements(ConstraintTier.RELATIVE))
    load = 0.12 * n_abs + 0.06 * n_rel
    intensity = max(0.10, intensity - load)
    complexity = max(0.10, complexity - 0.5 * load)
    volume = max(0.10, volume - 0.5 * load)

    supported = ("stroke_history" in detected or "falls_risk" in detected or
                 any(c.movement in ("unsupported_balance", "maximal_exertion")
                     and c.tier != ConstraintTier.MONITOR for c in cset.items))

    # Anti-infantilization: no constraints + trained/active → WIDE, regardless of
    # age label. Absence of constraints must not be over-ridden by a number.
    if cset.is_empty() and (level.startswith(("advanced", "напред")) or
                            activity in ("active", "very_active")):
        intensity = max(intensity, 0.90)
        complexity = max(complexity, 0.85)
        volume = max(volume, 0.85)
        supported = False

    envelope = CapacityEnvelope(
        intensity_ceiling=round(intensity, 2),
        complexity_ceiling=round(complexity, 2),
        volume_ceiling=round(volume, 2),
        supported=supported,
        confidence=round(_completeness(profile), 2),
    )
    return cset, envelope
