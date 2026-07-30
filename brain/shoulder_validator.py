"""
APEX Brain — Shoulder Load Plan Validator.

Post-plan deterministic validator. Before any workout is rendered, this
validator checks every exercise in the blueprint against all active
shoulder-region constraints in the ConstraintSet.

Rules:
- If SHOULDER_LOAD_FORBIDDEN (any of shoulder_pain, left_shoulder_pain,
  right_shoulder_pain) is active in the ConstraintSet, every exercise in the
  blueprint is validated against EXERCISE_SHOULDER_LOAD.
- Any exercise that maps to a violated movement → blueprint is REJECTED.
- Unknown exercises (not in index) → fail closed (REJECTED).
- On REJECTION: one retry with violating IDs added to hard exclusions.
- If second blueprint still fails → fail closed: no workout rendered.

The validator also produces a SafetyProof that the composer MUST receive
before making any shoulder-safety claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain.types import ConstraintSet, ConstraintTier
from brain.shoulder_exercise_index import (
    SHOULDER_LOAD_MOVEMENTS,
    exercise_violates_shoulder_constraint,
)

# The movement reason_keys that signal an active shoulder constraint
_SHOULDER_REASON_KEYS = frozenset({
    "shoulder_load_forbidden",
    "left_shoulder_load_forbidden",
    "right_shoulder_load_forbidden",
})


@dataclass(frozen=True)
class ShoulderSafetyProof:
    """Machine-checkable proof passed to the composer.

    The composer MUST NOT claim shoulder safety unless:
        shoulder_constraint_active=True AND shoulder_constraint_validated=True
        AND violating_exercise_count=0
    """
    shoulder_constraint_active: bool
    shoulder_constraint_validated: bool
    violating_exercise_count: int
    violating_exercise_ids: tuple = field(default_factory=tuple)

    @property
    def may_claim_safe(self) -> bool:
        return (
            self.shoulder_constraint_active
            and self.shoulder_constraint_validated
            and self.violating_exercise_count == 0
        )


@dataclass
class ValidationResult:
    passed: bool
    proof: ShoulderSafetyProof
    violating_ids: list[str] = field(default_factory=list)
    message: str = ""


def _active_shoulder_forbidden_movements(cset: ConstraintSet) -> frozenset:
    """Return the set of forbidden shoulder movements from the ConstraintSet."""
    forbidden = set()
    for c in cset.items:
        if (
            c.tier == ConstraintTier.ABSOLUTE
            and c.reason_key in _SHOULDER_REASON_KEYS
        ):
            forbidden.add(c.movement)
    return frozenset(forbidden)


def is_shoulder_constraint_active(cset: ConstraintSet) -> bool:
    """True iff at least one absolute shoulder constraint is present."""
    return bool(_active_shoulder_forbidden_movements(cset))


def validate_blueprint(
    exercises: list[dict[str, Any]],
    cset: ConstraintSet,
) -> ValidationResult:
    """Validate a list of exercise dicts against the active ConstraintSet.

    Each dict must have a 'canonical_id' key.
    Falls back to 'id' then 'name' if 'canonical_id' is absent (fail-closed
    on name: name-based IDs are not in the index → unknown_shoulder_load).

    Returns a ValidationResult with a ShoulderSafetyProof.
    """
    forbidden = _active_shoulder_forbidden_movements(cset)
    shoulder_active = bool(forbidden)

    if not shoulder_active:
        # No shoulder constraint — no validation needed.
        return ValidationResult(
            passed=True,
            proof=ShoulderSafetyProof(
                shoulder_constraint_active=False,
                shoulder_constraint_validated=False,
                violating_exercise_count=0,
            ),
        )

    violating_ids: list[str] = []
    for ex in exercises:
        canonical_id = (
            ex.get("canonical_id")
            or ex.get("id")
            or ex.get("name", "")
        )
        if exercise_violates_shoulder_constraint(str(canonical_id), forbidden):
            violating_ids.append(str(canonical_id))

    passed = len(violating_ids) == 0
    proof = ShoulderSafetyProof(
        shoulder_constraint_active=True,
        shoulder_constraint_validated=passed,
        violating_exercise_count=len(violating_ids),
        violating_exercise_ids=tuple(violating_ids),
    )
    return ValidationResult(
        passed=passed,
        proof=proof,
        violating_ids=violating_ids,
        message=(
            ""
            if passed
            else f"Blueprint rejected: {len(violating_ids)} exercise(s) violate "
                 f"shoulder constraint: {violating_ids}"
        ),
    )


def validate_blueprint_with_retry(
    exercises_attempt_1: list[dict[str, Any]],
    cset: ConstraintSet,
    generate_alternative_fn,  # callable(excluded_ids: list[str]) -> list[dict]
) -> ValidationResult:
    """Validate blueprint; if it fails, retry once with violating IDs excluded.

    generate_alternative_fn must accept a list of canonical_ids to exclude
    and return a new list of exercise dicts.

    If the second attempt also fails → fail closed (returns failed result).
    """
    result1 = validate_blueprint(exercises_attempt_1, cset)
    if result1.passed:
        return result1

    # Retry with violating IDs hard-excluded
    try:
        exercises_attempt_2 = generate_alternative_fn(result1.violating_ids)
        result2 = validate_blueprint(exercises_attempt_2, cset)
        return result2
    except Exception as e:
        # Generation failure → fail closed
        return ValidationResult(
            passed=False,
            proof=ShoulderSafetyProof(
                shoulder_constraint_active=True,
                shoulder_constraint_validated=False,
                violating_exercise_count=-1,
            ),
            message=f"Retry generation failed: {e}",
        )
