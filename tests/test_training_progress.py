"""Progress reads real persisted lineage; no classifier or model runs on reads."""
from dataclasses import replace
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import delete, event, select, update

import app as appmod
import db as store
from test_my_training import _client, _complete, _persist, _user
from training_engine import build_training_plan, completion_projection, load_exercise_library
from training_engine.lineage import delivered_plan_lineage
import training_engine.training_trajectory as trajectory


def _series(owner, identifier="comparable", count=3, effort="easy"):
    plan = build_training_plan(recommendation_blueprint_id=identifier, facts={
        "goal": "strength", "level": "intermediate", "equipment": "home", "recoveryFeel": "fresh"})
    # A historical plan with repeated comparable sessions, persisted through the
    # actual lineage/completion write paths, not mocked read SQL.
    first = plan.sessions[0]
    plan = replace(plan, sessions=tuple(replace(first, session_id=f"{identifier}:session:{n}",
                   session_index=n) for n in range(1, count + 1)))
    record_id = uuid.UUID(store.persist_delivered_training_plan(owner, delivered_plan_lineage(plan)))
    for n, session in enumerate(completion_projection(plan, load_exercise_library(plan.exercise_library_version))["sessions"], 1):
        payload = {"workout_id": f"{identifier}:workout:{n}", "plan_id": plan.plan_id,
                   "plan_version": plan.version, "session_id": session["session_id"],
                   "completion_timestamp": f"2026-10-{n:02}T10:00:00Z", "exercises": []}
        for item in session["exercises"]:
            duration = item["prescription_type"] == "duration"
            payload["exercises"].append({"prescription_id": item["prescription_id"],
                "exercise_id": item["exercise_id"], "exercise_version": item["exercise_version"],
                "prescription_type": item["prescription_type"], "completed_sets": item["prescribed_sets"],
                "completed_repetitions": None if duration else item["rep_max"],
                **({"completed_duration_seconds": item["duration_max_seconds"]} if duration else {}),
                "completed_load": None, "completed_rpe": 6 if effort == "easy" else 7,
                "completed_rir": 4 if effort == "easy" else 3, "completed_effort": effort})
        store.record_training_completion(owner, {"completion": 100, "type": "training"}, payload)
    return plan, record_id


def _rows(table):
    with store.engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(table)).mappings()]


def test_authentication_and_truthful_empty_account():
    assert appmod.app.test_client().get("/api/progress").status_code == 401
    response = _client(_user()).get("/api/progress")
    assert response.status_code == 200
    assert response.json == {"record": {"completed_sessions": 0, "recent_sessions": []},
                             "exercise_trajectories": [], "recent_adjustments": []}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_account_owned_record_ignores_other_account_and_query_identity():
    owner, other = _user(), _user("foreign-progress@example.com")
    _series(other, "foreign", count=3)
    _series(owner, "owned", count=1)
    response = _client(owner).get("/api/progress?user_id=" + str(other))
    assert response.json["record"]["completed_sessions"] == 1
    text = response.get_data(as_text=True)
    assert "foreign" not in text and str(other) not in text
    assert {item["state"] for item in response.json["exercise_trajectories"]} == {"insufficient_evidence"}


@pytest.mark.parametrize("percentage,sets", [(50, 1), (100, 1), (100, 0)])
def test_partial_or_false_completed_row_and_legacy_history_are_not_progress(percentage, sets):
    owner = _user()
    plan, _ = _persist(owner)
    if sets == 0:
        with pytest.raises(ValueError, match="observed dose"):
            _complete(owner, plan, percentage=percentage, sets=sets)
    else:
        _complete(owner, plan, percentage=percentage, sets=sets)
    store.log_workout(owner, {"type": "legacy", "completion": 100})
    result = store.get_training_progress(owner)
    assert result["record"] == {"completed_sessions": 0, "recent_sessions": []}
    assert result["exercise_trajectories"] == [] and result["recent_adjustments"] == []


