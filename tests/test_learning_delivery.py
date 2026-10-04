"""Learning extraction must never gate authoritative chat delivery."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

from flask import has_app_context, has_request_context
import pytest
from sqlalchemy import event, update

import app as appmod
import db as store


@pytest.fixture
def runtime(monkeypatch):
    for flag in ("BRAIN_ENFORCE", "BRAIN_SHADOW", "PERSONA_MATCHER_SHADOW",
                 "EXPERT_CONSENSUS_SHADOW", "HSE_INGEST", "HSE_OBSERVATORY",
                 "INDIVIDUAL_MODEL_SHADOW", "INDIVIDUAL_MODEL_CONSUMER"):
        monkeypatch.setenv(flag, "false")
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.HumanLearningEngine, "extract_facts", lambda *_args: {})
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs:
                        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                            content=json.dumps({"explanations": ["Use controlled repetitions."]})))]))
    profile = {"goal": "strength", "level": "intermediate", "equipment": "gym",
               "age": "30", "height": "180", "weight": "80",
               "sleepQuality": "good", "stressLevel": "low", "recoveryFeel": "fresh"}
    uid = store.get_or_create_user("learning-delivery@example.com")
    store.save_profile(uid, profile)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    # Real detached threads, drained before the database fixture is reused.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-learning") as executor:
        monkeypatch.setattr(appmod, "_learning_worker_executor", lambda: executor)
        yield client, uid, profile


def _workout(client):
    response = client.post("/chat", json={
        "message": "\u041d\u0430\u043f\u0440\u0430\u0432\u0438 \u043c\u0438 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0430 \u0437\u0430 \u0434\u043d\u0435\u0441",
        "lang": "bg",
    })
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


def _capture_scheduling(monkeypatch):
    scheduled = []
    original = appmod._update_learning_engine

    def schedule(*args):
        future = original(*args)
        scheduled.append(future)
        return future

    monkeypatch.setattr(appmod, "_update_learning_engine", schedule)
    return scheduled


def test_workout_completion_and_done_precede_release_of_blocked_learning(runtime, monkeypatch):
    client, uid, profile = runtime
    started, release, completed = threading.Event(), threading.Event(), threading.Event()
    observations = []

    def blocked_learning(model, user_message, reply):
        observations.append((has_request_context(), has_app_context(),
                             len(store.list_conversation(uid, limit=10))))
        started.set()
        if not release.wait(30):
            raise TimeoutError("test worker was not released")
        model.preferences["duration"] = "short"
        completed.set()

    monkeypatch.setattr(appmod.HumanLearningEngine, "process_exchange", blocked_learning)
    scheduled = _capture_scheduling(monkeypatch)
    with ThreadPoolExecutor(max_workers=1) as requests:
        delivery = requests.submit(_workout, client)
        try:
            assert started.wait(10), "learning was not scheduled"
            events = delivery.result(timeout=10)
            text_index = next(i for i, item in enumerate(events) if item.get("t"))
            completion_index = next(i for i, item in enumerate(events) if "training_completion" in item)
            done_index = next(i for i, item in enumerate(events) if item.get("done"))
            assert text_index < completion_index < done_index == len(events) - 1
            assert "|" in events[text_index]["t"]
            assert events[completion_index]["training_completion"]["sessions"][0]["exercises"]
            # These barriers prove ordering, independently of extraction speed.
            assert not release.is_set()
            assert not completed.is_set()
            assert len(scheduled) == 1 and not scheduled[0].done()
            assert observations == [(False, False, 2)]
            newer = store.get_profile(uid)
            newer.update({"goal": "endurance", "healthRestrictions": ["Avoid overhead pressing"]})
            store.save_profile(uid, newer)
        finally:
            release.set()
        scheduled[0].result(timeout=10)
    assert completed.is_set()
    saved = store.get_profile(uid)
    assert saved["preferences"]["duration"] == "short"
    assert saved["goal"] == "endurance"
    assert saved["healthRestrictions"] == ["Avoid overhead pressing"]
    assert profile["goal"] == "strength" and "preferences" not in profile


def test_fast_learning_is_scheduled_and_persisted_once(runtime, monkeypatch):
    client, uid, _profile = runtime
    calls = []
    writes = []
    original_save = store.save_profile_learning

    def facts(*args):
        calls.append(args)
        return {"preferences": {"duration": "short"}}

    def save(*args):
        writes.append(args)
        return original_save(*args)

    monkeypatch.setattr(appmod.HumanLearningEngine, "extract_facts", facts)
    monkeypatch.setattr(store, "save_profile_learning", save)
    scheduled = _capture_scheduling(monkeypatch)
    events = _workout(client)
    assert events[-1] == {"done": True}
    assert len(scheduled) == 1
    scheduled[0].result(timeout=10)
    assert len(calls) == len(writes) == 1
    assert store.get_profile(uid)["confidence"]["preferences:duration"] == 0.35


@pytest.mark.parametrize("failure_stage", ["extraction", "persistence", "dispatch"])
def test_learning_failure_preserves_workout_and_done(runtime, monkeypatch, caplog, failure_stage):
    client, _uid, _profile = runtime
    scheduled = _capture_scheduling(monkeypatch)
    baseline = _workout(client)
    scheduled[0].result(timeout=10)

    def fail(*_args, **_kwargs):
        raise RuntimeError("private-learning-exception-content")

    if failure_stage == "extraction":
        monkeypatch.setattr(appmod.HumanLearningEngine, "process_exchange", fail)
    elif failure_stage == "persistence":
        monkeypatch.setattr(store, "save_profile_learning", fail)
    else:
        monkeypatch.setattr(appmod, "_learning_worker_executor", fail)
    result = _workout(client)
    if scheduled[-1] is not None:
        scheduled[-1].result(timeout=10)
    assert result[-1] == {"done": True}
    assert [item["t"] for item in result if "t" in item] == [item["t"] for item in baseline if "t" in item]
    assert [item["training_completion"] for item in result if "training_completion" in item] == [
        item["training_completion"] for item in baseline if "training_completion" in item]
    assert "private-learning-exception-content" not in json.dumps(result) + caplog.text
    assert "RuntimeError" in caplog.text


def test_learning_queue_saturation_never_waits_or_retries(runtime, monkeypatch):
    _client, uid, profile = runtime
    started, release = threading.Event(), threading.Event()
    calls = []

    def blocked(*_args):
        calls.append(True)
        started.set()
        if not release.wait(30):
            raise TimeoutError("test worker was not released")

    monkeypatch.setattr(appmod.HumanLearningEngine, "process_exchange", blocked)
    futures = []
    try:
        for _ in range(16):
            futures.append(appmod._update_learning_engine(uid, "message", "reply", profile))
        assert started.wait(10)
        assert all(future is not None for future in futures)
        assert appmod._update_learning_engine(uid, "overflow", "reply", profile) is None
        assert len(calls) == 1
    finally:
        release.set()
        for future in futures:
            if future is not None:
                future.result(timeout=10)
    assert len(calls) == 16


def test_anonymous_learning_uses_detached_profile_copy_without_persistence(runtime, monkeypatch):
    _client, _uid, profile = runtime
    original = deepcopy(profile)
    observations = []

    def learn(model, *_args):
        observations.append((has_request_context(), has_app_context()))
        model.preferences["duration"] = "short"

    monkeypatch.setattr(appmod.HumanLearningEngine, "process_exchange", learn)
    monkeypatch.setattr(store, "save_profile_learning", lambda *_args: pytest.fail("anonymous write"))
    appmod._update_learning_engine(None, "message", "reply", profile).result(timeout=10)
    assert observations == [(False, False)]
    assert profile == original


def test_stale_learning_does_not_overwrite_newer_learning(runtime):
    _client, uid, profile = runtime
    before = appmod.HumanModel(deepcopy(profile)).to_dict()
    after = deepcopy(before)
    after["preferences"]["duration"] = "short"
    newer = {**profile, "preferences": {"time_of_day": "evening"}}
    store.save_profile(uid, newer)
    assert store.save_profile_learning(uid, before, after) is False
    assert store.get_profile(uid) == newer


def test_concurrent_save_between_learning_read_and_write_wins(runtime):
    _client, uid, profile = runtime
    before = appmod.HumanModel(deepcopy(profile)).to_dict()
    after = deepcopy(before)
    after["preferences"]["duration"] = "short"
    newer = {**profile, "goal": "endurance"}
    inserted = []

    def before_update(connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("UPDATE profiles") and not inserted:
            inserted.append(True)
            connection.execute(update(store.profiles).where(
                store.profiles.c.user_id == store._as_uuid(uid)).values(data=newer))

    event.listen(store.engine, "before_cursor_execute", before_update)
    try:
        assert store.save_profile_learning(uid, before, after) is False
    finally:
        event.remove(store.engine, "before_cursor_execute", before_update)
    assert inserted == [True]
    assert store.get_profile(uid) == newer


def test_learning_cannot_write_non_learning_fields_or_recreate_deleted_profile(runtime):
    _client, uid, profile = runtime
    before = appmod.HumanModel(deepcopy(profile)).to_dict()
    with pytest.raises(ValueError):
        store.save_profile_learning(uid, before, {**before, "goal": "endurance"})
    after = deepcopy(before)
    after["preferences"]["duration"] = "short"
    with store.engine.begin() as connection:
        connection.execute(store.profiles.delete().where(store.profiles.c.user_id == store._as_uuid(uid)))
    assert store.save_profile_learning(uid, before, after) is False
    assert store.get_profile(uid) == {}
