"""Factual My Training reads over real SQLite persistence and real auth cookies."""
from copy import deepcopy
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import delete, event, select, update

import app as appmod
import db as store
from training_engine import build_training_plan, completion_projection, load_exercise_library
from training_engine.lineage import delivered_plan_lineage


def _user(email="training-home@example.com"):
    return store.get_or_create_user(email)


def _client(owner):
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(owner))
    return client


def _persist(owner, identifier="home-plan", library_version=None):
    plan = build_training_plan(recommendation_blueprint_id=identifier, facts={
        "goal": "strength", "level": "intermediate", "equipment": "home", "recoveryFeel": "fresh",
    }, **({"library": load_exercise_library(library_version)} if library_version else {}))
    record_id = store.persist_delivered_training_plan(owner, delivered_plan_lineage(plan))
    return plan, uuid.UUID(record_id)


def _complete(owner, plan, *, load=None, sets=None, percentage=100):
    first = completion_projection(plan, load_exercise_library(plan.exercise_library_version))["sessions"][0]
    payload = {"workout_id": "completed-home-" + uuid.uuid4().hex,
               "plan_id": plan.plan_id, "plan_version": plan.version, "session_id": first["session_id"],
               "completion_timestamp": "2026-10-04T10:00:00Z", "exercises": []}
    for item in first["exercises"]:
        duration = item["prescription_type"] == "duration"
        payload["exercises"].append({
            "prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"], "prescription_type": item["prescription_type"],
            "completed_sets": item["prescribed_sets"] if sets is None else sets,
            "completed_repetitions": None if duration else item["rep_min"],
            **({"completed_duration_seconds": item["duration_min_seconds"]} if duration else {}),
            "completed_load": load,
        })
    store.record_training_completion(owner, {"completion": percentage, "type": "training"}, payload)
    return payload


def test_requires_authentication_and_empty_account_is_truthful():
    assert appmod.app.test_client().get("/api/my-training").status_code == 401
    response = _client(_user()).get("/api/my-training")
    assert response.status_code == 200
    assert response.json == {"latest_workout": None, "last_completed": None, "active_constraints": []}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_owned_first_session_only_and_no_later_plan_or_policy_noise():
    owner = _user()
    plan, _ = _persist(owner)
    assert len(plan.sessions) > 1
    response = _client(owner).get("/api/my-training")
    latest = response.json["latest_workout"]
    assert latest is not None
    assert latest["estimated_duration_minutes"] == plan.sessions[0].estimated_duration_minutes
    assert [item["exercise_id"] for item in latest["exercises"]] == [item.exercise_id for item in plan.sessions[0].prescriptions]
    assert set(latest) == {"delivered_at", "estimated_duration_minutes", "exercises"}
    text = response.get_data(as_text=True)
    for session in plan.sessions:
        assert session.session_id not in text
    for key in ("sessions", "next_session", "upcoming_sessions", "remaining_sessions", "lineage", "policy_version", "weekly_volume"):
        assert key not in text
    library = load_exercise_library(plan.exercise_library_version)
    for item, prescription in zip(latest["exercises"], plan.sessions[0].prescriptions, strict=True):
        assert item["difficulty"] == library.require(prescription.exercise_id, prescription.exercise_version).difficulty.value
        assert item["sets"] == prescription.sets
        assert item["rpe"] == float(prescription.target_rpe)
        assert item["rir"] == prescription.target_rir
        assert item["tempo"] == prescription.tempo


