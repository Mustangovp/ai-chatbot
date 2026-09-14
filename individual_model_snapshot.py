"""Read-only APEX Individual Model v1 aggregation over authoritative stores."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import db
import nutrition_plan
from constraint_store_state import ConstraintStoreUnavailable, load_constraints
from human_state.config import audit_enabled, ingest_enabled
from sqlalchemy.exc import SQLAlchemyError

SCHEMA_VERSION = "individual-model-snapshot-v1"
_PROFILE_FIELDS = ("goal", "level", "experience_level", "equipment")
_HSE_KEYS = frozenset({"motivation", "confidence", "adherence"})
_CONSTRAINT_PATTERNS = frozenset({
    "vertical_push", "horizontal_push", "vertical_pull", "squat", "lunge", "hinge",
})


class CompletionEvidenceFreshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class IndividualModelSnapshotUnavailable(RuntimeError):
    """Optional context cannot safely read all required authoritative sources."""
_TABLE_COLUMNS = {
    "delivered_training_plans": frozenset({
        "id", "user_id", "plan_id", "plan_version", "lineage", "delivered_at",
    }),
    "training_completions": frozenset({
        "id", "user_id", "delivered_plan_id", "delivered_session_id",
        "workout_id", "execution_schema", "execution_state", "completion_percent",
        "completed_at", "recorded_at",
    }),
    "workout_history": frozenset({
        "id", "user_id", "execution_state", "occurred_at",
    }),
    "exercise_progression_states": frozenset({
        "id", "user_id", "delivered_plan_id", "exercise_id", "exercise_version",
        "source_completion_id", "state", "updated_at",
    }),
    "training_trajectory_states": frozenset({
        "id", "user_id", "delivered_plan_id", "exercise_id", "exercise_version",
        "classifier_version", "trajectory_state", "completion_ids",
        "progression_event_ids", "generated_at",
    }),
    "nutrition_plans": frozenset({
        "id", "user_id", "plan_id", "version", "plan", "created_at",
    }),
}


@dataclass(frozen=True)
class IndividualModelSnapshotV1:
    schema_version: str
    user_id: str
    profile: dict[str, Any]
    constraints: tuple[dict[str, str], ...]
    training: dict[str, Any] | None
    progression: tuple[dict[str, Any], ...]
    trajectory: tuple[dict[str, Any], ...]
    adherence: str
    human_state: dict[str, Any] | None
    nutrition: dict[str, Any] | None
    generated_at: datetime


def build_individual_model_snapshot(
        user_id: str,
        *,
        evaluation_time: datetime | None = None,
        now: datetime | None = None,
) -> IndividualModelSnapshotV1:
    """Aggregate only the requesting account's persisted, typed authorities."""
    user_uuid = db._as_uuid(user_id)
    current = _evaluation_time(evaluation_time, now)
    try:
        profile = db.get_profile(user_uuid)
        constraint_patterns = load_constraints(
            lambda: db.list_account_training_constraints(user_uuid),
            _CONSTRAINT_PATTERNS,
        ).require_available()
    except (SQLAlchemyError, ConstraintStoreUnavailable) as error:
        # An unavailable constraint source is never equivalent to no constraints.
        # Omit this optional context instead of risking unsafe recommendation drift.
        raise IndividualModelSnapshotUnavailable("constraint_store_unavailable") from error
    profile = profile if isinstance(profile, dict) else {}
    canonical_profile = {key: profile[key] for key in _PROFILE_FIELDS if key in profile}
    constraints = tuple({"pattern": pattern} for pattern in constraint_patterns)
    with db.engine.begin() as connection:
        plan = _latest_plan(connection, user_uuid)
        training = _training_section(
            connection, user_uuid, plan,
            evaluation_time=current,
        )
        progression = _state_rows(connection, db.exercise_progression_states, user_uuid, plan, "state")
        trajectory = _state_rows(connection, db.training_trajectory_states, user_uuid, plan, "trajectory_state")
        nutrition = _nutrition_section(connection, user_uuid)
    return IndividualModelSnapshotV1(
        SCHEMA_VERSION, str(user_uuid), canonical_profile, constraints, training, progression, trajectory,
        "unknown", _human_state_section(str(user_uuid), current), nutrition, current)


def _has_columns(connection, table) -> bool:
    """Avoid selecting metadata-only columns from an older partial database table."""
    try:
        available = {column["name"] for column in db.inspect(connection).get_columns(table.name)}
    except SQLAlchemyError:
        return False
    return _TABLE_COLUMNS[table.name].issubset(available)


def _latest_plan(connection, user_uuid):
    if not _has_columns(connection, db.delivered_training_plans):
        return None
    try:
        return connection.execute(db.select(db.delivered_training_plans).where(
            db.delivered_training_plans.c.user_id == user_uuid,
        ).order_by(db.delivered_training_plans.c.delivered_at.desc()).limit(1)).mappings().first()
    except SQLAlchemyError:
        return None


