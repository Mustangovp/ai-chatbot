"""Privacy and lifecycle guarantees for the flag-gated Human State Engine."""
import datetime as dt
import json

import db as store
from human_state import engine, extractor, observatory
from human_state.schema import KEY_TTL


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _transition(key="fatigue", value="high"):
    return [{
        "key": key, "extracted_value": value, "confidence": 0.8,
        "ttl_seconds": KEY_TTL.get(key, 3600), "source": "message",
        "prev_value": None, "prev_confidence": None, "prev_effective": 0.0,
        "action": "insert", "final_value": value,
    }]


def test_audit_never_persists_raw_message_or_health_fragment():
    message = "My knee hurts after a difficult private medical appointment"
    observatory.capture("device:private", message, now=NOW)
    event = store.hse_recent_events(subject="device:private")[0]
    state = store.hs_get("device:private", "pain")
    assert event["message"] is None
    assert message not in str(event["transitions"])
    assert state["note"] is None
    assert "knee" not in str(event["transitions"])


def test_structured_history_remains_trajectory_compatible():
    for offset, value in ((0, "high"), (1, "moderate"), (2, "low")):
        store.hse_log_event("device:trend", _transition("fatigue", value), 1.0)
        with store.engine.begin() as c:
            c.execute(store.update(store.human_state_events).where(
                store.human_state_events.c.subject == "device:trend").values(
                created_at=NOW - dt.timedelta(days=2 - offset)))
    from human_state import trajectory
    result = trajectory.compute("device:trend", now=NOW)
    assert result["ok"] is True and result["sufficient"] is True


def test_cleanup_physically_removes_only_expired_state_and_30_day_event_history():
    store.hs_upsert("device:cleanup", "pain", "present", 0.8, "message",
                    NOW - dt.timedelta(hours=13), KEY_TTL["pain"], note="private")
    store.hs_upsert("device:cleanup", "fatigue", "high", 0.8, "message",
                    NOW - dt.timedelta(hours=1), KEY_TTL["fatigue"])
    old_event = store.hse_log_event("device:cleanup", _transition(), 1.0)
    fresh_event = store.hse_log_event("device:cleanup", _transition(), 1.0)
    with store.engine.begin() as c:
        c.execute(store.update(store.human_state_events).where(
            store.human_state_events.c.id == store._as_uuid(old_event)).values(
            created_at=NOW - dt.timedelta(days=31)))
        c.execute(store.update(store.human_state_events).where(
            store.human_state_events.c.id == store._as_uuid(fresh_event)).values(created_at=NOW))
    result = store.hse_cleanup_expired(now=NOW, subject="device:cleanup")
    assert result == {"states_deleted": 1, "events_deleted": 1}
    assert store.hs_get("device:cleanup", "pain") is None
    assert store.hs_get("device:cleanup", "fatigue") is not None
    assert [event["id"] for event in store.hse_recent_events(subject="device:cleanup")] == [fresh_event]


def test_user_purge_removes_all_hse_owned_records_and_never_touches_other_subjects():
    event_id = store.hse_log_event("user:one", _transition(), 1.0)
    store.hse_add_review(event_id, "fatigue", "correct", note="never persist")
    engine.apply("user:one", extractor.extract("I'm exhausted", now=NOW), now=NOW)
    store.hse_log_event("user:two", _transition("stress", "high"), 1.0)
    result = store.hse_purge_user("one")
    assert result == {"states_deleted": 1, "events_deleted": 1, "reviews_deleted": 1}
    assert store.hs_get_all("user:one") == []
    assert store.hse_recent_events(subject="user:one") == []
    assert store.hs_get_all("user:two") == []
    assert len(store.hse_recent_events(subject="user:two")) == 1


def test_subjects_are_isolated_and_device_data_is_never_merged_on_account_access():
    engine.apply("device:a", extractor.extract("I'm exhausted", now=NOW), now=NOW)
    engine.apply("user:a", extractor.extract("I slept 8 hours", now=NOW), now=NOW)
    engine.apply("user:b", extractor.extract("I'm stressed", now=NOW), now=NOW)
    assert store.hs_get_all("user:a")[0]["key"] == "sleep"
    assert store.hs_get_all("user:b")[0]["key"] == "stress"
    assert store.hs_get_all("device:a")[0]["key"] == "fatigue"
    assert store.hs_get_all("user:a") != store.hs_get_all("device:a")


def test_unscoped_observatory_returns_aggregate_only_but_scoped_inspection_works():
    event_id = store.hse_log_event("device:scoped", _transition(), 1.0)
    store.hse_add_review(event_id, "fatigue", "correct", note="raw review note")
    aggregate = observatory.report()
    scoped = observatory.report(subject="device:scoped")
    assert aggregate["events"] == [] and aggregate["timeline"] == []
    assert aggregate["metrics"]["tp"] == 1
    assert len(scoped["events"]) == 1 and scoped["events"][0]["message"] is None
    assert scoped["events"][0]["subject"] == "device:scoped"
    assert store.hse_recent_events() == []


def test_cleanup_failure_isolated_from_hse_apply(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private database detail")
    monkeypatch.setattr(store, "hs_upsert", fail)
    result = engine.apply("device:failure", extractor.extract("I'm exhausted", now=NOW), now=NOW)
    assert result == {"applied": [], "kept": [], "transitions": []}


def test_hse_persistence_failure_does_not_break_chat_or_terminal_sse(monkeypatch):
    import app as appmod

    class _Delta:
        content = "ok"

    class _Chunk:
        choices = [type("Choice", (), {"delta": _Delta()})()]

    def fail_ingest(*_args, **_kwargs):
        raise RuntimeError("sensitive database failure")

    monkeypatch.setenv("HSE_INGEST", "true")
    monkeypatch.delenv("HSE_AUDIT", raising=False)
    monkeypatch.setattr(appmod.human_state, "ingest", fail_ingest)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs: iter([_Chunk()]))
    appmod.app.config["TESTING"] = True
    response = appmod.app.test_client().post("/chat", json={
        "message": "What is a good way to stay consistent?", "lang": "en",
        "profile": {"level": "intermediate"},
    })
    events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
              if line.startswith("data: ")]
    assert response.status_code == 200
    assert events[-1] == {"done": True}
