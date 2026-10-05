"""Completion receipts and refresh projections over real persisted SQLite rows."""
import uuid

import pytest
from sqlalchemy import delete, event, insert, select, update

import app as appmod
import db as store
from training_engine import completion_projection, load_exercise_library
from test_my_training import _client, _persist, _user


def _post_completed(owner):
    plan, record_id = _persist(owner)
    first = completion_projection(plan, load_exercise_library(plan.exercise_library_version))["sessions"][0]
    payload = {"workout_id": "receipt-" + uuid.uuid4().hex, "plan_id": plan.plan_id,
               "plan_version": plan.version, "session_id": first["session_id"],
               "completion_timestamp": "2026-10-05T07:00:00Z", "execution_state": "completed",
               "exercises": []}
    for item in first["exercises"]:
        duration = item["prescription_type"] == "duration"
        dose = item["duration_min_seconds"] + 1 if duration else item["rep_min"] + 1
        payload["exercises"].append({
            "prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"], "prescription_type": item["prescription_type"],
            "completed_sets": item["prescribed_sets"], "execution_state": "completed",
            "completed_repetitions": None if duration else dose, "actual_repetitions": None if duration else dose,
            **({"completed_duration_seconds": dose, "actual_duration_seconds": dose} if duration else {}),
            "completed_load": None, "completed_rpe": 7, "completed_rir": 3, "completed_effort": "productive",
        })
    client = _client(owner)
    response = client.post("/api/workout", json={"session": {"completion": 100, "type": "training",
                          "execution_schema": "workout-execution-v1", "execution_state": "completed",
                          "exercises": payload["exercises"]}, "workout_completion": payload})
    assert response.status_code == 200, response.json
    return client, plan, record_id, payload, response.json


def _events(owner):
    with store.engine.connect() as connection:
        return connection.execute(select(store.training_progression_events).where(
            store.training_progression_events.c.user_id == uuid.UUID(str(owner)))).mappings().all()


def test_receipt_uses_exact_immutable_completion_and_survives_refresh():
    owner = _user()
    client, _, _, payload, response = _post_completed(owner)
    assert response["ok"] is True
    assert response["adaptation"]["workout_id"] == payload["workout_id"]
    events = _events(owner)
    assert events
    with store.engine.connect() as connection:
        row = connection.execute(select(store.training_completions)).mappings().one()
        assert row["workout_id"] == payload["workout_id"] and row["completion_percent"] == 100
        facts = connection.execute(select(store.training_completion_prescriptions).order_by(
            store.training_completion_prescriptions.c.prescription_index)).mappings().all()
    result = client.get("/api/my-training").json["last_completed"]
    assert result["adjustments"] == response["adaptation"]["decisions"]
    for projected, saved, observed in zip(result["exercises"], facts, payload["exercises"], strict=True):
        assert projected["completed_sets"] == saved["completed_sets"] == observed["completed_sets"]
        assert projected["completed_load"] is None
        assert projected["completed_effort"] == "productive"
        assert projected["completed_rpe"] == 7 and projected["completed_rir"] == 3
        if observed["prescription_type"] == "duration":
            assert projected["completed_repetitions"] is None
            assert projected["completed_duration_seconds"] == observed["actual_duration_seconds"]
        else:
            assert projected["completed_repetitions"] == observed["actual_repetitions"]
    for decision, persisted in zip(result["adjustments"], events, strict=True):
        assert decision["decision_type"] == persisted["decision"]["decision_type"]
    assert client.post("/api/workout", json={"session": {"completion": 100}, "workout_completion": payload}).status_code == 400


