"""Authoritative dose/difficulty transport, observation, persistence and replay."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text

import db
from training_engine import build_training_plan, completion_projection, load_exercise_library
from training_engine.completion import workout_completion_from_payload
from training_engine.followups import serialize_conversation_plan, conversation_plan_from_record
from training_engine.lineage import delivered_plan_lineage, plan_from_delivered_lineage
from training_engine.prescription import PrescriptionType
from training_engine.renderer import render_delivery
from workout_execution import normalize_execution, lifecycle_evidence


def _plan(level="intermediate"):
    return build_training_plan(recommendation_blueprint_id="typed-dose-test", facts={
        "goal": "muscle_gain", "level": level, "equipment": "home",
        "recoveryFeel": "fresh"})


def _payload(plan):
    session = completion_projection(plan, load_exercise_library())["sessions"][0]
    return {
        "workout_id": "typed-workout", "plan_id": plan.plan_id, "plan_version": plan.version,
        "session_id": session["session_id"], "completion_timestamp": "2026-10-04T10:00:00Z",
        "exercises": [{
            "prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"], "completed_sets": item["prescribed_sets"],
            "actual_repetitions": item["rep_min"], "completed_repetitions": item["rep_min"],
            **({"prescription_type": "duration", "actual_duration_seconds": item["duration_min_seconds"],
                "completed_duration_seconds": item["duration_min_seconds"]}
               if item["prescription_type"] == "duration" else {}),
        } for item in session["exercises"]],
    }


@pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
def test_registry_difficulty_is_copied_not_inferred_from_reps(level):
    plan, library = _plan(level), load_exercise_library()
    for item in completion_projection(plan, library)["sessions"][0]["exercises"]:
        assert item["difficulty"] == library.require(item["exercise_id"], item["exercise_version"]).difficulty.value
    assert library.version == "1.4.0"


def test_new_hollow_hold_uses_versioned_explicit_seconds_without_changing_repetition_doses():
    plan = _plan()
    baseline = json.loads(Path(__file__).with_name("legacy_repetition_plan_v2.json").read_text())
    assert [item.exercise_id for item in plan.sessions[0].prescriptions] == [
        item["exercise_id"] for item in baseline["sessions"][0]["prescriptions"]]
    hold = next(item for item in plan.sessions[0].prescriptions if item.exercise_id == "bodyweight.hollow_hold")
    assert plan.version == "training-plan-blueprint-v3"
    assert hold.prescription_type is PrescriptionType.DURATION
    assert (hold.rep_min, hold.rep_max) == (None, None)
    assert (hold.duration_min_seconds, hold.duration_max_seconds) == (20, 40)
    assert hold.sets == 2
    assert "isometric-duration-policy-v1" in hold.prescription_policy_version
    for item in plan.sessions[0].prescriptions:
        if item != hold:
            assert item.prescription_type is PrescriptionType.REPETITIONS
            assert (item.rep_min, item.rep_max) == (8, 12)
            assert item.duration_min_seconds is None
    for language, unit in (("en", "sec"), ("bg", "сек")):
        assert f"| 2 | 20-40 {unit} |" in render_delivery(plan, load_exercise_library(), (), language)


def test_dead_bug_is_not_retyped_by_core_movement_pattern():
    from training_engine.prescription import duration_range
    assert duration_range("bodyweight.dead_bug") is None
    assert duration_range("bodyweight.plank") == (20, 40)


def test_duration_round_trips_through_both_real_plan_persistence_contracts():
    plan = _plan()
    assert plan_from_delivered_lineage(delivered_plan_lineage(plan)) == plan
    assert conversation_plan_from_record(serialize_conversation_plan(plan)).plan == plan


@pytest.mark.parametrize("seconds,state", [(20, "completed"), (10, "partial"), (None, "partial")])
def test_duration_execution_uses_only_observed_seconds(seconds, state):
    plan, payload = _plan(), _payload(_plan())
    hold = next(item for item in payload["exercises"] if item.get("prescription_type") == "duration")
    hold["actual_duration_seconds"] = seconds
    normalized = normalize_execution({}, payload, plan=plan)
    result = next(item for item in normalized["exercises"] if item.get("prescription_type") == "duration")
    assert result["completed_repetitions"] is None
    assert result["actual_repetitions"] is None
    assert result["completed_duration_seconds"] == seconds
    assert result["execution_state"] == ("unknown" if seconds is None else state)
    assert normalized["execution_state"] == state
    assert (lifecycle_evidence(payload, plan) is not None) == (state == "completed")


def test_prescribed_duration_is_not_observed_evidence_and_reps_cannot_stand_in_for_seconds():
    plan, payload = _plan(), _payload(_plan())
    hold = next(item for item in payload["exercises"] if item.get("prescription_type") == "duration")
    del hold["actual_duration_seconds"]
    assert lifecycle_evidence(payload, plan) is None
    hold["actual_repetitions"] = 20
    with pytest.raises(ValueError, match="cannot report repetitions"):
        normalize_execution({}, payload, plan=plan)


def test_actual_duration_persists_as_seconds_and_replays_without_repetition_progression():
    plan, payload = _plan(), _payload(_plan())
    account = db.get_or_create_user("duration-test@example.com")
    db.persist_delivered_training_plan(account, delivered_plan_lineage(plan))
    evidence = lifecycle_evidence(payload, plan)
    db.record_training_completion(account, {"completion": 100}, evidence)
    reloaded = db.list_training_completion_records(account)[0]["exercises"]["workout_completion"]
    assert workout_completion_from_payload(reloaded, plan=plan) == workout_completion_from_payload(evidence, plan=plan)
    hold = next(item for item in reloaded["exercises"] if item.get("prescription_type") == "duration")
    assert hold["completed_repetitions"] is None
    assert hold["completed_duration_seconds"] == 20
    with db.engine.begin() as connection:
        row = connection.execute(select(db.training_completion_prescriptions).where(
            db.training_completion_prescriptions.c.prescription_type == "duration")).mappings().one()
        assert row["completed_duration_seconds"] == 20
        assert row["completed_repetitions"] == 0  # Legacy NOT NULL storage sentinel, never seconds.
    history = db.list_workouts(account)[0]
    hold = next(item for item in history["exercises"] if item.get("prescription_type") == "duration")
    assert hold["actual_duration_seconds"] == 20 and hold["actual_repetitions"] is None


def test_v28_additive_upgrade_preserves_legacy_reps_and_is_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE training_completion_prescriptions "
                                "(id INTEGER PRIMARY KEY, completed_repetitions INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO training_completion_prescriptions VALUES (1, 12)"))
        db._add_training_completion_duration(connection)
        db._add_training_completion_duration(connection)
        row = connection.execute(text("SELECT * FROM training_completion_prescriptions")).mappings().one()
        assert dict(row) == {"id": 1, "completed_repetitions": 12,
                             "prescription_type": "repetitions", "completed_duration_seconds": None}
        assert {"prescription_type", "completed_duration_seconds"} <= {
            item["name"] for item in inspect(connection).get_columns("training_completion_prescriptions")}


def test_legacy_rep_based_hold_replay_does_not_apply_new_duration_policy():
    # Captured from BASE 2f66db2, including real pre-hotfix plan/prescription IDs.
    lineage = json.loads(Path(__file__).with_name("legacy_repetition_plan_v2.json").read_text())
    old = plan_from_delivered_lineage(lineage)
    assert old.version == "training-plan-blueprint-v2"
    assert delivered_plan_lineage(old) == lineage
    conversation = serialize_conversation_plan(old)
    assert conversation_plan_from_record(conversation).plan == old
    account = db.get_or_create_user("legacy-dose-test@example.com")
    first = db.persist_delivered_training_plan(account, lineage)
    assert db.persist_delivered_training_plan(account, delivered_plan_lineage(old)) == first
    payload = _payload(old)
    assert all(item.get("prescription_type", "repetitions") == "repetitions" for item in payload["exercises"])
    assert workout_completion_from_payload(payload, plan=old).to_workout_result().completed
    evidence = lifecycle_evidence(payload, old)
    db.record_training_completion(account, {"completion": 100}, evidence)
    reloaded = db.list_training_completion_records(account)[0]["exercises"]["workout_completion"]
    assert workout_completion_from_payload(reloaded, plan=old) == workout_completion_from_payload(evidence, plan=old)
    assert all("completed_duration_seconds" not in item for item in reloaded["exercises"])
