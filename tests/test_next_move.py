"""Next Move M1: real account-owned SQLite reads, no network or autonomous writes."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import event, select

import app as appmod
import db as store
from coaching import next_move
from human_state.schema import Reading
import human_state
from training_engine import build_training_plan, completion_projection, load_exercise_library
from training_engine.lineage import delivered_plan_lineage


PROFILE = {"goal": "strength", "age": "30", "level": "intermediate", "equipment": "gym",
           "activityLevel": "active", "frequency": "3", "recoveryFeel": "fresh",
           "sleepQuality": "good", "stressLevel": "low", "weight": "75", "height": "178", "gender": "male"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("APEX_NEXT_MOVE_ENABLED", "true")
    monkeypatch.setattr(appmod.HumanLearningEngine, "extract_facts", lambda *_: {})
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_: pytest.fail("Unexpected model call"))
    yield


def account(email="next-move@example.invalid", profile=None):
    owner = store.get_or_create_user(email)
    store.save_profile(owner, PROFILE if profile is None else profile)
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(owner))
    return owner, client


def recommendation(client, language="en"):
    response = client.get("/api/next-move?lang=" + language)
    assert response.status_code == 200, response.json
    assert response.headers["Cache-Control"] == "private, no-store"
    return response.json["recommendation"]


def checkin(client, value="fresh"):
    response = client.post("/api/next-move/check-in?lang=en", json={"recovery": value})
    assert response.status_code == 200, response.json
    return response.json["recommendation"]


def complete(owner):
    plan = build_training_plan(recommendation_blueprint_id=uuid.uuid4().hex, facts=PROFILE)
    store.persist_delivered_training_plan(owner, delivered_plan_lineage(plan))
    first = completion_projection(plan, load_exercise_library(plan.exercise_library_version))["sessions"][0]
    payload = {"workout_id": uuid.uuid4().hex, "plan_id": plan.plan_id, "plan_version": plan.version,
               "session_id": first["session_id"], "completion_timestamp": datetime.now(timezone.utc).isoformat(),
               "execution_state": "completed", "exercises": []}
    for item in first["exercises"]:
        duration = item["prescription_type"] == "duration"
        payload["exercises"].append({"prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"], "prescription_type": item["prescription_type"],
            "completed_sets": item["prescribed_sets"], "actual_repetitions": None if duration else item["rep_min"],
            "completed_repetitions": None if duration else item["rep_min"],
            **({"actual_duration_seconds": item["duration_min_seconds"],
                "completed_duration_seconds": item["duration_min_seconds"]} if duration else {}),
            "execution_state": "completed", "completed_load": None})
    return payload


def test_flag_default_off_and_rollback_remove_ui_and_endpoints(monkeypatch):
    _, client = account()
    monkeypatch.delenv("APEX_NEXT_MOVE_ENABLED")
    assert next_move.enabled() is False
    assert "next_move.js" not in client.get("/app").get_data(as_text=True)
    for path in ("/api/next-move", "/api/next-move/approve", "/api/next-move/check-in"):
        response = client.get(path) if path == "/api/next-move" else client.post(path, json={})
        assert response.status_code == 404


def test_requires_real_auth_and_ignores_browser_account_and_profile():
    assert appmod.app.test_client().get("/api/next-move").status_code == 401
    owner, client = account(profile={})
    response = client.get("/api/next-move?lang=en&account_id=other&goal=strength")
    assert response.json["recommendation"]["kind"] == "profile"
    assert response.json["recommendation"]["known"]["goal"] is None
    assert str(owner) not in response.get_data(as_text=True)


def test_page_open_surfaces_one_action_without_model_or_writes():
    _, client = account()
    assert "next_move.js" in client.get("/app").get_data(as_text=True)
    statements = []
    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement.strip().split()[0].upper())
    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        result = recommendation(client)
        assert result["kind"] == "checkin"
        assert result == recommendation(client)
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE"}
    assert "score" not in json.dumps(result).lower()


@pytest.mark.parametrize("language", ("bg", "en"))
def test_missing_current_recovery_asks_one_question_not_profile_guess(language):
    _, client = account()
    result = recommendation(client, language)
    assert result["kind"] == "checkin"
    assert result["title"].count("?") == 1
    assert result["completed_at"] is None
    assert "readiness" not in json.dumps(result)


@pytest.mark.parametrize("age,source,confidence", [(25, "checkin", 1), (0, "inference", 1), (0, "message", .4), (-1, "checkin", 1)])
def test_expired_inferred_weak_and_future_state_do_not_become_verified(age, source, confidence):
    owner, client = account()
    now = datetime.now(timezone.utc)
    human_state.engine.apply("user:" + str(owner), [Reading("recovery", "high", confidence,
        source=source, observed_at=now - timedelta(hours=age))], now=now)
    assert recommendation(client)["kind"] == "checkin"


def test_explicit_checkin_reuses_hse_without_changing_profile_or_constraints():
    owner, client = account()
    store.add_account_training_constraints(owner, ("vertical_push",))
    before = store.get_profile(owner)
    result = checkin(client, "tired")
    assert result["kind"] == "recovery"
    assert result["constraints"] == ["vertical_push"]
    assert store.hs_get("user:" + str(owner), "recovery")["source"] == "checkin"
    assert store.get_profile(owner) == before
    assert store.list_account_training_constraints(owner) == ("vertical_push",)


def test_completion_ack_invalidates_prior_recommendation_and_recalculates():
    owner, client = account()
    prior = checkin(client)
    payload = complete(owner)
    saved = client.post("/api/workout", json={"session": {"completion": 100, "type": "training"}, "workout_completion": payload})
    assert saved.status_code == 200, saved.json
    after = recommendation(client)
    assert after["kind"] == "post_workout"
    assert after["completed_at"]
    assert after["decision_id"] != prior["decision_id"]
    assert recommendation(client)["decision_id"] == after["decision_id"]


def test_owner_bound_approval_revalidates_changed_constraints():
    owner, client = account()
    old = recommendation(client)
    store.add_account_training_constraints(owner, ("vertical_push",))
    stale = client.post("/api/next-move/approve?lang=en", json={"decision_id": old["decision_id"]})
    assert stale.status_code == 409
    _, other = account("next-move-other@example.invalid")
    assert other.post("/api/next-move/approve?lang=en", json={"decision_id": old["decision_id"]}).status_code == 409
    assert recommendation(other)["constraints"] == []


def test_wall_clock_confidence_decay_does_not_invalidate_unchanged_evidence():
    owner, _ = account()
    now = datetime.now(timezone.utc)
    next_move.record_checkin(owner, "fresh", now)
    training = store.get_my_training(owner)
    arguments = dict(owner=owner, profile=PROFILE, training=training, language="en", secret="test-only")
    first = next_move.recommend(**arguments, state=next_move.fresh_state(owner, now), now=now)
    later = now + timedelta(minutes=5)
    second = next_move.recommend(**arguments, state=next_move.fresh_state(owner, later), now=later)
    assert first["decision_id"] == second["decision_id"]


def test_checkin_persistence_failure_cannot_return_success(monkeypatch):
    _, client = account()
    monkeypatch.setattr(human_state.engine, "apply", lambda *_args, **_kwargs: {"applied": [], "kept": []})
    assert client.post("/api/next-move/check-in", json={"recovery": "fresh"}).status_code == 503


def test_unverified_adaptive_signal_does_not_become_a_claimed_self_report():
    owner, client = account()
    checkin(client)
    human_state.engine.apply("user:" + str(owner), [Reading("pain", "present", .4,
        source="inference", observed_at=datetime.now(timezone.utc))])
    assert recommendation(client)["kind"] != "recovery"


def test_safety_context_cannot_approve_training():
    _, client = account(profile={**PROFILE, "healthNotes": "chest pain today"})
    result = recommendation(client)
    assert result["kind"] == "safety"
    approved = client.post("/api/next-move/approve?lang=en", json={"decision_id": result["decision_id"]})
    assert approved.status_code == 200
    assert approved.json["workflow"] == "chat"
    assert "Do not prescribe" in approved.json["message"]
    assert "chest pain" not in json.dumps(result)


def test_read_failures_fail_closed_and_never_approve(monkeypatch):
    _, client = account()
    monkeypatch.setattr(store, "list_account_training_constraints", lambda *_: (_ for _ in ()).throw(RuntimeError()))
    assert client.get("/api/next-move").status_code == 503
    assert client.post("/api/next-move/approve", json={"decision_id": "forged"}).status_code == 503


def test_json_validation_origin_and_no_cross_account_checkin():
    owner, client = account()
    other, _ = account("second-next-move@example.invalid")
    assert client.post("/api/next-move/check-in", json={"recovery": "invented"}).status_code == 400
    assert client.post("/api/next-move/check-in", json={"recovery": "fresh"}, headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.post("/api/next-move/check-in", json={"recovery": "fresh", "user_id": str(other)}).status_code == 200
    assert store.hs_get_all("user:" + str(other)) == []
    assert store.hs_get_all("user:" + str(owner))


@pytest.mark.parametrize("brain_on", (False, True))
@pytest.mark.parametrize("language", ("bg", "en"))
def test_real_harder_workout_keeps_account_overhead_constraint(monkeypatch, brain_on, language):
    owner, client = account()
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("BRAIN_ENFORCE", "true" if brain_on else "false")
    store.add_account_training_constraints(owner, ("vertical_push",))
    checkin(client)
    def fake(**kwargs):
        if not kwargs.get("stream"):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='{"explanations": []}'), finish_reason=None)]),
                     SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")])])
    monkeypatch.setattr(appmod.client.chat.completions, "create", fake)
    messages = (("Направи ми тренировка за горна част.", "Направи тренировката по-трудна.") if language == "bg" else
                ("Create an upper-body workout.", "Make the workout harder."))
    for message in messages:
        response = client.post("/chat", json={"message": message, "lang": language, "conversation_id": "next-move-hard-upper-001"})
        events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]
        assert response.status_code == 200
        completion = next(item["training_completion"] for item in events if "training_completion" in item)
        library = load_exercise_library()
        for session in completion["sessions"]:
            for exercise in session["exercises"]:
                assert library.require(exercise["exercise_id"], exercise["exercise_version"]).movement_pattern.value != "vertical_push"
        assert events[-1] == {"done": True}
    assert store.list_account_training_constraints(owner) == ("vertical_push",)


def test_explicit_feedback_reuses_existing_ingestion_and_recalculates(monkeypatch):
    owner, client = account()
    checkin(client)
    monkeypatch.setenv("HSE_INGEST", "false")
    def fake(**kwargs):
        if not kwargs.get("stream"):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Let's discuss how you feel today."), finish_reason=None)]),
                     SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")])])
    monkeypatch.setattr(appmod.client.chat.completions, "create", fake)
    response = client.post("/chat", json={"message": "I am exhausted today. Help me think it through, no workout.",
                                         "lang": "en", "conversation_id": "next-move-feedback-001"})
    assert '"done": true' in response.get_data(as_text=True)
    assert store.hs_get("user:" + str(owner), "fatigue")["value"] == "high"
    assert recommendation(client)["kind"] == "recovery"


def test_fresh_checkin_reaches_existing_training_context_without_rewriting_profile(monkeypatch):
    owner, client = account()
    checkin(client, "tired")
    snapshots = []
    original = appmod.context_builder.build_context
    def capture(**kwargs):
        result = original(**kwargs)
        snapshots.append(result)
        return result
    monkeypatch.setattr(appmod.context_builder, "build_context", capture)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_: iter([
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Let's discuss recovery."), finish_reason=None)]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")])]))
    response = client.post("/chat", json={"message": "Help me discuss recovery, no workout.", "lang": "en"})
    response.get_data()
    assert snapshots and snapshots[0].profile["recoveryFeel"].value == "tired"
    assert store.get_profile(owner)["recoveryFeel"] == "fresh"