@pytest.mark.parametrize("kind,key,value", [
    ("increase_load", "load_delta_kg", "1.25"),
    ("increase_repetitions", "repetition_delta", 2),
    ("increase_sets", "set_delta", 1),
    ("maintain", None, None), ("deload", None, None), ("replace_exercise", None, None),
])
def test_bounded_decision_mapping_preserves_persisted_values(kind, key, value):
    owner = _user()
    _, _, _, payload, _ = _post_completed(owner)
    source = _events(owner)[0]
    raw = {"decision_id": "persisted-decision", "decision_type": kind,
           "reason": "PRIVATE_POLICY_REASON", "policy_version": "PRIVATE_POLICY_VERSION",
           "load_delta_kg": None, "repetition_delta": None, "set_delta": None,
           "replacement_exercise_id": None, "replacement_exercise_version": None}
    if key:
        raw[key] = value
    if kind == "replace_exercise":
        raw.update(replacement_exercise_id="bodyweight.push_up", replacement_exercise_version="1.0.0")
    with store.engine.begin() as connection:
        connection.execute(delete(store.training_progression_events).where(store.training_progression_events.c.id != source["id"]))
        connection.execute(update(store.training_progression_events).where(store.training_progression_events.c.id == source["id"]).values(decision=raw))
    [projected] = store.get_workout_adaptation(owner, payload)["decisions"]
    assert projected["decision_type"] == kind
    if key:
        assert projected[key] == value
    else:
        assert not {"load_delta_kg", "repetition_delta", "set_delta", "percentage"}.intersection(projected)
    if kind == "replace_exercise":
        assert projected["replacement"] == {"exercise_id": "bodyweight.push_up", "exercise_version": "1.0.0", "display_name": "Push-Up"}
    assert "PRIVATE" not in str(projected)
    assert not {"reason", "policy_version", "decision_id", "event_id"}.intersection(projected)


def test_missing_events_are_not_inferred():
    owner = _user()
    client, _, _, payload, _ = _post_completed(owner)
    with store.engine.begin() as connection:
        connection.execute(delete(store.training_progression_events))
    assert store.get_workout_adaptation(owner, payload) == {"workout_id": payload["workout_id"], "decisions": []}
    assert client.get("/api/my-training").json["last_completed"]["adjustments"] == []


def test_no_other_account_or_completion_can_supply_decisions():
    owner = _user()
    _, _, _, payload, _ = _post_completed(owner)
    other = _user("other-receipt@example.com")
    assert store.get_workout_adaptation(other, payload) is None
    assert _client(other).get("/api/my-training").json["last_completed"] is None
    damaged = {**payload, "session_id": "different-session"}
    assert store.get_workout_adaptation(owner, damaged) is None
    source = _events(owner)[0]
    foreign = {**dict(source), "id": uuid.uuid4(), "user_id": uuid.UUID(str(other)), "prescription_id": "foreign-prescription"}
    with store.engine.begin() as connection:
        connection.execute(insert(store.training_progression_events).values(**foreign))
    assert len(store.get_workout_adaptation(owner, payload)["decisions"]) == len(_events(owner))


@pytest.mark.parametrize("field,value", [("exercise_id", "bodyweight.hspu"), ("exercise_version", "999"),
                                          ("prescription_id", "wrong"), ("delivered_session_id", uuid.uuid4())])
def test_inconsistent_event_identity_fails_closed(field, value):
    owner = _user()
    _, _, _, payload, _ = _post_completed(owner)
    source = _events(owner)[0]
    # SQLite contract fixture permits corrupt historical identities without mocking the read SQL.
    with store.engine.begin() as connection:
        connection.execute(update(store.training_progression_events).where(store.training_progression_events.c.id == source["id"]).values(**{field: value}))
    assert store.get_workout_adaptation(owner, payload)["decisions"] == []


def test_reads_never_recompute_write_or_call_model(monkeypatch):
    owner = _user()
    client, _, _, payload, _ = _post_completed(owner)
    def forbidden(*args, **kwargs):
        pytest.fail("receipt read invoked authority/write/model")
    for name in ("_materialize_progression_from_lineage", "_materialize_training_trajectory", "record_training_completion"):
        monkeypatch.setattr(store, name, forbidden)
    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden)
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())
    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        assert store.get_workout_adaptation(owner, payload)["decisions"]
        assert client.get("/api/my-training").status_code == 200
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)
    assert statements and set(statements) == {"SELECT"}


def test_optional_receipt_failure_does_not_undo_completion(monkeypatch):
    owner = _user()
    monkeypatch.setattr(store, "get_workout_adaptation", lambda *args: (_ for _ in ()).throw(RuntimeError("private")))
    _, _, _, _, response = _post_completed(owner)
    assert response["ok"] and response["adaptation"] is None
    with store.engine.connect() as connection:
        assert connection.execute(select(store.training_completions)).mappings().one()


def test_completion_receipt_needs_no_model_or_learning_call(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("completion receipt invoked a model/learning call")
    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden)
    monkeypatch.setattr(appmod, "_update_learning_engine", forbidden)
    assert _post_completed(_user())[-1]["adaptation"]["decisions"]
