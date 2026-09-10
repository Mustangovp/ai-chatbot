from datetime import datetime, timezone
from uuid import uuid4

import db
import pytest
from sqlalchemy import create_engine, insert, select, text
from individual_model_projection import build_projection, render_prompt
from individual_model_snapshot import SCHEMA_VERSION, build_individual_model_snapshot
from training_engine import build_training_plan, completion_projection, load_exercise_library
from training_engine.lineage import delivered_plan_lineage


def _plan():
    return build_training_plan(recommendation_blueprint_id="snapshot-completion", facts={
        "goal": "strength", "level": "intermediate", "equipment": "gym",
    })


def _completed_payload(plan):
    session = completion_projection(plan, load_exercise_library())["sessions"][0]
    return {
        "workout_id": "snapshot-completed-workout",
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "session_id": session["session_id"],
        "execution_state": "completed",
        "completion_timestamp": "2026-09-02T10:00:00Z",
        "exercises": [{
            "prescription_id": item["prescription_id"],
            "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"],
            "completed_sets": item["prescribed_sets"],
            "completed_repetitions": item["rep_max"],
            "actual_repetitions": item["rep_max"],
            "completed_load": 20,
            "completed_rpe": 6,
            "completed_rir": 4,
            "completed_effort": "easy",
        } for item in session["exercises"]],
    }


def _session(payload):
    return {
        "type": "deterministic",
        "diff": "medium",
        "execution_state": payload["execution_state"],
        "completion": 100,
        "exercises": {"workout_completion": payload},
    }


def test_snapshot_is_account_owned_and_contains_only_canonical_authorities(monkeypatch):
    user = db.get_or_create_user("snapshot@example.com")
    other = db.get_or_create_user("snapshot-other@example.com")
    db.save_profile(user, {"goal": "strength", "level": "intermediate", "equipment": "gym", "note": "ignore"})
    db.add_account_training_constraints(user, ("vertical_push",))
    plan = build_training_plan(recommendation_blueprint_id="snapshot", facts={
        "goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh"})
    db.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    db.save_nutrition_plan(user, {"id": "nutrition-snapshot", "version": "v1", "targets": {"calories": 2000}})
    db.save_profile(other, {"goal": "other"})
    monkeypatch.setattr("individual_model_snapshot.ingest_enabled", lambda: False)
    monkeypatch.setattr("individual_model_snapshot.audit_enabled", lambda: False)

    snapshot = build_individual_model_snapshot(user, now=datetime(2026, 9, 3, tzinfo=timezone.utc))

    assert snapshot.schema_version == SCHEMA_VERSION
    assert snapshot.user_id == user
    assert snapshot.profile == {"goal": "strength", "level": "intermediate", "equipment": "gym"}
    assert snapshot.constraints[0]["pattern"] == "vertical_push"
    assert snapshot.training["plan_id"] == plan.plan_id
    assert snapshot.nutrition == {"authority": "nutrition_plan", "plan_id": "nutrition-snapshot",
                                  "version": "v1", "targets": {"calories": 2000}}
    assert snapshot.adherence == "unknown"
    assert snapshot.human_state is None
    assert "ignore" not in repr(snapshot)


def test_snapshot_rebuild_is_read_only_and_does_not_merge_anonymous_or_hse_when_disabled(monkeypatch):
    user = db.get_or_create_user("snapshot-rebuild@example.com")
    db.save_profile(user, {"goal": "strength"})
    before = db.get_profile(user)
    monkeypatch.setattr("individual_model_snapshot.ingest_enabled", lambda: False)
    monkeypatch.setattr("individual_model_snapshot.audit_enabled", lambda: False)
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)

    first = build_individual_model_snapshot(user, now=now)
    second = build_individual_model_snapshot(user, now=now)

    assert first == second
    assert db.get_profile(user) == before
    assert first.training is None and first.progression == () and first.trajectory == ()


