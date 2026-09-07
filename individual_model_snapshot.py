"""Read-only APEX Individual Model v1 aggregation over authoritative stores."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import db
from human_state.config import audit_enabled, ingest_enabled
from sqlalchemy.exc import SQLAlchemyError

SCHEMA_VERSION = "individual-model-snapshot-v1"
_PROFILE_FIELDS = ("goal", "level", "experience_level", "equipment")
_HSE_KEYS = frozenset({"motivation", "confidence", "adherence"})
_TABLE_COLUMNS = {
    "delivered_training_plans": frozenset({
        "id", "user_id", "plan_id", "plan_version", "lineage", "delivered_at",
    }),
    "training_completions": frozenset({
        "id", "user_id", "delivered_plan_id", "delivered_session_id",
        "workout_id", "completion_percent", "completed_at", "recorded_at",
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


def build_individual_model_snapshot(user_id: str, *, now: datetime | None = None) -> IndividualModelSnapshotV1:
    """Aggregate only the requesting account's persisted, typed authorities."""
    user_uuid = db._as_uuid(user_id)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        profile = db.get_profile(user_uuid)
        constraint_rows = db.list_account_training_constraint_records(user_uuid)
    except SQLAlchemyError:
        # Shadow is best-effort. An unavailable legacy database shape contributes
        # no context; it must not turn into a request-visible failure.
        profile = {}
        constraint_rows = ()
    canonical_profile = {key: profile[key] for key in _PROFILE_FIELDS if key in profile}
    constraints = tuple({key: str(row[key]) for key in ("id", "pattern", "source", "state")}
                        for row in constraint_rows)
    with db.engine.begin() as connection:
        plan = _latest_plan(connection, user_uuid)
        training = _training_section(connection, user_uuid, plan)
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


def _training_section(connection, user_uuid, plan):
    if not plan or not _has_columns(connection, db.training_completions):
        return None
    try:
        completion = connection.execute(db.select(db.training_completions).where(
            db.training_completions.c.user_id == user_uuid,
            db.training_completions.c.delivered_plan_id == plan["id"],
        ).order_by(db.training_completions.c.completed_at.desc()).limit(1)).mappings().first()
    except SQLAlchemyError:
        return None
    return {"authority": "persisted_training_lineage", "plan_id": plan["plan_id"],
            "plan_version": plan["plan_version"],
            "latest_completion_id": None if not completion else str(completion["id"]),
            "latest_session_id": None if not completion else str(completion["delivered_session_id"]),
            "completion_percent": None if not completion else completion["completion_percent"]}


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
    plan = row["plan"] if isinstance(row["plan"], dict) else {}
    return {"authority": "nutrition_plan", "plan_id": row["plan_id"], "version": row["version"],
            "targets": plan.get("targets") if isinstance(plan.get("targets"), dict) else None}


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
