"""Detached Individual Model shadow privacy and runtime guarantees."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json

import pytest

import app as appmod
import db as store
import individual_model_projection as projection_module
import individual_model_shadow as shadow
from individual_model_projection import IndividualModelCoachingProjectionV1
from individual_model_snapshot import IndividualModelSnapshotV1


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    shadow.reset_for_testing()
    monkeypatch.delenv(shadow.FLAG, raising=False)
    monkeypatch.delenv("INDIVIDUAL_MODEL_CONSUMER", raising=False)
    monkeypatch.delenv("CONVERSATION_COMPOSER_ACTIVE", raising=False)


def _snapshot(**changes):
    values = dict(
        schema_version="individual-model-snapshot-v1",
        user_id="private-user-id",
        profile={
            "goal": "strength",
            "level": "beginner",
            "equipment": "home",
            "healthNotes": "private-health-text",
            "preference": "private-free-text",
        },
        constraints=({
            "id": "private-constraint-id",
            "pattern": "vertical_push",
            "source": "private-diagnosis",
            "state": "active",
        },),
        training={
            "plan_id": "private-plan-id",
            "latest_session_id": "private-session-id",
            "latest_completion_id": "private-completion-id",
        },
        progression=(),
        trajectory=({
            "trajectory_state": "progressing",
            "completion_ids": ("private-completion-id",),
        },),
        adherence="unknown",
        human_state={"motivation": {"value": "private-hse-value"}},
        nutrition={
            "plan_id": "private-nutrition-id",
            "targets": {"calories": 2200, "protein_g": 150, "meal": "private-meal"},
        },
        generated_at=datetime.now(timezone.utc),
    )
    values.update(changes)
    return IndividualModelSnapshotV1(**values)


def _empty_projection():
    return IndividualModelCoachingProjectionV1(None, None, None, (), False, None, ())


def _mock_stream(monkeypatch):
    calls = []

    class Delta:
        content = "ok"

    class Chunk:
        choices = [type("Choice", (), {"delta": Delta()})()]

    def create(**kwargs):
        calls.append(kwargs)
        return iter([Chunk()])

    monkeypatch.setattr(appmod.client.chat.completions, "create", create)
    return calls


def _login(client, email):
    user_id = store.get_or_create_user(email)
    store.save_profile(user_id, {"goal": "strength", "level": "beginner", "equipment": "home"})
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))


def _post(client):
    return client.post("/chat", json={
        "message": "How should I train today?",
        "lang": "en",
        "profile": {"goal": "strength", "level": "beginner", "equipment": "home"},
    })


def _events(response):
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


def test_shadow_default_off_skips_builder_and_telemetry(client, monkeypatch):
    calls = _mock_stream(monkeypatch)
    _login(client, "shadow-off@example.com")
    built = {"count": 0}
    monkeypatch.setattr(
        appmod.individual_model_snapshot,
        "build_individual_model_snapshot",
        lambda *_: built.__setitem__("count", built["count"] + 1),
    )

    events = _events(_post(client))

    assert not shadow.shadow_enabled()
    assert events[-1] == {"done": True}
    assert built["count"] == 0
    assert len(calls) == 1
    assert shadow.snapshot_telemetry() == {field: 0 for field in shadow.COUNTERS}


def test_shadow_on_observes_redacted_presence_and_does_not_change_prompt(client, monkeypatch):
    llm_calls = _mock_stream(monkeypatch)
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setattr(
        appmod.individual_model_snapshot, "build_individual_model_snapshot", lambda *_: _snapshot())
    composer_calls = []
    original_compose = appmod.conversation_composer.compose

    def compose(*args, **kwargs):
        composer_calls.append(kwargs)
        return original_compose(*args, **kwargs)

    monkeypatch.setattr(appmod.conversation_composer, "compose", compose)

    _login(client, "shadow-baseline@example.com")
    off_events = _events(_post(client))
    off_messages = llm_calls[-1]["messages"]

    _login(client, "shadow-on@example.com")
    monkeypatch.setenv(shadow.FLAG, "true")
    on_events = _events(_post(client))
    on_messages = llm_calls[-1]["messages"]
    telemetry = shadow.snapshot_telemetry()

    assert on_events == off_events
    assert on_messages == off_messages
    assert len(composer_calls) == 2
    assert composer_calls[0] == composer_calls[1]
    assert all("individual" not in key and "shadow" not in key
               for call in composer_calls for key in call)
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in str(on_messages)
    assert telemetry == {
        "eligible": 1,
        "none": 0,
        "failed": 0,
        "goal_present": 1,
        "experience_present": 1,
        "equipment_present": 1,
        "constraint_present": 1,
        "recent_completion_present": 1,
        "trajectory_progressing": 1,
        "trajectory_stable": 0,
        "nutrition_targets_present": 1,
        "latency_max_ms": telemetry["latency_max_ms"],
    }
    assert 0 <= telemetry["latency_max_ms"] <= shadow.MAX_LATENCY_MS
    serialized = json.dumps(telemetry)
    for forbidden in (
        "strength", "beginner", "home", "vertical_push", "2200", "150",
        "private-user-id", "private-session-id", "private-completion-id",
        "private-health-text", "private-hse-value", "private-meal",
    ):
        assert forbidden not in serialized


def test_shadow_none_and_malformed_projection_fail_closed(monkeypatch, caplog):
    monkeypatch.setenv(shadow.FLAG, "true")
    shadow.observe_projection(_empty_projection(), latency_ms=1)
    shadow.observe_projection({"goal_context": "private-value"}, latency_ms=float("inf"))
    telemetry = shadow.snapshot_telemetry()

    assert telemetry["none"] == 1
    assert telemetry["failed"] == 1
    assert telemetry["eligible"] == 0
    assert telemetry["latency_max_ms"] == 1
    assert "ValueError" in caplog.text
    assert "private-value" not in caplog.text


def test_shadow_builder_failure_isolated_and_sse_done(client, monkeypatch, caplog):
    _mock_stream(monkeypatch)
    _login(client, "shadow-failure@example.com")
    monkeypatch.setenv(shadow.FLAG, "true")

    def fail(*_args):
        raise RuntimeError("private-health-and-id")

    monkeypatch.setattr(appmod.individual_model_snapshot, "build_individual_model_snapshot", fail)
    events = _events(_post(client))

    assert events[-1] == {"done": True}
    assert shadow.snapshot_telemetry()["failed"] == 1
    assert "RuntimeError" in caplog.text
    assert "private-health-and-id" not in caplog.text


@pytest.mark.parametrize(
    "shadow_on,consumer_on,builder_calls,shadow_eligible,prompt_present",
    (
        (False, False, 0, 0, False),
        (True, False, 1, 1, False),
        (False, True, 1, 0, True),
        (True, True, 1, 1, True),
    ),
)
def test_shadow_and_consumer_flags_are_independent_and_share_one_validated_build(
        client, monkeypatch, shadow_on, consumer_on, builder_calls, shadow_eligible,
        prompt_present):
    llm_calls = _mock_stream(monkeypatch)
    _login(client, f"flags-{shadow_on}-{consumer_on}@example.com")
    calls = {"count": 0}

    def build(*_args):
        calls["count"] += 1
        return _snapshot()

    monkeypatch.setattr(appmod.individual_model_snapshot, "build_individual_model_snapshot", build)
    monkeypatch.setenv(shadow.FLAG, str(shadow_on).lower())
    monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", str(consumer_on).lower())
    events = _events(_post(client))

    assert events[-1] == {"done": True}
    assert calls["count"] == builder_calls
    assert shadow.snapshot_telemetry()["eligible"] == shadow_eligible
    assert ("REDACTED INDIVIDUAL MODEL CONTEXT" in str(llm_calls[-1]["messages"])) is prompt_present


def test_shadow_module_has_no_delivery_persistence_or_identity_state():
    source = inspect.getsource(shadow).lower()
    for forbidden in (
        "import db", "flask", "openai", "composer", "prompt", "response",
        "user_id", "device_id", "plan_id", "session_id", "completion_id",
        "human_state", "coach_memory", "persona", "health", "medication",
    ):
        assert forbidden not in source
    assert set(shadow.snapshot_telemetry()) == set(shadow.COUNTERS)


def test_individual_model_shadow_admin_endpoint_is_hidden_and_aggregate_only(
        client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "operations-token")
    for headers in ({}, {"Authorization": "Bearer wrong-token"},
                    {"Authorization": "operations-token"}):
        response = client.get("/admin/individual-model-shadow/telemetry", headers=headers)
        assert response.status_code == 404
        assert response.get_json() == {"error": "not_found"}
    assert client.get(
        "/admin/individual-model-shadow/telemetry?token=operations-token").status_code == 404

    monkeypatch.setattr(shadow, "snapshot_telemetry", lambda: {
        **{field: 0 for field in shadow.COUNTERS},
        "eligible": 4,
        "private_value": "must-not-escape",
    })
    headers = {"Authorization": "Bearer operations-token"}
    first = client.get("/admin/individual-model-shadow/telemetry", headers=headers)
    second = client.get("/admin/individual-model-shadow/telemetry", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json()
    assert first.get_json()["eligible"] == 4
    assert set(first.get_json()) == set(shadow.COUNTERS)
    assert "private_value" not in first.get_data(as_text=True)
    assert first.headers["Cache-Control"] == "no-store"
    assert first.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert client.post("/admin/individual-model-shadow/telemetry", headers=headers).status_code == 405


def test_projection_validator_rejects_closed_schema_escape():
    malformed = IndividualModelCoachingProjectionV1(
        "private-goal", "beginner", "home", (), False, None, ())
    with pytest.raises(ValueError):
        projection_module.validate_projection(malformed)