def test_exact_record_count_newest_five_and_observed_typed_facts_only():
    owner = _user()
    _series(owner, count=7)
    record = store.get_training_progress(owner)["record"]
    assert record["completed_sessions"] == 7
    assert [item["completed_at"][:10] for item in record["recent_sessions"]] == [
        "2026-10-07", "2026-10-06", "2026-10-05", "2026-10-04", "2026-10-03"]
    facts = record["recent_sessions"][0]["exercises"]
    assert {item["prescription_type"] for item in facts} == {"repetitions", "duration"}
    for item in facts:
        assert item["completed_sets"] > 0 and item["completed_load"] is None
        if item["prescription_type"] == "duration":
            assert item["completed_duration_seconds"] > 0 and item["completed_repetitions"] is None
        else:
            assert item["completed_repetitions"] > 0 and item["completed_duration_seconds"] is None
    for key in ("completion_percent", "score", "adherence", "calories", "workout_id", "prescription_id"):
        assert key not in str(record)


@pytest.mark.parametrize("effort,count,expected", [("easy", 3, "progressing"),
    ("productive", 3, "stable"), ("easy", 1, "insufficient_evidence")])
def test_persisted_classifier_states_project_without_reinterpreting(effort, count, expected):
    owner = _user()
    _series(owner, count=count, effort=effort)
    saved = _rows(store.training_trajectory_states)
    assert saved and {row["trajectory_state"] for row in saved} == {expected}
    result = store.get_training_progress(owner)["exercise_trajectories"]
    assert result and {item["state"] for item in result} == {expected}
    assert {(item["exercise_id"], item["exercise_version"]) for item in result} == {
        (row["exercise_id"], row["exercise_version"]) for row in saved}
    assert all(set(item) == {"exercise_id", "exercise_version", "display_name", "state"} for item in result)


def test_newer_insufficient_plan_does_not_fall_back_to_older_progressing():
    owner = _user()
    _, old = _series(owner, "older", count=3)
    _, new = _series(owner, "newer", count=1)
    with store.engine.begin() as connection:
        for identifier, day in [(old, 1), (new, 2)]:
            connection.execute(update(store.delivered_training_plans).where(
                store.delivered_training_plans.c.id == identifier).values(delivered_at=datetime(2026, 10, day, tzinfo=timezone.utc)))
    assert {item["state"] for item in store.get_training_progress(owner)["exercise_trajectories"]} == {"insufficient_evidence"}


@pytest.mark.parametrize("damage", ["foreign_completion", "foreign_event", "plan_id", "plan_version",
    "exercise_version", "unknown_exercise", "classifier", "unsupported_state", "duplicate_sources", "missing_sources"])
def test_trajectory_source_and_version_boundaries_fail_closed(damage):
    owner, other = _user(), _user("other-direction@example.com")
    _, own_plan = _series(owner, "owned", count=3)
    _series(other, "foreign", count=3)
    target = next(row for row in _rows(store.training_trajectory_states) if row["user_id"] == uuid.UUID(str(owner)))
    different = _persist(owner, "other-plan")[1] if damage == "plan_id" else None
    values = {}
    with store.engine.begin() as connection:
        connection.execute(delete(store.training_trajectory_states).where(store.training_trajectory_states.c.id != target["id"]))
        if damage in ("foreign_completion", "foreign_event"):
            table = store.training_completions if damage == "foreign_completion" else store.training_progression_events
            foreign = next(row for row in _rows(table) if row["user_id"] == uuid.UUID(str(other)))
            key = "completion_ids" if damage == "foreign_completion" else "progression_event_ids"
            values[key] = [str(foreign["id"]), *target[key][1:]]
        elif damage == "plan_id":
            values["delivered_plan_id"] = different
        elif damage == "plan_version":
            connection.execute(update(store.delivered_training_plans).where(store.delivered_training_plans.c.id == own_plan).values(plan_version="unsupported-plan-version"))
        elif damage == "exercise_version": values["exercise_version"] = "99.0.0"
        elif damage == "unknown_exercise": values["exercise_id"] = "not.canonical"
        elif damage == "classifier": values["classifier_version"] = "unrecognized"
        elif damage == "unsupported_state": values["trajectory_state"] = "plateau"
        elif damage == "duplicate_sources": values["completion_ids"] = [target["completion_ids"][0]] * 3
        else: values["progression_event_ids"] = []
        if values:
            connection.execute(update(store.training_trajectory_states).where(store.training_trajectory_states.c.id == target["id"]).values(**values))
    assert store.get_training_progress(owner)["exercise_trajectories"] == []


