"""
APEX Brain — Station S4: the Appropriateness Gate.

The right of refusal. Emits exactly one Verdict ∈ {GO, MODIFY, NOT_YET,
NO_TRAIN} from the frozen, verified S4 decision table. Pure function; total and
deterministic (first-match priority chain). No Flask, no DB, no OpenAI.

Contract C2 (Addendum 02 A2-0): the S2 halt is the enforcement point for
EMERGENCY/URGENT red flags and routes upstream — S4 must be unreachable under a
halt. This organ nonetheless treats `halt` as DEFENSE-IN-DEPTH: if it is ever
reached while halted, it can only defer, never permit training.

Decision table (halt=False space): verdict = f(S1 state, S3 dominant), with an
uncertainty clamp. See the frozen S4 Truth Table for the reachability proofs.
"""
from brain.types import Verdict, ConstraintTier

# Movements that forbid ALL training (no safe modification) → S1 BLOCK. The seed
# constraint library encodes none (all absolute constraints are movement-level,
# leaving a gentle/supported envelope), so BLOCK is currently unreached — the
# branch exists for a future clinically-reviewed "no-safe-exertion" entry.
_NO_TRAINING_MOVEMENTS = frozenset()

_CONF_FLOOR = 0.15                              # below this, too little is known → ask/defer (§3)
_RECOVERY_NEEDS = ("recovery", "sleep", "stress_reduction")
_DEFER_DOMINANTS = ("RECOVERY", "MEDICAL")      # S3-dominant CATEGORIES that defer training


def _s1_state(constraints, envelope) -> str:
    """CLEAR (no constraints) | MODIFY (constraints, gentle envelope exists) | BLOCK."""
    if any(c.tier == ConstraintTier.ABSOLUTE and c.movement in _NO_TRAINING_MOVEMENTS
           for c in constraints.items):
        return "BLOCK"
    return "MODIFY" if constraints.items else "CLEAR"


def _s3_dominant(need_vector) -> str:
    if not need_vector:
        return "SOFT"
    top = need_vector[0][0]
    if top == "training":
        return "TRAINING"
    if top == "medical_followup":
        return "MEDICAL"
    if top in _RECOVERY_NEEDS:
        return "RECOVERY"
    return "SOFT"


def decide(*, constraints, envelope, s2, need_vector):
    """Return (Verdict, confidence). Total, deterministic, first-match priority."""
    conf = round((float(envelope.confidence) + float(getattr(s2, "readiness_conf", 0.0))) / 2.0, 3)

    # 1) Defense-in-depth: a halt should have routed at S2 (A2-0). Never permit training.
    if getattr(s2, "halt", False):
        return Verdict.NOT_YET, conf
    # 2) Uncertainty: too little known to prescribe safely → ask/defer (§3).
    if float(envelope.confidence) < _CONF_FLOOR:
        return Verdict.NOT_YET, conf
    # 3) Absolute contraindication with no safe modification → categorical refusal.
    if _s1_state(constraints, envelope) == "BLOCK":
        return Verdict.NO_TRAIN, conf
    # 4) A non-training safety/state need on top (state below floor) → defer (reversible).
    if _s3_dominant(need_vector) in _DEFER_DOMINANTS:
        return Verdict.NOT_YET, conf
    # 5) Clear (no constraints) vs constrained.
    return (Verdict.GO if not constraints.items else Verdict.MODIFY), conf
