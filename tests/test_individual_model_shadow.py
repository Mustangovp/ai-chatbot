"""Detached Individual Model shadow privacy and runtime guarantees."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import re

import pytest

import app as appmod
import db as store
import individual_model_projection as projection_module
import individual_model_shadow as shadow
from brain.types import (
    CapacityEnvelope,
    ConstraintSet,
    Decision,
    Intervention,
    RedFlag,
    S2State,
    Urgency,
    Verdict,
)
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
            "latest_authoritative_completed_session_evidence": True,
            "latest_authoritative_completed_session_freshness": "unknown",
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
    return IndividualModelCoachingProjectionV1(None, None, None, (), None, None, ())


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


def _login(client, email, profile=None):
    user_id = store.get_or_create_user(email)
    store.save_profile(user_id, profile or {
        "goal": "strength", "level": "beginner", "equipment": "home",
    })
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    return user_id


def _post(client):
    return client.post("/chat", json={
        "message": "How should I train today?",
        "lang": "en",
        "profile": {"goal": "strength", "level": "beginner", "equipment": "home"},
    })


def _events(response):
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


def _system_content(call):
    return "\n".join(
        message["content"] for message in call["messages"]
        if message.get("role") == "system"
    )


def _individual_model_addendum(call):
    marker = "[REDACTED INDIVIDUAL MODEL CONTEXT]"
    _before, found, remainder = _system_content(call).partition(marker)
    assert found == marker
    return marker + remainder.split("\n\n", 1)[0]


def _completion_evidence_snapshot(freshness="unknown"):
    return _snapshot(
        training={
            "plan_id": "private-plan-id",
            "latest_execution_id": "private-execution-id",
            "latest_session_id": "private-session-id",
            "latest_completion_id": "private-completion-id",
            "latest_authoritative_completed_session_evidence": True,
            "latest_authoritative_completed_session_occurred_at": datetime(
                2026, 9, 2, 10, 11, 12, tzinfo=timezone.utc),
            "latest_authoritative_completed_session_freshness": freshness,
        },
        trajectory=(),
        adherence="missed",
        human_state={"motivation": {"value": "private-hse-value"}},
    )


def _training_profile():
    return {
        "goal": "strength",
        "level": "intermediate",
        "equipment": "gym",
        "age": "30",
        "height": "180",
        "weight": "80",
        "recoveryFeel": "fresh",
    }


def _mock_structured_stream(monkeypatch):
    calls = []

    class Delta:
        content = "ok"

    class Chunk:
        choices = [type("Choice", (), {"delta": Delta()})()]

    class StructuredCompletion:
        choices = [type("Choice", (), {
            "message": type("Message", (), {"content": json.dumps({"explanations": []})})(),
        })()]

    def create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("response_format"):
            return StructuredCompletion()
        return iter([Chunk()])

    monkeypatch.setattr(appmod.client.chat.completions, "create", create)
    return calls


def _training_contract(events):
    completion = next(event["training_completion"] for event in events
                      if "training_completion" in event)
    return {
        "plan_id": completion["plan_id"],
        "plan_version": completion["plan_version"],
        "sessions": tuple(
            (session["session_id"], tuple(
                (exercise["prescription_id"], exercise["exercise_id"], exercise["exercise_version"],
                 exercise["prescribed_sets"], exercise["rep_min"], exercise["rep_max"],
                 exercise["rest_seconds"])
                for exercise in session["exercises"]
            ))
            for session in completion["sessions"]
        ),
        "recommendation_rationale": completion["recommendation_rationale"],
    }


def _brain_halt_decision():
    return Decision(
        verdict=Verdict.NOT_YET,
        intervention=Intervention("medical_followup", "readiness-boundary"),
        generate_training=False,
        halt=True,
        verdict_confidence=0.8,
        constraints=ConstraintSet(),
        envelope=CapacityEnvelope(0.6, 0.6, 0.6, True, 0.8),
        s2=S2State(
            readiness=0.6,
            readiness_conf=0.8,
            red_flags=[RedFlag(
                "readiness-boundary", Urgency.URGENT,
                "clinician_prompt", "readiness-boundary",
            )],
            halt=True,
        ),
        need_vector=[("training", 0.9)],
        decision_id="readiness-boundary",
        model=None,
    )


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


@pytest.mark.parametrize("consumer_value", (None, "false"))
def test_consumer_flag_off_skips_builder_and_preserves_chat_baseline(
        client, monkeypatch, consumer_value):
    llm_calls = _mock_stream(monkeypatch)
    _login(client, f"consumer-off-{consumer_value}@example.com")
    built = {"count": 0}

    def build(*_args):
        built["count"] += 1
        return _completion_evidence_snapshot()

    monkeypatch.setattr(
        appmod.individual_model_snapshot, "build_individual_model_snapshot", build)
    if consumer_value is not None:
        monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", consumer_value)

    events = _events(_post(client))

    assert events[-1] == {"done": True}
    assert built["count"] == 0
    assert len(llm_calls) == 1
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in _system_content(llm_calls[-1])


def test_consumer_renders_only_unknown_completion_freshness_through_chat(client, monkeypatch):
    llm_calls = _mock_stream(monkeypatch)
    _login(client, "consumer-freshness-unknown@example.com")
    monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
    monkeypatch.setattr(
        appmod.individual_model_snapshot,
        "build_individual_model_snapshot",
        lambda *_: _completion_evidence_snapshot(),
    )

    events = _events(_post(client))
    addendum = _individual_model_addendum(llm_calls[-1])

    assert events[-1] == {"done": True}
    assert "authoritative completed-session evidence freshness=unknown" in addendum
    assert "trajectory=" not in addendum
    assert "adherence" not in addendum.casefold()
    assert "readiness" not in addendum.casefold()
    assert "recovery" not in addendum.casefold()
    assert "fatigue" not in addendum.casefold()
    assert ("do not alter deterministic plans, progression, restrictions, safety, "
            "or nutrition authority" in addendum)
    for forbidden in (
        "2026-09-02", "10:11:12", "private-user-id", "private-plan-id",
        "private-execution-id", "private-session-id", "private-completion-id",
    ):
        assert forbidden not in addendum


@pytest.mark.parametrize("source_freshness", ("current", "stale", "unsupported-value"))
def test_consumer_downgrades_unsupported_completion_freshness_to_unknown(
        client, monkeypatch, source_freshness):
    llm_calls = _mock_stream(monkeypatch)
    _login(client, f"consumer-freshness-{source_freshness}@example.com")
    monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
    monkeypatch.setattr(
        appmod.individual_model_snapshot,
        "build_individual_model_snapshot",
        lambda *_: _completion_evidence_snapshot(source_freshness),
    )

    events = _events(_post(client))
    addendum = _individual_model_addendum(llm_calls[-1])

    assert events[-1] == {"done": True}
    assert "authoritative completed-session evidence freshness=unknown" in addendum
    assert f"freshness={source_freshness}" not in addendum
    for forbidden in ("recent", "recently", "current", "stale", "lately",
                      "today", "yesterday"):
        assert forbidden not in addendum.casefold()
    assert re.search(r"\bfresh\b", addendum, flags=re.IGNORECASE) is None


@pytest.mark.parametrize("attempted_freshness", ("current", "stale", "unsupported-value"))
def test_consumer_rejects_nonproduction_projection_freshness_before_llm(
        client, monkeypatch, attempted_freshness):
    llm_calls = _mock_stream(monkeypatch)
    _login(client, f"consumer-projection-{attempted_freshness}@example.com")
    monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
    monkeypatch.setattr(
        appmod.individual_model_snapshot,
        "build_individual_model_snapshot",
        lambda *_: _completion_evidence_snapshot(),
    )
    monkeypatch.setattr(
        appmod.individual_model_projection,
        "build_projection",
        lambda *_: IndividualModelCoachingProjectionV1(
            "strength", "beginner", "home", (), attempted_freshness, None, ()),
    )

    events = _events(_post(client))
    system_content = _system_content(llm_calls[-1])

    assert events[-1] == {"done": True}
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in system_content
    assert f"freshness={attempted_freshness}" not in system_content


@pytest.mark.parametrize("failure_point", ("snapshot", "projection", "render"))
def test_consumer_failures_are_isolated_from_chat_and_sse(
        client, monkeypatch, failure_point):
    llm_calls = _mock_stream(monkeypatch)
    _login(client, f"consumer-failure-{failure_point}@example.com")
    monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
    private_value = f"private-{failure_point}-failure"
    assert not shadow.shadow_enabled()

    def fail(*_args, **_kwargs):
        raise RuntimeError(private_value)

    if failure_point == "snapshot":
        monkeypatch.setattr(
            appmod.individual_model_snapshot, "build_individual_model_snapshot", fail)
    elif failure_point == "projection":
        monkeypatch.setattr(
            appmod.individual_model_snapshot,
            "build_individual_model_snapshot",
            lambda *_: _completion_evidence_snapshot(),
        )
        monkeypatch.setattr(appmod.individual_model_projection, "build_projection", fail)
    else:
        monkeypatch.setattr(
            appmod.individual_model_snapshot,
            "build_individual_model_snapshot",
            lambda *_: _completion_evidence_snapshot(),
        )
        monkeypatch.setattr(appmod.individual_model_projection, "render_prompt", fail)

    response = _post(client)
    events = _events(response)
    serialized_output = response.get_data(as_text=True)
    system_content = _system_content(llm_calls[-1])

    assert events[-1] == {"done": True}
    assert len(llm_calls) == 1
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in system_content
    assert private_value not in serialized_output
    assert private_value not in system_content


def test_consumer_requires_an_authenticated_account_and_redacts_persisted_identity(
        client, monkeypatch):
    llm_calls = _mock_stream(monkeypatch)
    monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
    build_calls = []
    original_build = appmod.individual_model_snapshot.build_individual_model_snapshot

    def build(user_id):
        build_calls.append(user_id)
        return original_build(user_id)

    monkeypatch.setattr(
        appmod.individual_model_snapshot, "build_individual_model_snapshot", build)

    anonymous_events = _events(_post(client))

    assert anonymous_events[-1] == {"done": True}
    assert build_calls == []
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in _system_content(llm_calls[-1])

    authenticated = appmod.app.test_client()
    user_id = _login(authenticated, "consumer-readiness-auth@example.com", _training_profile())
    store.add_account_training_constraints(user_id, ("vertical_push",))
    constraint_id = store.list_account_training_constraint_records(user_id)[0]["id"]

    authenticated_response = _post(authenticated)
    authenticated_events = _events(authenticated_response)
    addendum = _individual_model_addendum(llm_calls[-1])

    assert authenticated_events[-1] == {"done": True}
    assert build_calls == [user_id]
    assert "active movement exclusions=vertical_push" in addendum
    for private_value in (user_id, constraint_id, "consumer-readiness-auth@example.com"):
        assert str(private_value) not in addendum
        assert str(private_value) not in authenticated_response.get_data(as_text=True)
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in json.dumps(authenticated_events)


def test_consumer_preserves_deterministic_workout_and_persisted_constraint_authority(
        client, monkeypatch):
    llm_calls = _mock_structured_stream(monkeypatch)
    rendered_plans = []
    original_render = appmod.training_renderer.render_completion_projection

    def capture_plan(plan, *args, **kwargs):
        rendered_plans.append(appmod.serialize_conversation_plan(plan))
        return original_render(plan, *args, **kwargs)

    monkeypatch.setattr(appmod.training_renderer, "render_completion_projection", capture_plan)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.delenv("BRAIN_ENFORCE", raising=False)
    profile = _training_profile()

    def request(email, consumer_enabled):
        chat_client = appmod.app.test_client()
        user_id = _login(chat_client, email, profile)
        store.add_account_training_constraints(user_id, ("vertical_push",))
        if consumer_enabled:
            monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
        else:
            monkeypatch.delenv("INDIVIDUAL_MODEL_CONSUMER", raising=False)
        response = chat_client.post("/chat", json={
            "message": "Give me a harder upper-body workout.",
            "lang": "en",
            "conversation_id": f"consumer-readiness-{consumer_enabled}",
        })
        events = _events(response)
        return user_id, events, _system_content(llm_calls[-1]), rendered_plans[-1]

    off_user, off_events, off_prompt, off_plan = request(
        "consumer-workout-off@example.com", False)
    on_user, on_events, on_prompt, on_plan = request(
        "consumer-workout-on@example.com", True)

    off_contract = _training_contract(off_events)
    on_contract = _training_contract(on_events)
    assert off_events[-1] == on_events[-1] == {"done": True}
    assert on_contract == off_contract
    assert on_plan == off_plan
    assert store.list_account_training_constraints(off_user) == ("vertical_push",)
    assert store.list_account_training_constraints(on_user) == ("vertical_push",)
    for contract in (off_contract, on_contract):
        exercise_ids = {
            exercise[1]
            for _session_id, exercises in contract["sessions"]
            for exercise in exercises
        }
        assert "dumbbell.overhead_press" not in exercise_ids
        assert "dumbbell.seated_press" not in exercise_ids
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in off_prompt
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" in on_prompt
    assert on_prompt.index("[FIXED TRAINING PLAN]") < on_prompt.index(
        "[REDACTED INDIVIDUAL MODEL CONTEXT]")


def test_consumer_preserves_persisted_nutrition_targets_and_user_visible_output(
        client, monkeypatch):
    llm_calls = _mock_stream(monkeypatch)
    profile = _training_profile()
    plan = {
        "version": "nutrition-plan-v1",
        "targets": {
            "calories": 2200,
            "protein_g": 150,
            "carbs_g": 240,
            "fat_g": 70,
        },
    }

    def request(email, consumer_enabled):
        chat_client = appmod.app.test_client()
        user_id = _login(chat_client, email, profile)
        persisted_plan = {**plan, "id": f"nutrition-consumer-readiness-{consumer_enabled}"}
        store.save_nutrition_plan(user_id, persisted_plan)
        before = store.list_nutrition_plans(user_id)[0]["plan"]
        if consumer_enabled:
            monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
        else:
            monkeypatch.delenv("INDIVIDUAL_MODEL_CONSUMER", raising=False)
        response = chat_client.post("/chat", json={
            "message": "Give me one training cue.",
            "lang": "en",
        })
        events = _events(response)
        after = store.list_nutrition_plans(user_id)[0]["plan"]
        return events, before, after, _system_content(llm_calls[-1]), persisted_plan

    off_events, off_before, off_after, off_prompt, off_plan = request(
        "consumer-nutrition-off@example.com", False)
    on_events, on_before, on_after, on_prompt, on_plan = request(
        "consumer-nutrition-on@example.com", True)

    assert off_events == on_events
    assert off_events[-1] == {"done": True}
    assert off_before == off_after == off_plan
    assert on_before == on_after == on_plan
    assert off_after["version"] == on_after["version"] == "nutrition-plan-v1"
    assert off_after["targets"] == on_after["targets"] == plan["targets"]
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in off_prompt
    addendum = _individual_model_addendum(llm_calls[-1])
    assert "authoritative nutrition targets=calories:2200,carbs_g:240,fat_g:70,protein_g:150" in addendum
    assert on_plan["id"] not in addendum
    assert "REDACTED INDIVIDUAL MODEL CONTEXT" not in json.dumps(on_events)


def test_consumer_preserves_brain_halt_and_skips_controlled_reply_path(client, monkeypatch):
    llm_calls = _mock_stream(monkeypatch)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("BRAIN_ENFORCE", "true")
    monkeypatch.setattr(appmod.brain_cascade, "decide",
                        lambda *_args, **_kwargs: _brain_halt_decision())
    build_calls = []

    def build(*_args):
        build_calls.append(True)
        return _completion_evidence_snapshot()

    monkeypatch.setattr(
        appmod.individual_model_snapshot, "build_individual_model_snapshot", build)

    def request(email, consumer_enabled):
        chat_client = appmod.app.test_client()
        _login(chat_client, email, _training_profile())
        if consumer_enabled:
            monkeypatch.setenv("INDIVIDUAL_MODEL_CONSUMER", "true")
        else:
            monkeypatch.delenv("INDIVIDUAL_MODEL_CONSUMER", raising=False)
        return _events(chat_client.post("/chat", json={
            "message": "Build a workout.",
            "lang": "en",
        }))

    off_events = request("consumer-brain-off@example.com", False)
    on_events = request("consumer-brain-on@example.com", True)

    assert on_events == off_events
    assert on_events[-1] == {"done": True}
    assert not any("training_completion" in event for event in on_events)
    assert build_calls == []
    assert llm_calls == []


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
        "completed_session_evidence_present": 1,
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
        "private-goal", "beginner", "home", (), None, None, ())
    with pytest.raises(ValueError):
        projection_module.validate_projection(malformed)