def test_no_older_fallback_when_newest_plan_trajectory_is_invalid():
    owner = _user()
    _, old = _series(owner, "older", count=3)
    _, new = _series(owner, "newer", count=1)
    with store.engine.begin() as connection:
        connection.execute(update(store.delivered_training_plans).where(store.delivered_training_plans.c.id == old).values(delivered_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        connection.execute(update(store.delivered_training_plans).where(store.delivered_training_plans.c.id == new).values(delivered_at=datetime(2026, 2, 1, tzinfo=timezone.utc)))
        connection.execute(update(store.training_trajectory_states).where(store.training_trajectory_states.c.delivered_plan_id == new).values(progression_event_ids=[]))
    assert store.get_training_progress(owner)["exercise_trajectories"] == []


def test_adjustments_reuse_exact_task05_projection_and_are_newest_five():
    owner = _user()
    _series(owner, count=3)
    events = sorted(_rows(store.training_progression_events), key=lambda row: (row["event_at"], row["id"]), reverse=True)
    result = store.get_training_progress(owner)["recent_adjustments"]
    assert len(result) == 5
    for item, source in zip(result, events[:5], strict=True):
        assert item["occurred_at"][:10] == source["event_at"].isoformat()[:10]
        assert item["decision_type"] == source["decision"]["decision_type"]
        assert item["exercise_id"] == source["exercise_id"]
        for key in ("load_delta_kg", "repetition_delta", "set_delta"):
            if key in item: assert str(item[key]) == str(source["decision"][key])
    with store.engine.begin() as connection:
        connection.execute(delete(store.training_progression_events))
    assert store.get_training_progress(owner)["recent_adjustments"] == []


def test_private_source_identifiers_and_policy_codes_are_not_public():
    owner = _user()
    plan, _ = _series(owner)
    text = _client(owner).get("/api/progress").get_data(as_text=True)
    for value in [str(owner), plan.plan_id, plan.version, trajectory.CLASSIFIER_VERSION,
                  *[str(row["id"]) for row in _rows(store.training_progression_events)],
                  *[str(row["id"]) for row in _rows(store.training_completions)]]:
        assert value not in text
    for key in ("reason", "policy_version", "decision_id", "completion_ids", "progression_event_ids", "classifier_version"):
        assert key not in text


def test_read_does_not_write_recompute_or_call_model(monkeypatch):
    owner = _user()
    _series(owner)
    client = _client(owner)
    def forbidden(*args, **kwargs):
        pytest.fail("Progress invoked computation, model or write")
    for name in ("_materialize_training_trajectory", "_materialize_progression_from_lineage", "rebuild_progression_state", "record_training_completion", "save_profile"):
        monkeypatch.setattr(store, name, forbidden)
    monkeypatch.setattr(trajectory, "classify", forbidden)
    monkeypatch.setattr(appmod, "_update_learning_engine", forbidden)
    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden)
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())
    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/progress")
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and response.json["exercise_trajectories"]
    assert statements and set(statements) == {"SELECT"}


def test_unavailable_store_does_not_become_an_empty_record(monkeypatch, capsys):
    client = _client(_user())
    def broken(owner):
        raise RuntimeError("PRIVATE_VALUE")
    monkeypatch.setattr(store, "get_training_progress", broken)
    response = client.get("/api/progress")
    assert response.status_code == 503 and response.json == {"error": "training_data_unavailable"}
    assert "PRIVATE_VALUE" not in response.get_data(as_text=True)
    assert "PRIVATE_VALUE" not in capsys.readouterr().out
