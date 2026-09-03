from datetime import datetime, timezone

import db
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
