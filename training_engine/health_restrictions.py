"""Typed projection of explicitly supplied health restrictions.

This module deliberately reads only fields whose contract is an explicit
restriction. It never inspects a condition name, symptom, diagnosis, or medical
history to invent an exercise constraint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import MovementPattern


class UnsupportedHealthRestrictionError(ValueError):
    """An explicit restriction cannot be represented by the training taxonomy."""


@dataclass(frozen=True)
class HealthRestrictionProjection:
    """Removal-only projection into the existing typed movement taxonomy."""

    excluded_movement_patterns: frozenset[MovementPattern]
    source_count: int


_RESTRICTION_FIELDS = (
    "clinicianRestrictions",
    "medicalRestrictions",
    "healthRestrictions",
    "trainingRestrictions",
)

_CLINICIAN_DECLARATION_MARKERS = (
    "my doctor told me", "my doctor said", "my clinician told me", "my clinician said",
    "my healthcare professional told me", "doctor told me", "clinician told me",
    "лекарят ми каза", "лекар ми каза", "клиницистът ми каза", "медицинският ми специалист каза",
)

_DIRECT_RESTRICTION_MARKERS = (
    "avoid ", "do not ", "don't ", "dont ", "without ", "no ",
    "shouldn't ", "should not ", "не искам ", "без ", "избягвам ",
)

# Every phrase maps to an existing MovementPattern and only removes candidates.
# The matching is intentionally literal and closed; there is no medical or LLM
# interpretation of the surrounding text.
_FIXED_PATTERN_MAP = (
    (MovementPattern.VERTICAL_PUSH, (
        "overhead pressing", "overhead press", "press overhead", "press above head",
        "shoulder press", "military press", "преса над глава", "раменна преса",
        "военна преса", "над глава",
    )),
    (MovementPattern.HORIZONTAL_PUSH, (
        "push-up", "push up", "pushups", "лицеви опори", "лицеви",
    )),
    (MovementPattern.VERTICAL_PULL, (
        "pull-up", "pull up", "pullups", "chin-up", "chin up", "набирания", "набиране",
    )),
    (MovementPattern.SQUAT, (
        "squat", "squats", "клек", "клекове",
    )),
    (MovementPattern.LUNGE, (
        "lunge", "lunges", "напад", "напади",
    )),
    (MovementPattern.HINGE, (
        "deadlift", "deadlifts", "hip hinge", "romanian deadlift", "мъртва тяга",
    )),
)


def _values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace(";", ",").split(",") if part.strip())
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def explicit_restrictions_from_message(message: object) -> tuple[str, ...]:
    """Return an explicitly stated, closed-vocabulary training restriction.

    A clinician declaration is retained even when its restriction is not yet
    representable, so the caller can fail closed. Direct user restrictions are
    accepted only when both restriction wording and a known movement phrase are
    present; symptoms and conditions remain outside this projection.
    """
    text = str(message or "").strip()
    if not text:
        return ()
    normalized = text.casefold()
    if any(marker in normalized for marker in _CLINICIAN_DECLARATION_MARKERS):
        return (text,)
    has_known_movement = any(
        phrase in normalized
        for _pattern, phrases in _FIXED_PATTERN_MAP
        for phrase in phrases
    )
    if has_known_movement and any(marker in normalized for marker in _DIRECT_RESTRICTION_MARKERS):
        return (text,)
    return ()


def project_explicit_health_restrictions(profile: Mapping[str, object]) -> HealthRestrictionProjection:
    """Project only explicit user/clinician boundaries, or reject the plan safely."""
    restrictions = tuple(
        restriction
        for field in _RESTRICTION_FIELDS
        for restriction in _values(profile.get(field))
    )
    excluded: set[MovementPattern] = set()
    for restriction in restrictions:
        text = restriction.casefold()
        matches = {
            pattern
            for pattern, phrases in _FIXED_PATTERN_MAP
            if any(phrase in text for phrase in phrases)
        }
        if not matches:
            raise UnsupportedHealthRestrictionError("explicit health restriction is unsupported")
        excluded.update(matches)
    return HealthRestrictionProjection(frozenset(excluded), len(restrictions))
