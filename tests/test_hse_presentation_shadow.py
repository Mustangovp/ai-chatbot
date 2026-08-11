"""Detached HSE PresentationProjectionV1 shadow-runtime guarantees."""
from __future__ import annotations

import json
import inspect

import app as appmod
import pytest
import db as store
from coaching import presentation_shadow as shadow
from coaching.presentation import PresentationProjectionV1


def _events(response):
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _mock_stream(monkeypatch, text="stable response"):
    class _Delta:
        content = text

    class _Chunk:
        choices = [type("Choice", (), {"delta": _Delta()})()]

    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return iter([_Chunk()])

    monkeypatch.setattr(appmod.client.chat.completions, "create", create)
    return calls


def _post(client):
    return client.post("/chat", json={
        "message": "How can I stay consistent?", "lang": "en",
        "profile": {"level": "intermediate"},
    })


def test_shadow_flag_off_is_a_complete_runtime_noop(client, monkeypatch):
    shadow.reset_for_testing()
    monkeypatch.delenv(shadow.FLAG, raising=False)
    _mock_stream(monkeypatch)
    called = {"builder": 0}
    monkeypatch.setattr(shadow, "build_presentation_projection",
                        lambda *_: called.__setitem__("builder", called["builder"] + 1))

    events = _events(_post(client))
    assert events[-1] == {"done": True}
    assert called["builder"] == 0
    assert shadow.snapshot_telemetry() == {
        "eligible": 0, "none": 0, "failed": 0, "tone_supportive": 0,
        "tone_reassuring": 0, "ack_brief": 0, "encouragement_gentle": 0,
        "encouragement_mastery": 0, "latency_max_ms": 0,
    }


def test_shadow_on_discards_projection_and_preserves_delivery(client, monkeypatch):
    shadow.reset_for_testing()
    llm_calls = _mock_stream(monkeypatch)
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.delenv(shadow.FLAG, raising=False)
    off_events = _events(_post(client))
    off_prompt = llm_calls[-1]["messages"]

    shadow.reset_for_testing()
    monkeypatch.setenv(shadow.FLAG, "true")
    calls = {"subject": None}
    projection = PresentationProjectionV1(tone="supportive", acknowledgement="brief",
                                          encouragement="gentle")
    monkeypatch.setattr(shadow, "build_presentation_projection",
                        lambda subject: calls.__setitem__("subject", subject) or projection)
    captured = {"projection": "not-called"}
    original_compose = appmod.conversation_composer.compose

    def compose(*args, **kwargs):
        captured["projection"] = kwargs.get("presentation_projection")
        return original_compose(*args, **kwargs)

    monkeypatch.setattr(appmod.conversation_composer, "compose", compose)
    on_events = _events(_post(client))

    assert on_events == off_events
    assert llm_calls[-1]["messages"] == off_prompt
    assert calls["subject"].startswith("device:")
    assert captured["projection"] is None
    assert store.hs_get_all(calls["subject"]) == []
    assert store.hse_event_count() == 0
    assert shadow.snapshot_telemetry() == {
        "eligible": 1, "none": 0, "failed": 0, "tone_supportive": 1,
        "tone_reassuring": 0, "ack_brief": 1, "encouragement_gentle": 1,
        "encouragement_mastery": 0, "latency_max_ms": shadow.snapshot_telemetry()["latency_max_ms"],
    }


def test_aggregate_counters_only_for_approved_projection_values(monkeypatch):
    shadow.reset_for_testing()
    monkeypatch.setenv(shadow.FLAG, "true")
    projections = iter((
        PresentationProjectionV1(tone="reassuring", encouragement="mastery"),
        PresentationProjectionV1(acknowledgement="brief", encouragement="gentle"),
        None,
    ))
    monkeypatch.setattr(shadow, "build_presentation_projection", lambda subject: next(projections))
    shadow.observe("device:not-retained")
    shadow.observe("device:not-retained")
    shadow.observe("device:not-retained")
    telemetry = shadow.snapshot_telemetry()
    assert telemetry == {
        "eligible": 2, "none": 1, "failed": 0, "tone_supportive": 0,
        "tone_reassuring": 1, "ack_brief": 1, "encouragement_gentle": 1,
        "encouragement_mastery": 1, "latency_max_ms": telemetry["latency_max_ms"],
    }
    assert set(telemetry) == {
        "eligible", "none", "failed", "tone_supportive", "tone_reassuring", "ack_brief",
        "encouragement_gentle", "encouragement_mastery", "latency_max_ms",
    }


def test_blocklisted_state_is_only_a_none_counter(monkeypatch):
    shadow.reset_for_testing()
    monkeypatch.setenv(shadow.FLAG, "true")
    monkeypatch.setattr(shadow, "build_presentation_projection", lambda subject: None)
    shadow.observe("device:never-stored")
    telemetry = shadow.snapshot_telemetry()
    assert telemetry["none"] == 1 and telemetry["eligible"] == 0
    assert all(telemetry[key] == 0 for key in (
        "tone_supportive", "tone_reassuring", "ack_brief",
        "encouragement_gentle", "encouragement_mastery"))


def test_shadow_failure_cannot_break_terminal_sse_or_store_request_data(client, monkeypatch):
    shadow.reset_for_testing()
    monkeypatch.setenv(shadow.FLAG, "true")
    _mock_stream(monkeypatch)

    def fail(subject):
        raise RuntimeError("private state detail")

    monkeypatch.setattr(shadow, "build_presentation_projection", fail)
    events = _events(_post(client))
    assert events[-1] == {"done": True}
    telemetry = shadow.snapshot_telemetry()
    assert telemetry["failed"] == 1
    assert "private" not in repr(telemetry).lower()


def test_runtime_hook_failure_isolated_from_chat_and_terminal_sse(client, monkeypatch):
    _mock_stream(monkeypatch)
    monkeypatch.setenv(shadow.FLAG, "true")

    def fail(*_args):
        raise RuntimeError("telemetry-private-detail")

    monkeypatch.setattr(appmod.hse_presentation_shadow, "observe", fail)
    events = _events(_post(client))
    assert events[-1] == {"done": True}


def test_shadow_has_no_delivery_or_persistence_dependencies():
    source = inspect.getsource(shadow)
    for forbidden in ("import db", "flask", "openai", "render", "composer", "sse"):
        assert forbidden not in source.lower()
