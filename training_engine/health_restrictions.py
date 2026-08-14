"""Typed projection of explicitly supplied health restrictions.

This module deliberately reads only fields whose contract is an explicit
restriction. It never inspects a condition name, symptom, diagnosis, or medical
history to invent an exercise constraint.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from .models import MovementPattern


class UnsupportedHealthRestrictionError(ValueError):
    """An explicit restriction cannot be represented by the training taxonomy."""


class FitnessLimitationState(str, Enum):
    """Lifecycle for a temporary, self-reported fitness limitation."""

    ACTIVE = "active"
    RECOVERING = "recovering"
    CLEARED = "cleared"


@dataclass(frozen=True)
class FitnessLimitation:
    """A non-medical movement boundary supplied and updated by the user."""

    state: FitnessLimitationState
    body_area: str = "shoulder"
    excluded_movement_patterns: frozenset[MovementPattern] = frozenset(
        {MovementPattern.VERTICAL_PUSH})
    version: str = "fitness-limitation-v1"

    def to_record(self) -> dict[str, object]:
        return {
            "version": self.version,
            "state": self.state.value,
            "body_area": self.body_area,
            "excluded_movement_patterns": sorted(
                pattern.value for pattern in self.excluded_movement_patterns),
        }


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

_CLINICIAN_IDENTITY_MARKERS = (
    "doctor", "clinician", "healthcare professional",
    "\u043b\u0435\u043a\u0430\u0440", "\u043a\u043b\u0438\u043d\u0438\u0446\u0438\u0441\u0442",
    "\u043c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0438 \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0441\u0442",
)

_CLINICIAN_CLEARANCE_MARKERS = (
    "cleared me", "cleared me to", "said i can", "told me i can",
    "approved me to", "allowed me to",
    "\u0440\u0430\u0437\u0440\u0435\u0448\u0438 \u043c\u0438", "\u043a\u0430\u0437\u0430, \u0447\u0435 \u043c\u043e\u0433\u0430",
    "\u043a\u0430\u0437\u0430 \u0447\u0435 \u043c\u043e\u0433\u0430", "\u043f\u043e\u0442\u0432\u044a\u0440\u0434\u0438, \u0447\u0435 \u043c\u043e\u0433\u0430",
    "\u043f\u043e\u0442\u0432\u044a\u0440\u0434\u0438 \u0447\u0435 \u043c\u043e\u0433\u0430",
)

_DIRECT_RESTRICTION_MARKERS = (
    "avoid ", "do not ", "don't ", "dont ", "without ", "no ",
    "shouldn't ", "should not ", "не искам ", "без ", "избягвам ",
)

_USER_CONSTRAINT_CLEARANCE_MARKERS = (
    "remove my", "remove the", "remove this", "no longer want to avoid",
    "okay again", "ok again", "can do it again",
    "премахни", "махни", "вече е окей", "вече е добре",
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

_FITNESS_LIMITATION_PROFILE_KEY = "_fitness_limitation_state"
_SHOULDER_TERMS = (
    "shoulder", "overhead press", "pressing overhead",
    "\u0440\u0430\u043c\u043e", "\u0440\u0430\u043c\u043e\u0442\u043e", "\u043f\u0440\u0435\u0441\u0430 \u043d\u0430\u0434 \u0433\u043b\u0430\u0432\u0430",
)
_PAIN_TERMS = (
    "hurts", "hurt again", "pain", "painful",
    "\u0431\u043e\u043b\u0438", "\u0431\u043e\u043b\u043a\u0430", "\u0431\u043e\u043b\u043a\u0438", "\u0437\u0430\u0431\u043e\u043b\u044f",
)
_RECOVERING_PHRASES = (
    "shoulder is better", "shoulder feels better", "shoulder feels much better",
    "\u0440\u0430\u043c\u043e\u0442\u043e \u043c\u0438 \u0435 \u043f\u043e-\u0434\u043e\u0431\u0440\u0435",
    "\u0440\u0430\u043c\u043e\u0442\u043e \u0435 \u043f\u043e-\u0434\u043e\u0431\u0440\u0435",
    "\u0432\u0435\u0447\u0435 \u043f\u043e\u0447\u0442\u0438 \u043d\u0435 \u043c\u0435 \u0431\u043e\u043b\u0438",
)
_CLEARED_PHRASES = (
    "shoulder doesn't hurt anymore", "shoulder does not hurt anymore",
    "no longer have shoulder pain", "shoulder pain is gone",
    "\u0440\u0430\u043c\u043e\u0442\u043e \u0432\u0435\u0447\u0435 \u043d\u0435 \u043c\u0435 \u0431\u043e\u043b\u0438",
    "\u0432\u0435\u0447\u0435 \u043d\u044f\u043c\u0430\u043c \u0431\u043e\u043b\u043a\u0430 \u0432 \u0440\u0430\u043c\u043e\u0442\u043e",
    "\u0431\u043e\u043b\u043a\u0430\u0442\u0430 \u0432 \u0440\u0430\u043c\u043e\u0442\u043e \u0438\u0437\u0447\u0435\u0437\u043d\u0430",
)


def _values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace(";", ",").split(",") if part.strip())
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def fitness_limitation_from_record(value: object) -> FitnessLimitation | None:
    if not isinstance(value, Mapping) or value.get("version") != "fitness-limitation-v1":
        return None
    try:
        state = FitnessLimitationState(str(value.get("state")))
        patterns = frozenset(
            MovementPattern(str(item))
            for item in value.get("excluded_movement_patterns", ()))
    except (TypeError, ValueError):
        return None
    expected = frozenset({MovementPattern.VERTICAL_PUSH})
    if value.get("body_area") != "shoulder" or patterns != expected:
        return None
    return FitnessLimitation(state=state)


def fitness_limitation_from_profile(profile: Mapping[str, object]) -> FitnessLimitation | None:
    return fitness_limitation_from_record(profile.get(_FITNESS_LIMITATION_PROFILE_KEY))


def fitness_limitation_from_history(
        conversation: Sequence[object], initial: FitnessLimitation | None = None) -> FitnessLimitation | None:
    """Replay user-authored lifecycle evidence without relying on assistant prose."""
    state = initial
    for turn in conversation:
        if isinstance(turn, Mapping) and turn.get("role") == "user":
            state = transition_fitness_limitation(state, turn.get("content"))
    return state


def is_clinician_statement(message: object) -> bool:
    text = str(message or "").casefold()
    return any(marker in text for marker in _CLINICIAN_IDENTITY_MARKERS)


def transition_fitness_limitation(
        current: FitnessLimitation | None, message: object) -> FitnessLimitation | None:
    """Apply only explicit shoulder limitation, improvement, or clearance evidence."""
    text = str(message or "").casefold().strip()
    if not text or is_clinician_statement(text):
        return current
    if any(phrase in text for phrase in _CLEARED_PHRASES):
        return FitnessLimitation(FitnessLimitationState.CLEARED) if current is not None else None
    if any(phrase in text for phrase in _RECOVERING_PHRASES):
        if current is not None and current.state is not FitnessLimitationState.CLEARED:
            return FitnessLimitation(FitnessLimitationState.RECOVERING)
        return current
    if (any(term in text for term in _SHOULDER_TERMS)
            and any(term in text for term in _PAIN_TERMS)):
        return FitnessLimitation(FitnessLimitationState.ACTIVE)
    return current


def clinician_clearance_patterns(message: object) -> frozenset[MovementPattern]:
    """Return only movement families covered by an explicit clinician clearance."""
    text = str(message or "").casefold()
    if (not any(marker in text for marker in _CLINICIAN_IDENTITY_MARKERS)
            or not any(marker in text for marker in _CLINICIAN_CLEARANCE_MARKERS)):
        return frozenset()
    return frozenset(
        pattern for pattern, phrases in _FIXED_PATTERN_MAP
        if any(phrase in text for phrase in phrases))


def explicit_user_constraint_clearance_patterns(message: object) -> frozenset[MovementPattern]:
    """Recognize only unambiguous user-owned movement-exclusion retirement intent."""
    text = str(message or "").casefold().strip()
    if (not text or is_clinician_statement(text)
            or not any(marker in text for marker in _USER_CONSTRAINT_CLEARANCE_MARKERS)):
        return frozenset()
    return frozenset(
        pattern for pattern, phrases in _FIXED_PATTERN_MAP
        if any(phrase in text for phrase in phrases))


def remove_cleared_clinician_restrictions(
        restrictions: object, cleared_patterns: frozenset[MovementPattern], *, clinician_field: bool = False
) -> tuple[str, ...]:
    """Remove only clinician-origin restrictions covered by explicit clearance."""
    kept = []
    for restriction in _values(restrictions):
        text = restriction.casefold()
        patterns = {
            pattern for pattern, phrases in _FIXED_PATTERN_MAP
            if any(phrase in text for phrase in phrases)
        }
        clinician_origin = clinician_field or is_clinician_statement(text)
        if clinician_origin and patterns and patterns <= cleared_patterns:
            continue
        kept.append(restriction)
    return tuple(kept)


def migrate_temporary_fitness_restrictions(
        restrictions: object) -> tuple[tuple[str, ...], FitnessLimitation | None]:
    """Separate legacy self-reported pain constraints from hard restrictions."""
    kept = []
    migrated = None
    for restriction in _values(restrictions):
        candidate = transition_fitness_limitation(None, restriction)
        if candidate is not None and candidate.state is FitnessLimitationState.ACTIVE:
            migrated = candidate
        else:
            kept.append(restriction)
    return tuple(kept), migrated


def limitation_excluded_patterns(limitation: FitnessLimitation | None) -> frozenset[MovementPattern]:
    if limitation is None or limitation.state is FitnessLimitationState.CLEARED:
        return frozenset()
    return limitation.excluded_movement_patterns


def is_recovering_light_session_request(message: object, limitation: FitnessLimitation | None) -> bool:
    if limitation is None or limitation.state is not FitnessLimitationState.RECOVERING:
        return False
    text = str(message or "").casefold()
    return any(term in text for term in (
        "light warm-up", "light warmup", "gentle warm-up", "gentle warmup",
        "\u043b\u0435\u043a\u0430 \u0437\u0430\u0433\u0440\u044f\u0432\u043a\u0430", "\u043b\u0435\u043a\u043e \u0440\u0430\u0437\u0434\u0432\u0438\u0436\u0432\u0430\u043d\u0435",
    ))


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
    if clinician_clearance_patterns(text):
        return ()
    if explicit_user_constraint_clearance_patterns(text):
        return ()
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
