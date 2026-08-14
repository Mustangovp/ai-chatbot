"""Bounded adaptation from persisted immutable workout-completion evidence."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from .completion import validate_workout_completion_payload
from .construction import TrainingPlanBlueprintV2
from .lifecycle import PlanRevisionReason
from .lifecycle_runtime import advance_training_lifecycle
from .progression import (
    DEFAULT_PROGRESSION_POLICY,
    ExercisePerformance,
    RecoverySnapshot,
    RecoveryState,
    WorkoutResult,
)


@dataclass(frozen=True)
class CrossSessionAdaptation:
    """A delivery-time projection; historical rows and the parent plan stay immutable."""

    plan: TrainingPlanBlueprintV2
    change: str | None = None
    comparable_session: bool = False

    @property
    def applied(self) -> bool:
        return self.change is not None


_MAX_AGE = timedelta(days=42)
_MINIMUM_COMPARABLE_EXERCISES = 2
_MINIMUM_COMPARABLE_RATIO = Decimal("0.40")
_NEUTRAL_RECOVERY = RecoverySnapshot(
    RecoveryState.NORMALLY_RECOVERED, Decimal("30"), "cross-session-adaptation-v1")
_CROSS_SESSION_PROGRESSION_POLICY = replace(
    DEFAULT_PROGRESSION_POLICY,
    version="progression-policy-v2-cross-session-single-effort",
    allow_single_effort_signal=True,
)
_CHANGE_BY_REASON = {
    PlanRevisionReason.LOAD: "load",
    PlanRevisionReason.REPETITIONS: "repetitions",
    PlanRevisionReason.SETS: "sets",
    PlanRevisionReason.EXERCISE_REPLACEMENT: "eligible_alternative",
    PlanRevisionReason.DELOAD: "conservative",
    PlanRevisionReason.ROTATION: "eligible_alternative",
}
_MIXED_CHANGE = "mixed"


def adapt_from_persisted_history(
        plan: TrainingPlanBlueprintV2, records: Sequence[Mapping[str, object]] | object,
        *, now: datetime | None = None) -> CrossSessionAdaptation:
    """Apply one compatible, recent completion through the native lifecycle policy.

    Completion rows are accepted only when their immutable exercise identities
    overlap substantially with the newly selected plan and contain explicit,
    directionally consistent RPE and/or RIR feedback. Everything else is
    intentionally ignored.
    """
    if (not isinstance(plan, TrainingPlanBlueprintV2)
            or not isinstance(records, Sequence)
            or isinstance(records, (str, bytes, bytearray))):
        return CrossSessionAdaptation(plan)
    current_time = now or datetime.now(timezone.utc)
    candidates = []
    for record in records:
        candidate = _candidate(plan, record, current_time)
        if candidate is not None:
            candidates.append(candidate)
    duplicate_ids = {
        workout.workout_id for workout, _ in candidates
        if sum(other.workout_id == workout.workout_id for other, _ in candidates) > 1
    }
    for workout, comparable in sorted(candidates, key=lambda item: (
            item[0].completed_at, item[0].workout_id), reverse=True):
        if workout.workout_id in duplicate_ids:
            continue
        try:
            result = advance_training_lifecycle(
                plan=plan,
                workouts=(workout,),
                recovery=_NEUTRAL_RECOVERY,
                policy=_CROSS_SESSION_PROGRESSION_POLICY,
            )
        except (TypeError, ValueError):
            continue
        changed = tuple(reason for reason in result.revision.reasons if reason in _CHANGE_BY_REASON)
        if not changed:
            return CrossSessionAdaptation(plan, comparable_session=comparable)
        return CrossSessionAdaptation(
            result.revision.revised_plan,
            change=(_CHANGE_BY_REASON[changed[0]] if len(set(changed)) == 1 else _MIXED_CHANGE),
            comparable_session=comparable,
        )
    return CrossSessionAdaptation(plan)


def _candidate(plan: TrainingPlanBlueprintV2, record: object,
               now: datetime) -> tuple[WorkoutResult, bool] | None:
    if not isinstance(record, Mapping) or record.get("completion") != 100:
        return None
    occurred_at = _timestamp(record.get("occurred_at"))
    if occurred_at is None or occurred_at > now or now - occurred_at > _MAX_AGE:
        return None
    session = record.get("exercises")
    completion = session.get("workout_completion") if isinstance(session, Mapping) else None
    try:
        validate_workout_completion_payload(completion)
    except ValueError:
        return None
    assert isinstance(completion, Mapping)
    expected = {
        (item.exercise_id, item.exercise_version): item
        for workout_session in plan.sessions for item in workout_session.prescriptions
    }
    raw_exercises = completion.get("exercises")
    if not isinstance(raw_exercises, list):
        return None
    matched: list[ExercisePerformance] = []
    seen = set()
    for item in raw_exercises:
        if not isinstance(item, Mapping):
            return None
        identity = (item.get("exercise_id"), item.get("exercise_version"))
        prescription = expected.get(identity)
        if prescription is None or identity in seen:
            continue
        seen.add(identity)
        performance = _performance(item)
        if performance is None or performance.completed_sets < prescription.sets:
            return None
        matched.append(performance)
    if (len(matched) < _MINIMUM_COMPARABLE_EXERCISES
            or Decimal(len(matched)) / Decimal(len(expected)) < _MINIMUM_COMPARABLE_RATIO):
        return None
    return WorkoutResult(
        workout_id=str(completion["workout_id"]), plan_id=plan.plan_id, plan_version=plan.version,
        completed_at=occurred_at, completed=True, performances=tuple(matched),
    ), True


def _performance(item: Mapping[str, object]) -> ExercisePerformance | None:
    try:
        rpe, rir = item.get("completed_rpe"), item.get("completed_rir")
        parsed_rpe = Decimal(str(rpe)) if rpe is not None else None
        parsed_rir = int(rir) if rir is not None else None
        if parsed_rpe is None and parsed_rir is None:
            return None
        if parsed_rpe is not None and not Decimal("1") <= parsed_rpe <= Decimal("10"):
            return None
        if parsed_rir is not None and not 0 <= parsed_rir <= 10:
            return None
        if (parsed_rpe is not None and parsed_rir is not None
                and ((parsed_rpe <= _CROSS_SESSION_PROGRESSION_POLICY.maximum_progress_rpe)
                     != (parsed_rir >= _CROSS_SESSION_PROGRESSION_POLICY.minimum_progress_rir))):
            return None
        return ExercisePerformance(
            exercise_id=str(item["exercise_id"]), exercise_version=str(item["exercise_version"]),
            completed_sets=int(item["completed_sets"]),
            completed_repetitions=int(item["completed_repetitions"]),
            achieved_rpe=parsed_rpe, achieved_rir=parsed_rir,
            load_kg=(Decimal(str(item["completed_load"]))
                     if item.get("completed_load") is not None else None),
            completed=int(item["completed_sets"]) > 0,
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