def test_snapshot_does_not_treat_an_unmarked_completion_id_as_completed_evidence(
        monkeypatch):
    user = db.get_or_create_user("snapshot-unmarked@example.com")
    plan = _plan()
    db.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    with db.engine.begin() as connection:
        stored_plan = connection.execute(select(db.delivered_training_plans).where(
            db.delivered_training_plans.c.user_id == db._as_uuid(user),
        )).mappings().one()
        stored_session = connection.execute(select(db.delivered_training_sessions).where(
            db.delivered_training_sessions.c.delivered_plan_id == stored_plan["id"],
        ).order_by(db.delivered_training_sessions.c.session_index.asc()).limit(1)).mappings().one()
        connection.execute(insert(db.training_completions).values(
            id=uuid4(), user_id=db._as_uuid(user), delivered_plan_id=stored_plan["id"],
            delivered_session_id=stored_session["id"], workout_id="id-is-not-evidence",
            completion_percent=100, completed_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        ))
    monkeypatch.setattr("individual_model_snapshot.ingest_enabled", lambda: False)
    monkeypatch.setattr("individual_model_snapshot.audit_enabled", lambda: False)

    snapshot = build_individual_model_snapshot(user)

    assert snapshot.training["latest_authoritative_completed_session_evidence"] is False
    assert "completion_id" not in snapshot.training
    assert "completed-session" not in render_prompt(build_projection(snapshot))


def test_snapshot_separates_latest_execution_from_verified_completed_evidence(monkeypatch):
    user = db.get_or_create_user("snapshot-execution-state@example.com")
    plan = _plan()
    db.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    completion = _completed_payload(plan)
    db.record_training_completion(user, _session(completion), completion)
    db.log_workout(user, {
        "type": "deterministic",
        "execution_state": "partial",
        "completion": 50,
        "exercises": [{"completed_sets": 1, "actual_repetitions": 8}],
    })
    monkeypatch.setattr("individual_model_snapshot.ingest_enabled", lambda: False)
    monkeypatch.setattr("individual_model_snapshot.audit_enabled", lambda: False)

    snapshot = build_individual_model_snapshot(user)

    assert snapshot.training["latest_execution_state"] == "partial"
    assert snapshot.training["latest_authoritative_completed_session_evidence"] is True
    assert "authoritative completed-session evidence=true" in render_prompt(
        build_projection(snapshot))


@pytest.mark.parametrize("state", ("partial", "skipped", "abandoned", "unknown"))
def test_noncompleted_execution_states_never_become_completed_snapshot_evidence(
        monkeypatch, state):
    user = db.get_or_create_user(f"snapshot-{state}@example.com")
    plan = _plan()
    db.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    exercises = {
        "partial": [{"completed_sets": 1, "actual_repetitions": 8}],
        "skipped": [{"completed_sets": 0, "actual_repetitions": None,
                     "execution_state": "skipped"}],
        "abandoned": [],
        "unknown": [],
    }[state]
    db.log_workout(user, {
        "type": "deterministic",
        "execution_state": state,
        "completion": None,
        "exercises": exercises,
    })
    monkeypatch.setattr("individual_model_snapshot.ingest_enabled", lambda: False)
    monkeypatch.setattr("individual_model_snapshot.audit_enabled", lambda: False)

    snapshot = build_individual_model_snapshot(user)

    assert snapshot.training["latest_execution_state"] == state
    assert snapshot.training["latest_authoritative_completed_session_evidence"] is False
    assert "completed-session" not in render_prompt(build_projection(snapshot))


def test_snapshot_omits_legacy_trajectory_schema_without_query_failure(monkeypatch):
    """Use a real legacy-shaped table; metadata.create_all never repairs its columns."""
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)
    db.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE training_trajectory_states"))
        connection.execute(text("""
            CREATE TABLE training_trajectory_states (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                delivered_plan_id VARCHAR(36) NOT NULL,
                exercise_id VARCHAR(128) NOT NULL,
                exercise_version VARCHAR(48) NOT NULL,
                trajectory_state VARCHAR(32) NOT NULL,
                completion_ids JSON NOT NULL,
                progression_event_ids JSON NOT NULL,
                generated_at TIMESTAMP
            )
        """))

    user = db.get_or_create_user("snapshot-legacy-trajectory@example.com")
    plan = build_training_plan(recommendation_blueprint_id="snapshot-legacy", facts={
        "goal": "strength", "level": "intermediate", "equipment": "gym",
    })
    db.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    monkeypatch.setattr("individual_model_snapshot.ingest_enabled", lambda: False)
    monkeypatch.setattr("individual_model_snapshot.audit_enabled", lambda: False)

    snapshot = build_individual_model_snapshot(user)

    assert snapshot.training is not None
    assert snapshot.trajectory == ()
