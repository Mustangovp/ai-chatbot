"""Versioned dose semantics, independent of immutable exercise-library releases."""
from enum import Enum


class PrescriptionType(str, Enum):
    REPETITIONS = "repetitions"
    DURATION = "duration"


DURATION_POLICY_VERSION = "isometric-duration-policy-v1"


def duration_range(exercise_id: str) -> tuple[int, int] | None:
    # Per-set controlled holds; movement pattern alone never changes dose units.
    # These bounds apply only when constructing a new typed prescription.
    if exercise_id in {"bodyweight.plank", "bodyweight.hollow_hold"}:
        return (20, 40)
    return None
