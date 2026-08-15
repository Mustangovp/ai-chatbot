"""Bounded, deterministic programming context from immutable workout history.

This module deliberately accepts only the validated browser completion contract.
It does not parse chat text, infer recovery, or retain a second history store.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .completion import validate_workout_completion_payload
from .models import MovementPattern
from .registry import ExerciseLibrary
from .selection import TrainingSplit, training_goal_policy


@dataclass(frozen=True)
class LongitudinalTrainingContext:
    """Safe selection signals derived from recent completed sessions only."""

    recent_exercise_ids: frozenset[str] = frozenset()
    recent_patterns: frozenset[MovementPattern] = frozenset()
    recent_primary_muscles: frozenset[str] = frozenset()
    next_session_index: int = 0
    source_completion_count: int = 0

    @property
    def has_recent_exposure(self) -> bool:
        return bool(self.recent_exercise_ids)


def context_from_persisted_history(
        records: Sequence[Mapping[str, object]] | object, *, library: ExerciseLibrary,
        split: TrainingSplit, limit: int = 4) -> LongitudinalTrainingContext:
    """Return only factual recent exposure from canonical completed workouts.

    Invalid, duplicate, incomplete, or legacy free-form rows are ignored. The
    newest usable completion determines the next split session; its exact
    exercise identities are a deterministic *deprioritisation*, never a ban.
    """
    if (not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray))
            or not isinstance(library, ExerciseLibrary) or not isinstance(split, TrainingSplit)
            or not isinstance(limit, int) or limit < 1):
        return LongitudinalTrainingContext()
    completed: list[tuple[datetime, str, tuple[str, ...]]] = []
    seen_ids: set[str] = set()
    for row in records:
        parsed = _completed_exercise_ids(row, library)
        if parsed is None:
            continue
        occurred_at, workout_id, exercise_ids = parsed
        if workout_id in seen_ids:
            continue
        seen_ids.add(workout_id)
        completed.append((occurred_at, workout_id, exercise_ids))
    completed.sort(key=lambda item: (item[0], item[1]), reverse=True)
    completed = completed[:limit]
    if not completed:
        return LongitudinalTrainingContext()

    latest_ids = completed[0][2]
    pattern_sets: list[frozenset[MovementPattern]] = []
    all_patterns: set[MovementPattern] = set()
    muscles: set[str] = set()
    for _, _, exercise_ids in completed:
        patterns: set[MovementPattern] = set()
        for exercise_id in exercise_ids:
            exercise = library.get(exercise_id)
            if exercise is None:
                continue
            patterns.add(exercise.movement_pattern)
            all_patterns.add(exercise.movement_pattern)
            muscles.update(exercise.primary_muscles)
        pattern_sets.append(frozenset(patterns))
    next_session_index = _next_session_index(pattern_sets[0], split)
    return LongitudinalTrainingContext(
        recent_exercise_ids=frozenset(latest_ids),
        recent_patterns=frozenset(all_patterns),
        recent_primary_muscles=frozenset(muscles),
        next_session_index=next_session_index,
        source_completion_count=len(completed),
    )


def _completed_exercise_ids(row: object, library: ExerciseLibrary) -> tuple[datetime, str, tuple[str, ...]] | None:
    if not isinstance(row, Mapping) or row.get("completion") != 100:
        return None
    occurred_at = _timestamp(row.get("occurred_at"))
    session = row.get("exercises")
    completion = session.get("workout_completion") if isinstance(session, Mapping) else None
    try:
        validate_workout_completion_payload(completion)
    except ValueError:
        return None
    if not isinstance(completion, Mapping) or occurred_at is None:
        return None
    workout_id = str(completion.get("workout_id") or "").strip()
    exercises = completion.get("exercises")
    if not workout_id or not isinstance(exercises, list):
        return None
    ids: list[str] = []
    for item in exercises:
        if not isinstance(item, Mapping):
            return None
        exercise_id = item.get("exercise_id")
        if not isinstance(exercise_id, str) or library.get(exercise_id) is None:
            return None
        ids.append(exercise_id)
    if not ids or len(ids) != len(set(ids)):
        return None
    return occurred_at, workout_id, tuple(ids)


def _next_session_index(last_patterns: frozenset[MovementPattern], split: TrainingSplit) -> int:
    # Session taxonomy is goal-invariant; use a closed existing goal solely to
    # obtain the split's canonical pattern groups.
    from .selection import TrainingGoal
    groups = training_goal_policy(TrainingGoal.MAINTENANCE, split).session_patterns
    for index, patterns in enumerate(groups):
        if last_patterns == frozenset(patterns):
            return (index + 1) % len(groups)
    return 0


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
