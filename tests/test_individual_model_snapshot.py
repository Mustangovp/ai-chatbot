from datetime import datetime, timezone

import db
from sqlalchemy import create_engine, text
from individual_model_snapshot import SCHEMA_VERSION, build_individual_model_snapshot
from training_engine import build_training_plan
from training_engine.lineage import delivered_plan_lineage


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