def _training_section(connection, user_uuid, plan, *, evaluation_time):
    if not plan or not _has_columns(connection, db.training_completions):
        return None
    try:
        completion = connection.execute(db.select(db.training_completions).where(
            db.training_completions.c.user_id == user_uuid,
            db.training_completions.c.delivered_plan_id == plan["id"],
            db.training_completions.c.execution_schema == "workout-execution-v1",
            db.training_completions.c.execution_state == "completed",
            db.training_completions.c.completion_percent == 100,
        ).order_by(db.training_completions.c.completed_at.desc()).limit(1)).mappings().first()
        latest_execution_state = _latest_execution_state(connection, user_uuid)
    except SQLAlchemyError:
        return None
    source_timestamp = _persisted_completion_timestamp(completion["completed_at"]) if completion else None
    freshness = (_completion_evidence_freshness(
        source_timestamp, evaluation_time=evaluation_time, policy=None)
                 if completion else None)
    return {"authority": "persisted_training_lineage", "plan_id": plan["plan_id"],
            "plan_version": plan["plan_version"],
            "latest_execution_state": latest_execution_state,
            "latest_authoritative_completed_session_evidence": completion is not None,
            "latest_authoritative_completed_session_occurred_at": source_timestamp,
            "latest_authoritative_completed_session_freshness": freshness}


def _evaluation_time(evaluation_time: object | None, legacy_now: object | None) -> datetime:
    """Use caller-supplied UTC time when valid; wall clock stays at the boundary."""
    supplied = evaluation_time if evaluation_time is not None else legacy_now
    parsed = _utc_timestamp(supplied) if supplied is not None else None
    return parsed if parsed is not None else datetime.now(timezone.utc)


def _completion_evidence_freshness(
        completion_timestamp: object,
        *,
        evaluation_time: object,
        policy: object | None,
) -> str:
    """No product-wide policy exists, so completion freshness is always unknown."""
    completed_at = _utc_timestamp(completion_timestamp)
    evaluated_at = _utc_timestamp(evaluation_time)
    if completed_at is None or evaluated_at is None:
        return CompletionEvidenceFreshness.UNKNOWN.value
    # A future policy must be an explicitly authorized product contract, not
    # caller data. This slice intentionally supports no such policy.
    if policy is not None:
        return CompletionEvidenceFreshness.UNKNOWN.value
    return CompletionEvidenceFreshness.UNKNOWN.value


def _utc_timestamp(value: object) -> datetime | None:
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
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _persisted_completion_timestamp(value: object) -> datetime | None:
    """Restore SQLite's lost UTC metadata only for marker-backed writer output."""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return _utc_timestamp(value)


def _latest_execution_state(connection, user_uuid):
    """Return only a closed execution state; old untyped history stays unknown."""
    if not _has_columns(connection, db.workout_history):
        return None
    row = connection.execute(db.select(db.workout_history.c.execution_state).where(
        db.workout_history.c.user_id == user_uuid,
    ).order_by(db.workout_history.c.occurred_at.desc()).limit(1)).mappings().first()
    if not row:
        return None
    state = row["execution_state"]
    return state if state in {"completed", "partial", "skipped", "abandoned", "unknown"} else "unknown"


def _state_rows(connection, table, user_uuid, plan, field):
    if not plan or not _has_columns(connection, table):
        return ()
    try:
        rows = connection.execute(db.select(table).where(table.c.user_id == user_uuid,
            table.c.delivered_plan_id == plan["id"])).mappings().all()
    except SQLAlchemyError:
        return ()
    return tuple({"authority": "deterministic_progression" if table is db.exercise_progression_states
                  else "training_trajectory", "exercise_id": row["exercise_id"],
                  "exercise_version": row["exercise_version"], field: row[field],
                  "source_completion_id": str(row["source_completion_id"])
                  if "source_completion_id" in row else None,
                  "completion_ids": tuple(row["completion_ids"]) if "completion_ids" in row else (),
                  "progression_event_ids": tuple(row["progression_event_ids"])
                  if "progression_event_ids" in row else ()}
                 for row in rows)


def _nutrition_section(connection, user_uuid):
    if not _has_columns(connection, db.nutrition_plans):
        return None
    try:
        row = connection.execute(db.select(db.nutrition_plans).where(
            db.nutrition_plans.c.user_id == user_uuid).order_by(db.nutrition_plans.c.created_at.desc()).limit(1)).mappings().first()
    except SQLAlchemyError:
        return None
    if not row:
        return None
    try:
        plan = nutrition_plan.from_record(row["plan"])
    except (TypeError, ValueError, nutrition_plan.NutritionPlanError):
        return None
    targets = {
        "calories": plan.targets.kcal,
        "protein_g": plan.targets.protein,
        "carbs_g": plan.targets.carbs,
        "fat_g": plan.targets.fat,
    }
    return {
        "authority": "nutrition_plan",
        "targets": {key: value for key, value in targets.items() if value is not None},
    }


def _human_state_section(user_id, now):
    if not (ingest_enabled() or audit_enabled()):
        return None
    try:
        rows = db.hs_get_all(f"user:{user_id}")
    except SQLAlchemyError:
        return None
    values = {}
    for row in rows:
        if row.get("key") not in _HSE_KEYS or not isinstance(row.get("observed_at"), datetime):
            continue
        observed = row["observed_at"].astimezone(timezone.utc)
        if (now - observed).total_seconds() > int(row.get("ttl_seconds") or 0):
            continue
        values[row["key"]] = {"value": row.get("value"), "confidence": row.get("confidence"),
                              "observed_at": observed.isoformat()}
    return values or None
