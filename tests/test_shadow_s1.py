"""
Brain shadow remains non-authoritative and records only safe in-memory/log telemetry.
"""
import json
import time
import types
import app as app_module
import db as store
from sqlalchemy import select
from brain.runtime_assets import shadow_observability


def _mock_openai(monkeypatch, reply="Good work. Controlled tempo."):
    NS = types.SimpleNamespace
    monkeypatch.setattr(app_module, "client",
                        NS(chat=NS(completions=NS(
                            create=lambda *a, **k: [NS(choices=[NS(delta=NS(content=reply))])]))))


def _brain_rows():
    with store.engine.begin() as c:
        return c.execute(select(store.brain_decisions)).mappings().all()


def _trace(row):
    tr = row["trace"]
    return json.loads(tr) if isinstance(tr, str) else tr


def _wait_for_shadow_event():
    deadline = time.monotonic() + 2
    while shadow_observability.snapshot_for_internal_use()["total"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    return shadow_observability.snapshot_for_internal_use()


def test_shadow_off_writes_nothing(monkeypatch):
    monkeypatch.delenv("BRAIN_SHADOW", raising=False)
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={"message": "make me a workout", "lang": "en",
                                   "profile": {"healthNotes": "prior stroke, high blood pressure"}})
    assert r.status_code == 200
    r.get_data()
    assert len(_brain_rows()) == 0


def test_shadow_on_records_safe_telemetry_without_persisting_a_trace(monkeypatch):
    shadow_observability.reset_for_testing()
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={
        "message": "make me a workout", "lang": "en",
        "profile": {"age": 69, "level": "beginner", "activityLevel": "sedentary",
                    "healthNotes": "prior stroke, high blood pressure"}})
    assert r.status_code == 200
    r.get_data()

    telemetry = _wait_for_shadow_event()
    assert telemetry["components"]["brain"]["SUCCESS"] == 1
    assert len(_brain_rows()) == 0


def test_shadow_on_medical_like_input_remains_non_persistent(monkeypatch):
    shadow_observability.reset_for_testing()
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={
        "message": "i get a tight, heavy feeling in my chest going uphill — make me a workout",
        "lang": "en", "profile": {}})
    assert r.status_code == 200
    r.get_data()
    telemetry = _wait_for_shadow_event()
    assert telemetry["components"]["brain"]["SUCCESS"] == 1
    assert len(_brain_rows()) == 0


def test_shadow_on_anonymous_session_has_no_user_scoped_write(monkeypatch):
    shadow_observability.reset_for_testing()
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={"message": "workout please", "lang": "en",
                                   "profile": {"healthNotes": "osteoporosis"}})
    assert r.status_code == 200
    r.get_data()
    telemetry = _wait_for_shadow_event()
    assert telemetry["components"]["brain"]["SUCCESS"] == 1
    assert len(_brain_rows()) == 0