def test_newest_delivered_plan_wins_without_scheduled_status():
    owner = _user()
    _, old = _persist(owner, "old")
    plan, new = _persist(owner, "new")
    with store.engine.begin() as connection:
        connection.execute(update(store.delivered_training_plans).where(store.delivered_training_plans.c.id == old).values(delivered_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        connection.execute(update(store.delivered_training_plans).where(store.delivered_training_plans.c.id == new).values(delivered_at=datetime(2026, 2, 1, tzinfo=timezone.utc)))
    latest = store.get_my_training(owner)["latest_workout"]
    assert latest["delivered_at"].startswith("2026-02-01")
    assert [item["exercise_id"] for item in latest["exercises"]] == [item.exercise_id for item in plan.sessions[0].prescriptions]


def test_repetition_and_duration_are_projected_without_conversion():
    owner = _user()
    plan, _ = _persist(owner)
    latest = store.get_my_training(owner)["latest_workout"]
    kinds = {item["prescription_type"] for item in latest["exercises"]}
    assert kinds == {"repetitions", "duration"}
    for item in latest["exercises"]:
        if item["prescription_type"] == "duration":
            assert item["rep_min"] is None and item["rep_max"] is None
            assert item["duration_min_seconds"] > 0
        else:
            assert item["duration_min_seconds"] is None
            assert item["rep_min"] > 0


@pytest.mark.parametrize("load", [None, 12.5])
def test_immutable_observed_completion_and_missing_load(load):
    owner = _user()
    plan, _ = _persist(owner)
    payload = _complete(owner, plan, load=load)
    result = _client(owner).get("/api/my-training").json["last_completed"]
    assert result is not None
    assert result["completed_at"].startswith("2026-10-04T10:00:00")
    assert result["completion_percent"] == 100
    for item, fact in zip(result["exercises"], payload["exercises"], strict=True):
        assert item["completed_sets"] == fact["completed_sets"]
        assert item["completed_repetitions"] == fact["completed_repetitions"]
        assert item["completed_duration_seconds"] == fact.get("completed_duration_seconds")
        assert item["completed_load"] == load
    assert "prescription_id" not in str(result)
    assert "workout_id" not in str(result)


@pytest.mark.parametrize("percentage,sets", [(50, 1), (100, 1)])
def test_partial_or_contradictory_immutable_record_is_not_completed(percentage, sets):
    owner = _user()
    plan, _ = _persist(owner)
    _complete(owner, plan, sets=sets, percentage=percentage)
    assert store.get_my_training(owner)["last_completed"] is None


def test_other_account_plan_completion_and_constraints_never_leak():
    owner = _user()
    other = _user("other-training@example.com")
    plan, _ = _persist(other)
    _complete(other, plan)
    store.add_account_training_constraints(other, ["vertical_push"])
    assert _client(owner).get("/api/my-training").json == {"latest_workout": None, "last_completed": None, "active_constraints": []}
    own, _ = _persist(owner, "owned")
    store.add_account_training_constraints(owner, ["lunge"])
    data = _client(owner).get("/api/my-training?user_id=" + str(other)).json
    assert [item["exercise_id"] for item in data["latest_workout"]["exercises"]] == [item.exercise_id for item in own.sessions[0].prescriptions]
    assert data["last_completed"] is None
    assert [item["pattern"] for item in data["active_constraints"]] == ["lunge"]


def test_active_constraints_only_and_no_health_reason():
    owner = _user()
    store.add_account_training_constraints(owner, ["vertical_push", "squat"])
    rows = store.list_account_training_constraint_records(owner)
    retired = next(item for item in rows if item["pattern"] == "squat")
    store.retire_account_training_constraint(owner, retired["id"])
    data = _client(owner).get("/api/my-training").json
    assert [item["pattern"] for item in data["active_constraints"]] == ["vertical_push"]
    assert set(data["active_constraints"][0]) == {"id", "pattern"}


@pytest.mark.parametrize("damage", ["lineage", "metadata", "first_identity", "missing_session", "missing_prescription", "prescription_mismatch", "bad_duration"])
def test_incomplete_optional_lineage_fails_closed(damage):
    owner = _user()
    _, record_id = _persist(owner)
    with store.engine.begin() as connection:
        row = connection.execute(select(store.delivered_training_plans).where(store.delivered_training_plans.c.id == record_id)).mappings().one()
        lineage = deepcopy(row["lineage"])
        first = connection.execute(select(store.delivered_training_sessions).where(store.delivered_training_sessions.c.delivered_plan_id == record_id, store.delivered_training_sessions.c.session_index == 1)).mappings().one()
        if damage == "missing_session":
            connection.execute(delete(store.delivered_training_prescriptions).where(store.delivered_training_prescriptions.c.delivered_session_id == first["id"]))
            connection.execute(delete(store.delivered_training_sessions).where(store.delivered_training_sessions.c.id == first["id"]))
        elif damage == "missing_prescription":
            connection.execute(delete(store.delivered_training_prescriptions).where(store.delivered_training_prescriptions.c.delivered_session_id == first["id"]))
        elif damage == "prescription_mismatch":
            connection.execute(update(store.delivered_training_prescriptions).where(store.delivered_training_prescriptions.c.delivered_session_id == first["id"]).values(prescription={}))
        else:
            if damage == "lineage": lineage = {}
            elif damage == "metadata": lineage["metadata"] = {}
            elif damage == "first_identity": lineage["sessions"][0]["session_id"] = "not-delivered"
            else: lineage["sessions"][0]["estimated_duration_minutes"] = 0
            connection.execute(update(store.delivered_training_plans).where(store.delivered_training_plans.c.id == record_id).values(lineage=lineage))
    response = _client(owner).get("/api/my-training")
    assert response.status_code == 200
    assert response.json["latest_workout"] is None


def test_read_only_no_model_learning_or_progression(monkeypatch):
    owner = _user()
    plan, _ = _persist(owner)
    _complete(owner, plan)
    client = _client(owner)
    def forbidden(*args, **kwargs):
        pytest.fail("My Training invoked a write/model/materialization")
    for name in ("persist_delivered_training_plan", "record_training_completion", "save_profile", "_materialize_progression_from_lineage", "_materialize_training_trajectory"):
        monkeypatch.setattr(store, name, forbidden)
    monkeypatch.setattr(appmod, "_update_learning_engine", forbidden)
    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden)
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())
    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/my-training")
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert statements and set(statements) == {"SELECT"}


def test_unavailable_constraint_store_is_not_empty(monkeypatch):
    client = _client(_user())
    monkeypatch.setattr(store, "get_my_training", lambda owner: (_ for _ in ()).throw(RuntimeError("private detail")))
    response = client.get("/api/my-training")
    assert response.status_code == 503
    assert response.json == {"error": "training_data_unavailable"}
