"""Immutable browser-to-lifecycle contract for TrainingPlanBlueprintV2 completion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Mapping

from .construction import ExercisePrescription, TrainingPlanBlueprintV2, TrainingSessionBlueprint
from .progression import ExercisePerformance, WorkoutResult
from .registry import ExerciseLibrary


def prescription_id(plan: TrainingPlanBlueprintV2, session: TrainingSessionBlueprint,
                    prescription: ExercisePrescription) -> str:
    """Stable identity for the exact prescription rendered to the browser."""
    source = {
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "session_id": session.session_id,
        "exercise_id": prescription.exercise_id,
        "exercise_version": prescription.exercise_version,
        "selection_policy_version": prescription.selection_policy_version,
        "prescription_policy_version": prescription.prescription_policy_version,
        "construction_policy_version": prescription.construction_policy_version,
    }
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "prescription_" + sha256(encoded).hexdigest()[:24]


def completion_projection(plan: TrainingPlanBlueprintV2, library: ExerciseLibrary) -> dict[str, Any]:
    """Return browser metadata copied directly from one immutable plan."""
    sessions = []
    for session in plan.sessions:
        exercises = []
        for prescription in session.prescriptions:
            exercise = library.require(prescription.exercise_id, prescription.exercise_version)
            exercises.append({
                "prescription_id": prescription_id(plan, session, prescription),
                "exercise_id": prescription.exercise_id,
                "exercise_version": prescription.exercise_version,
                "display_name": exercise.display_name,
                "prescribed_sets": prescription.sets,
                "rep_min": prescription.rep_min,
                "rep_max": prescription.rep_max,
                "rest_seconds": prescription.rest_seconds,
            })
        sessions.append({
            "session_id": session.session_id,
            "session_index": session.session_index,
            "exercises": exercises,
        })
    return {"plan_id": plan.plan_id, "plan_version": plan.version, "sessions": sessions}


@dataclass(frozen=True)
class CompletedPrescription:
    prescription_id: str
    exercise_id: str
    exercise_version: str
    completed_sets: int
    completed_repetitions: int
    completed_load: Decimal | None
    completed_rir: int | None
    completed_rpe: Decimal | None


@dataclass(frozen=True)
class WorkoutCompletion:
    """The only completion evidence accepted for deterministic lifecycle replay."""

    workout_id: str
    plan_id: str
    plan_version: str
    session_id: str
    completion_timestamp: datetime
    exercises: tuple[CompletedPrescription, ...]

    def to_workout_result(self) -> WorkoutResult:
        return WorkoutResult(
            workout_id=self.workout_id,
            plan_id=self.plan_id,
            plan_version=self.plan_version,
            completed_at=self.completion_timestamp,
            completed=True,
            performances=tuple(ExercisePerformance(
                exercise_id=item.exercise_id,
                exercise_version=item.exercise_version,
                completed_sets=item.completed_sets,
                completed_repetitions=item.completed_repetitions,
                achieved_rpe=item.completed_rpe,
                achieved_rir=item.completed_rir,
                load_kg=item.completed_load,
                completed=item.completed_sets > 0,
            ) for item in self.exercises),
        )


def workout_completion_from_payload(payload: Mapping[str, Any], *, plan: TrainingPlanBlueprintV2) -> WorkoutCompletion:
    """Validate a browser payload against the exact plan it claims to complete."""
    if not isinstance(payload, Mapping):
        raise ValueError("workout completion must be an object")
    if payload.get("plan_id") != plan.plan_id or payload.get("plan_version") != plan.version:
        raise ValueError("workout completion must identify the active training plan")
    session = _session(plan, _text(payload.get("session_id"), "session_id"))
    raw_exercises = payload.get("exercises")
    if not isinstance(raw_exercises, list) or not raw_exercises:
        raise ValueError("workout completion requires completed exercises")
    expected = {prescription_id(plan, session, item): item for item in session.prescriptions}
    completed = tuple(_completed_exercise(item, expected) for item in raw_exercises)
    if {item.prescription_id for item in completed} != set(expected):
        raise ValueError("workout completion must contain every rendered session prescription exactly once")
    if len(completed) != len({item.prescription_id for item in completed}):
        raise ValueError("workout completion contains duplicate prescription identity")
    return WorkoutCompletion(
        workout_id=_text(payload.get("workout_id"), "workout_id"),
        plan_id=plan.plan_id,
        plan_version=plan.version,
        session_id=session.session_id,
        completion_timestamp=_timestamp(payload.get("completion_timestamp")),
        exercises=completed,
    )


def validate_workout_completion_payload(payload: Any) -> None:
    """Reject malformed browser evidence at /api/workout without inferring IDs."""
    if not isinstance(payload, Mapping):
        raise ValueError("workout completion must be an object")
    for field in ("workout_id", "plan_id", "plan_version", "session_id", "completion_timestamp"):
        _text(payload.get(field), field)
    _timestamp(payload.get("completion_timestamp"))
    exercises = payload.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        raise ValueError("workout completion requires completed exercises")
    for item in exercises:
        if not isinstance(item, Mapping):
            raise ValueError("completed exercise must be an object")
        for field in ("prescription_id", "exercise_id", "exercise_version"):
            _text(item.get(field), field)
        _nonnegative_int(item.get("completed_sets"), "completed_sets")
        _nonnegative_int(item.get("completed_repetitions"), "completed_repetitions")
        _optional_decimal(item.get("completed_load"), "completed_load")
        _optional_int(item.get("completed_rir"), "completed_rir", 0, 10)
        _optional_decimal(item.get("completed_rpe"), "completed_rpe", Decimal("1"), Decimal("10"))


def _session(plan: TrainingPlanBlueprintV2, session_id: str) -> TrainingSessionBlueprint:
    for session in plan.sessions:
        if session.session_id == session_id:
            return session
    raise ValueError("workout completion references an unknown plan session")


def _completed_exercise(payload: Any, expected: Mapping[str, ExercisePrescription]) -> CompletedPrescription:
    if not isinstance(payload, Mapping):
        raise ValueError("completed exercise must be an object")
    identifier = _text(payload.get("prescription_id"), "prescription_id")
    prescription = expected.get(identifier)
    if prescription is None:
        raise ValueError("completed exercise does not originate from the rendered blueprint")
    if (payload.get("exercise_id"), payload.get("exercise_version")) != (prescription.exercise_id, prescription.exercise_version):
        raise ValueError("completed exercise identity does not match its prescription")
    sets = _nonnegative_int(payload.get("completed_sets"), "completed_sets")
    repetitions = _nonnegative_int(payload.get("completed_repetitions"), "completed_repetitions")
    if sets > prescription.sets:
        raise ValueError("completed sets exceed the rendered prescription")
    if (sets == 0) != (repetitions == 0):
        raise ValueError("completed work must include both sets and repetitions")
    return CompletedPrescription(
        prescription_id=identifier,
        exercise_id=prescription.exercise_id,
        exercise_version=prescription.exercise_version,
        completed_sets=sets,
        completed_repetitions=repetitions,
        completed_load=_optional_decimal(payload.get("completed_load"), "completed_load"),
        completed_rir=_optional_int(payload.get("completed_rir"), "completed_rir", 0, 10),
        completed_rpe=_optional_decimal(payload.get("completed_rpe"), "completed_rpe", Decimal("1"), Decimal("10")),
    )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("completion_timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("completion_timestamp must use ISO-8601") from error
    if parsed.tzinfo is None:
        raise ValueError("completion_timestamp must include a timezone")
    return parsed


def _nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _optional_int(value: Any, field: str, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field} is invalid")
    return value


def _optional_decimal(value: Any, field: str, minimum: Decimal | None = Decimal("0"),
                      maximum: Decimal | None = None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except Exception as error:
        raise ValueError(f"{field} is invalid") from error
    if (minimum is not None and parsed < minimum) or (maximum is not None and parsed > maximum):
        raise ValueError(f"{field} is invalid")
    return parsed
