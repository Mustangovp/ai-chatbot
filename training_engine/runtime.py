"""Pure runtime adapter for the deterministic Training Engine.

It translates already-verified profile facts into typed engine inputs. Unknown,
ambiguous, or injury-constrained facts fail closed; this module never falls back
to prompt-generated planning.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from .construction import (
    PrescriptionRule,
    RecoveryAssumption,
    TrainingPlanBlueprintV2,
    TrainingPlanConstructionEngine,
    TrainingStructurePolicy,
)
from .models import Difficulty, Equipment, MovementPattern
from .registry import ExerciseLibrary, load_exercise_library
from .selection import (
    TrainingGoal,
    TrainingSafetyConstraints,
    TrainingSelectionEngine,
    TrainingSelectionRequest,
    TrainingSplit,
    resolve_training_split,
    training_goal_policy,
)


class TrainingRuntimeError(ValueError):
    pass


_GOALS = {
    "muscle_gain": TrainingGoal.MUSCLE_GAIN,
    "muscle gain": TrainingGoal.MUSCLE_GAIN,
    "strength": TrainingGoal.MUSCLE_GAIN,
    "hypertrophy": TrainingGoal.MUSCLE_GAIN,
    "fat_loss": TrainingGoal.FAT_LOSS,
    "fat loss": TrainingGoal.FAT_LOSS,
    "weight_loss": TrainingGoal.FAT_LOSS,
    "maintenance": TrainingGoal.MAINTENANCE,
    "general_fitness": TrainingGoal.MAINTENANCE,
}
_LEVELS = {
    "beginner": Difficulty.BEGINNER,
    "intermediate": Difficulty.INTERMEDIATE,
    "moderate": Difficulty.INTERMEDIATE,
    "advanced": Difficulty.ADVANCED,
}
_EQUIPMENT = {
    "bodyweight": Equipment.BODYWEIGHT,
    "body weight": Equipment.BODYWEIGHT,
    "dumbbell": Equipment.DUMBBELL,
    "dumbbells": Equipment.DUMBBELL,
    "resistance_band": Equipment.RESISTANCE_BAND,
    "resistance band": Equipment.RESISTANCE_BAND,
    "band": Equipment.RESISTANCE_BAND,
    "bands": Equipment.RESISTANCE_BAND,
    "bench": Equipment.BENCH,
    "barbell": Equipment.BARBELL,
    "cable": Equipment.CABLE,
    "pullup_bar": Equipment.PULLUP_BAR,
    "pull-up bar": Equipment.PULLUP_BAR,
}


def build_training_plan(*, recommendation_blueprint_id: str, facts: Mapping[str, Any],
                        locked_preferences: Mapping[str, tuple[str, ...]] | None = None,
                        requested_split: object | None = None,
                        library: ExerciseLibrary | None = None) -> TrainingPlanBlueprintV2:
    """Build one deterministic weekly plan or fail without producing a partial plan."""
    profile = dict(facts)
    locked = dict(locked_preferences or {})
    _reject_unreviewed_safety_constraints(profile, locked)
    goal = _goal(profile.get("goal"))
    level = _level(profile.get("level") or profile.get("experience_level"))
    split = _split(requested_split if requested_split is not None
                   else profile.get("training_split") or profile.get("split"))
    equipment = _equipment(locked.get("equipment") or profile.get("equipment"))
    selected_library = library or load_exercise_library()
    safety = _safety(locked, selected_library)
    selection = TrainingSelectionEngine.select(
        selected_library,
        TrainingSelectionRequest(
            recommendation_blueprint_id=recommendation_blueprint_id,
            goal=goal,
            experience_level=level,
            available_equipment=equipment,
            muscle_priorities=_priorities(profile),
            requested_split=split,
            safety=safety,
            policy=training_goal_policy(goal, split),
        ),
    )
    if selection.blueprint is None:
        raise TrainingRuntimeError("training selection rejected: " + ",".join(selection.rejection_reasons))
    return TrainingPlanConstructionEngine.construct(
        selection.blueprint, selected_library, _structure_policy(goal, level, split, _recovery(profile)),
    )


def _goal(value: object) -> TrainingGoal:
    key = str(value or "").strip().lower()
    try:
        return _GOALS[key]
    except KeyError as error:
        raise TrainingRuntimeError("verified profile needs a supported training goal") from error


def _level(value: object) -> Difficulty:
    key = str(value or "").strip().lower()
    try:
        return _LEVELS[key]
    except KeyError as error:
        raise TrainingRuntimeError("verified profile needs a supported experience level") from error


def _split(value: object) -> TrainingSplit:
    try:
        return resolve_training_split(value)
    except ValueError as error:
        raise TrainingRuntimeError("verified profile contains an unsupported training split") from error


def _tokens(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().lower() for item in value.replace(";", ",").split(",") if item.strip())
    if isinstance(value, (tuple, list, frozenset, set)):
        return tuple(str(item).strip().lower() for item in value if str(item).strip())
    return ()


def _equipment(value: object) -> frozenset[Equipment]:
    tokens = _tokens(value)
    if not tokens:
        raise TrainingRuntimeError("verified profile needs specific equipment")
    resolved = []
    for token in tokens:
        if token == "gym":
            resolved.extend((Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.BARBELL,
                             Equipment.CABLE, Equipment.BENCH, Equipment.PULLUP_BAR))
            continue
        # These are the stable values submitted by the existing browser profile
        # wizard.  They are capability groups, not unsupported equipment names.
        if token == "home":
            resolved.extend((Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.PULLUP_BAR))
            continue
        if token == "none":
            resolved.append(Equipment.BODYWEIGHT)
            continue
        try:
            resolved.append(_EQUIPMENT[token])
        except KeyError as error:
            raise TrainingRuntimeError("verified profile contains unsupported equipment") from error
    return frozenset(resolved)


def _priorities(profile: Mapping[str, Any]) -> tuple[str, ...]:
    values = _tokens(profile.get("muscle_priorities") or profile.get("musclePriorities"))
    return tuple(dict.fromkeys(values))


def _recovery(profile: Mapping[str, Any]) -> RecoveryAssumption:
    value = str(profile.get("recoveryFeel") or profile.get("sleepQuality") or "").strip().lower()
    if value in {"fresh", "good", "high"}:
        return RecoveryAssumption.FRESH
    if value in {"poor", "low", "limited"}:
        return RecoveryAssumption.LIMITED
    return RecoveryAssumption.MODERATE


def _reject_unreviewed_safety_constraints(profile: Mapping[str, Any], locked: Mapping[str, Any]) -> None:
    values = _tokens(profile.get("injuries")) + _tokens(profile.get("healthNotes"))
    values += _tokens(locked.get("permanent_injuries")) + _tokens(locked.get("accessibility"))
    if values:
        raise TrainingRuntimeError("verified safety constraints require a controlled review")


def _safety(locked: Mapping[str, Any], library: ExerciseLibrary) -> TrainingSafetyConstraints:
    exercise_ids = set()
    patterns = set()
    for value in _tokens(locked.get("exercise_exclusions")):
        if library.get(value) is not None:
            exercise_ids.add(value)
            continue
        try:
            patterns.add(MovementPattern(value))
        except ValueError as error:
            raise TrainingRuntimeError("locked exercise exclusion is unsupported") from error
    return TrainingSafetyConstraints(frozenset(exercise_ids), frozenset(patterns))


def _structure_policy(goal: TrainingGoal, level: Difficulty, split: TrainingSplit,
                      recovery: RecoveryAssumption) -> TrainingStructurePolicy:
    base_sets = 3 if goal is TrainingGoal.MUSCLE_GAIN else 2
    if recovery is RecoveryAssumption.LIMITED:
        base_sets = max(1, base_sets - 1)
    rep_min, rep_max = ((8, 12) if goal is TrainingGoal.MUSCLE_GAIN else (10, 15)
                        if goal is TrainingGoal.FAT_LOSS else (8, 12))
    rpe = Decimal("7") if recovery is RecoveryAssumption.FRESH else Decimal("6")
    rir = 10 - int(rpe)
    rest = 90 if goal is TrainingGoal.MUSCLE_GAIN else 60
    rules = tuple(
        PrescriptionRule(pattern, base_sets if pattern is not MovementPattern.CORE_ANTI_EXTENSION else max(1, base_sets - 1),
                         rep_min, rep_max, rpe, rir, rest if pattern is not MovementPattern.CORE_ANTI_EXTENSION else 45,
                         "3-1-1-0" if pattern is not MovementPattern.CORE_ANTI_EXTENSION else "2-1-2-0",
                         4 if pattern is not MovementPattern.CORE_ANTI_EXTENSION else 3,
                         Decimal("2") if pattern is not MovementPattern.CORE_ANTI_EXTENSION else Decimal("1"))
        for pattern in training_goal_policy(goal, split).required_patterns
    )
    requested_sessions = {TrainingSplit.FULL_BODY: 2, TrainingSplit.UPPER_LOWER: 2,
                          TrainingSplit.PUSH_PULL_LEGS: 3}[split]
    sessions = 1 if recovery is RecoveryAssumption.LIMITED else requested_sessions
    return TrainingStructurePolicy(
        version=f"training-structure-policy-v1:{goal.value}:{level.value}:{split.value}:{recovery.value}",
        goal=goal, experience_level=level, training_split=split, recovery=recovery, sessions_per_week=sessions,
        session_patterns=training_goal_policy(goal, split).session_patterns,
        movement_order=(MovementPattern.SQUAT, MovementPattern.LUNGE,
                        MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL,
                        MovementPattern.VERTICAL_PUSH, MovementPattern.HINGE,
                        MovementPattern.CORE_ANTI_EXTENSION),
        prescription_rules=rules, max_session_duration_minutes=60,
        max_session_fatigue_units=Decimal("30"), max_weekly_sets_per_primary_muscle=12,
        max_push_pull_set_difference=0, max_lower_body_set_difference=0, transition_seconds=30,
    )
