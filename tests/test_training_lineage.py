"""Individual Model v1 Slice 1: immutable account-owned training lineage."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select

import db as store
from training_engine import (
    RecoverySnapshot,
    RecoveryState,
    advance_training_lifecycle,
    build_training_plan,
    completion_projection,
    load_exercise_library,
    workout_completion_from_payload,
)
from training_engine.cross_session import adapt_from_persisted_history
from training_engine.lineage import delivered_plan_lineage


_FACTS = {"goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh"}


def _user(email):
    return store.get_or_create_user(email)


def _plan():
    return build_training_plan(recommendation_blueprint_id="lineage-v1", facts=_FACTS)


def _completion(plan, *, workout_id="lineage-workout-1", sets=None, effort="easy"):
    projection = completion_projection(plan, load_exercise_library())
    session = projection["sessions"][0]
    return {
        "workout_id": workout_id,
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "session_id": session["session_id"],
        "completion_timestamp": "2026-09-02T10:00:00Z",
        "exercises": [{
            "prescription_id": item["prescription_id"],
            "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"],
            "completed_sets": item["prescribed_sets"] if sets is None else sets,
            "completed_repetitions": item["rep_max"] if sets is None or sets > 0 else 0,
            "completed_load": 20,
            "completed_rpe": 6,
            "completed_rir": 4,
            "completed_effort": effort,
        } for item in session["exercises"]],
    }


def _session(completion, percentage=100):
    return {"type": "deterministic", "diff": "medium", "completion": percentage,
            "exercises": {"workout_completion": completion}}


def test_delivered_plan_persists_normalized_immutable_sessions_and_prescriptions_idempotently():
    user = _user("lineage-owner@example.com")
    plan = _plan()
    record = delivered_plan_lineage(plan)

    first = store.persist_delivered_training_plan(user, record)
    second = store.persist_delivered_training_plan(user, deepcopy(record))

    assert first == second
    with store.engine.begin() as connection:
        plans = connection.execute(select(func.count()).select_from(store.delivered_training_plans)).scalar_one()
        sessions = connection.execute(select(func.count()).select_from(store.delivered_training_sessions)).scalar_one()
        prescriptions = connection.execute(select(func.count()).select_from(store.delivered_training_prescriptions)).scalar_one()
    assert plans == 1
    assert sessions == len(plan.sessions)
    assert prescriptions == sum(len(session.prescriptions) for session in plan.sessions)

    changed = deepcopy(record)
    changed["sessions"][0]["prescriptions"][0]["sets"] += 1
    with pytest.raises(ValueError, match="immutable"):
        store.persist_delivered_training_plan(user, changed)


def test_v18_lineage_migration_is_additive_and_safe_to_rerun_for_legacy_accounts():
    user = _user("lineage-legacy@example.com")
    legacy_id = store.log_workout(user, {"type": "legacy", "completion": 100})

    store.run_migrations()
    store.run_migrations()

    assert legacy_id
    assert len(store.list_workouts(user)) == 1
    assert {"delivered_training_plans", "delivered_training_sessions",
            "delivered_training_prescriptions", "training_completions",
            "training_completion_prescriptions"} <= set(inspect(store.engine).get_table_names())
    with store.engine.begin() as connection:
        assert connection.execute(select(func.max(store.schema_version.c.version))).scalar_one() == 18


def test_completion_requires_exact_owned_plan_session_and_prescription_lineage():
    owner = _user("lineage-a@example.com")
    other = _user("lineage-b@example.com")
    plan = _plan()
    store.persist_delivered_training_plan(owner, delivered_plan_lineage(plan))
    completion = _completion(plan)

    legacy_id = store.record_training_completion(owner, _session(completion), completion)
    records = store.list_training_completion_records(owner)

    assert legacy_id
    assert len(records) == 1
    reloaded = records[0]["exercises"]["workout_completion"]
    assert reloaded["completion_timestamp"] == "2026-09-02T10:00:00+00:00"
    assert {key: value for key, value in reloaded.items() if key != "completion_timestamp"} == {
        key: value for key, value in completion.items() if key != "completion_timestamp"}
    assert len(store.list_workouts(owner)) == 1
    with pytest.raises(ValueError, match="unknown delivered training plan"):
        store.record_training_completion(other, _session(completion), completion)

    for field, value in (("plan_id", "unknown-plan"), ("session_id", "unknown-session"),
                         ("workout_id", "lineage-workout-2")):
        tampered = deepcopy(completion)
        tampered[field] = value
        if field == "workout_id":
            tampered["exercises"][0]["prescription_id"] = "unknown-prescription"
        with pytest.raises(ValueError):
            store.record_training_completion(owner, _session(tampered), tampered)


def test_completion_rejects_exercise_identity_mismatch_and_duplicate_without_writing_facts():
    user = _user("lineage-mismatch@example.com")
    plan = _plan()
    store.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    completion = _completion(plan)
    mismatch = deepcopy(completion)
    mismatch["exercises"][0]["exercise_id"] = "bodyweight.push_up"

    with pytest.raises(ValueError, match="does not match"):
        store.record_training_completion(user, _session(mismatch), mismatch)
    assert store.list_training_completion_records(user) == []

    store.record_training_completion(user, _session(completion), completion)
    with pytest.raises(ValueError, match="duplicate"):
        store.record_training_completion(user, _session(completion), completion)
    assert len(store.list_training_completion_records(user)) == 1


def test_partial_completion_is_factual_only_and_never_becomes_a_missed_workout():
    user = _user("lineage-partial@example.com")
    plan = _plan()
    store.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    completion = _completion(plan, sets=0, effort="incomplete")

    store.record_training_completion(user, _session(completion, percentage=50), completion)
    records = store.list_training_completion_records(user)

    assert records[0]["completion"] == 50
    assert records[0]["exercises"]["workout_completion"]["exercises"][0]["completed_sets"] == 0
    assert adapt_from_persisted_history(plan, records).applied is False
    assert "missed" not in repr(records).lower()


def test_normalized_completion_reloads_to_the_same_deterministic_progression_evidence():
    user = _user("lineage-replay@example.com")
    plan = _plan()
    store.persist_delivered_training_plan(user, delivered_plan_lineage(plan))
    completion = _completion(plan)
    store.record_training_completion(user, _session(completion), completion)

    reloaded = store.list_training_completion_records(user)[0]["exercises"]["workout_completion"]
    original_result = workout_completion_from_payload(completion, plan=plan).to_workout_result()
    reloaded_result = workout_completion_from_payload(reloaded, plan=plan).to_workout_result()
    recovery = RecoverySnapshot(RecoveryState.NORMALLY_RECOVERED, Decimal("30"), "recovery-policy-v1")

    assert reloaded_result == original_result
    assert advance_training_lifecycle(plan=plan, workouts=(reloaded_result,), recovery=recovery) == (
        advance_training_lifecycle(plan=plan, workouts=(original_result,), recovery=recovery))
    assert reloaded_result.completed_at == datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
