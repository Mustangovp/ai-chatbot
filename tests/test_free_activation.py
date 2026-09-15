"""Server-authoritative first-value activation contract tests."""
from __future__ import annotations

import concurrent.futures
import json
import uuid

import pytest
from sqlalchemy import func, select

import app as appmod
import db as store
import free_activation
from recommend import engine as recommendation_planning
from recommend.blueprint import WorkoutBlueprint, to_dict


class _Delta:
    def __init__(self, content):
        self.content = content


class _Chunk:
    def __init__(self, content):
        self.choices = [type("Choice", (), {"delta": _Delta(content)})()]


class _StructuredCompletion:
    def __init__(self, payload):
        message = type("Message", (), {"content": json.dumps(payload)})()
        self.choices = [type("Choice", (), {"message": message})()]


@pytest.fixture(autouse=True)
def _activation_defaults(monkeypatch):
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.delenv("RECOMMENDATION_ENGINE_ACTIVE", raising=False)
    monkeypatch.setenv("BRAIN_ENFORCE", "false")
    monkeypatch.delenv("CONVERSATION_COMPOSER_ACTIVE", raising=False)


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _events(response):
    return [
        json.loads(line[6:])
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]


def _profile(**extra):
    profile = {
        "goal": "strength",
        "equipment": "gym",
        "level": "intermediate",
        "age": "30",
        "height": "180",
        "weight": "80",
        "recoveryFeel": "fresh",
    }
    profile.update(extra)
    return profile


def _stub_chat(monkeypatch, *, stream_text="ok"):
    def fake_create(**kwargs):
        if kwargs.get("response_format"):
            return _StructuredCompletion({"explanations": []})

        def stream():
            yield _Chunk(stream_text)

        return stream()

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)


def _activation_events(events):
    return [event["activation"] for event in events if "activation" in event]


def _device_id(client):
    cookie = client.get_cookie(appmod.DEVICE_COOKIE)
    assert cookie is not None
    return cookie.value


def _qualifying_training(client, monkeypatch, *, headers=True):
    _stub_chat(monkeypatch)
    response = client.post(
        "/chat",
        headers={"X-APEX-Activation-Confirmation": "1"} if headers else {},
        json={"message": "Build a workout", "lang": "en", "profile": _profile()},
    )
    assert response.status_code == 200
    return _events(response)


def _workout_blueprint():
    return WorkoutBlueprint(
        goal="strength", difficulty="moderate", mobility_requirement="standard",
        joint_impact="moderate", balance_demand="low", equipment=["dumbbells"],
        session_minutes=35, exercise_families=["squat", "hinge"], contraindications=[],
        rotation_anchor="lower_body", meal_diversity=[], explanations=[],
    )


def test_activation_qualification_is_closed_to_resolved_delivered_value():
    qualifying = free_activation.qualify_delivered_value(
        activation_type="training",
        recommendation_outcome=recommendation_planning.RecommendationOutcome.RECOMMEND,
        profile_completeness=recommendation_planning.ProfileCompleteness.SUFFICIENT,
        structured_delivery=True,
        safety_controlled=False,
    )

    assert qualifying is not None
    assert qualifying.activation_type is free_activation.ActivationType.TRAINING
    for invalid in (
        {"recommendation_outcome": "clarify"},
        {"profile_completeness": "incomplete"},
        {"structured_delivery": False},
        {"safety_controlled": True},
        {"activation_type": "nutrition"},
    ):
        args = {
            "activation_type": "coaching",
            "recommendation_outcome": "recommend",
            "profile_completeness": "sufficient",
            "structured_delivery": True,
            "safety_controlled": False,
        }
        args.update(invalid)
        assert free_activation.qualify_delivered_value(**args) is None


def test_analytics_payload_is_minimal_and_never_carries_identity_or_content():
    qualification = free_activation.ActivationQualification(free_activation.ActivationType.COACHING)

    payload = free_activation.analytics_payload(
        qualification, authenticated=False, locale="en")

    assert payload == {
        "event": "apex_free_activation",
        "activation_type": "coaching",
        "authenticated": False,
        "locale": "en",
    }


def test_anonymous_ledger_reconciles_to_same_authenticated_identity_without_recouning():
    device_id = uuid.uuid4().hex
    user_id = store.get_or_create_user("activation-reconcile@example.com")

    anonymous = store.claim_free_activation(
        device_id=device_id, activation_type="training")
    authenticated = store.claim_free_activation(
        user_id=user_id, device_id=device_id, activation_type="coaching")
    record = store.get_free_activation(user_id=user_id, device_id=device_id)

    assert anonymous == {"created": True, "activation_type": "training"}
    assert authenticated == {"created": False}
    assert str(record["user_id"]) == user_id
    assert record["device_id"] == device_id
    assert record["activation_type"] == "training"


def test_authenticated_ledger_deduplicates_by_account_even_when_device_changes():
    user_id = store.get_or_create_user("activation-account@example.com")

    first = store.claim_free_activation(
        user_id=user_id, device_id=uuid.uuid4().hex, activation_type="training")
    second = store.claim_free_activation(
        user_id=user_id, device_id=uuid.uuid4().hex, activation_type="coaching")

    assert first["created"] is True
    assert second == {"created": False}
    assert store.get_free_activation(user_id=user_id)["activation_type"] == "training"


def test_concurrent_duplicate_claims_persist_exactly_one_first_activation():
    device_id = uuid.uuid4().hex

    def claim():
        return store.claim_free_activation(device_id=device_id, activation_type="training")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: claim(), range(8)))

    with store.engine.begin() as connection:
        count = connection.execute(
            select(func.count()).select_from(store.free_activations)
        ).scalar_one()
    assert sum(result.get("created") is True for result in results) == 1
    assert count == 1


def test_load_or_profile_only_never_activates(client):
    assert client.get("/app").status_code == 200
    device_id = _device_id(client)

    assert store.get_free_activation(device_id=device_id) is None
    user_id = store.get_or_create_user("activation-profile-only@example.com")
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))
    saved = client.put("/api/profile", json={"profile": _profile()})

    assert saved.status_code == 200
    assert store.get_free_activation(user_id=user_id, device_id=device_id) is None


def test_generic_or_failed_generation_never_activates(client, monkeypatch):
    _stub_chat(monkeypatch)
    generic = client.post(
        "/chat", headers={"X-APEX-Activation-Confirmation": "1"},
        json={"message": "hello", "lang": "en", "profile": _profile()},
    )
    device_id = _device_id(client)

    assert _activation_events(_events(generic)) == []
    assert store.get_free_activation(device_id=device_id) is None

    def fail_create(**_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(appmod.client.chat.completions, "create", fail_create)
    failed = client.post(
        "/chat", headers={"X-APEX-Activation-Confirmation": "1"},
        json={"message": "hello", "lang": "en", "profile": _profile()},
    )

    assert any(event.get("error") is True for event in _events(failed))
    assert store.get_free_activation(device_id=device_id) is None


def test_first_personalized_training_delivery_creates_one_anonymous_activation(client, monkeypatch):
    events = _qualifying_training(client, monkeypatch)
    activation_events = _activation_events(events)
    device_id = _device_id(client)
    record = store.get_free_activation(device_id=device_id)

    assert len(activation_events) == 1
    assert activation_events[0] == {
        "event": "apex_free_activation",
        "activation_type": "training",
        "authenticated": False,
        "locale": "en",
    }
    assert record["activation_type"] == "training"
    assert record["activated_at"] is not None
    assert any("training_completion" in event for event in events)

    replay = _qualifying_training(client, monkeypatch)
    assert _activation_events(replay) == []
    with store.engine.begin() as connection:
        assert connection.execute(
            select(func.count()).select_from(store.free_activations)
        ).scalar_one() == 1


def test_first_personalized_training_delivery_uses_authenticated_identity(client, monkeypatch):
    user_id = store.get_or_create_user("activation-authenticated@example.com")
    store.save_profile(user_id, _profile())
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))

    events = _qualifying_training(client, monkeypatch)
    activation_events = _activation_events(events)

    assert activation_events == [{
        "event": "apex_free_activation",
        "activation_type": "training",
        "authenticated": True,
        "locale": "en",
    }]
    assert store.get_free_activation(user_id=user_id)["activation_type"] == "training"


def test_structured_personalized_coaching_delivery_can_be_the_first_activation(client, monkeypatch):
    blueprint = _workout_blueprint()
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "false")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *_args, **_kwargs: blueprint)
    _stub_chat(monkeypatch, stream_text=json.dumps({
        "blueprint": to_dict(blueprint), "explanations": [],
    }))

    response = client.post(
        "/chat", headers={"X-APEX-Activation-Confirmation": "1"},
        json={"message": "Build a workout", "lang": "en", "profile": _profile()},
    )
    events = _events(response)

    assert _activation_events(events) == [{
        "event": "apex_free_activation",
        "activation_type": "coaching",
        "authenticated": False,
        "locale": "en",
    }]
    assert store.get_free_activation(device_id=_device_id(client))["activation_type"] == "coaching"


def test_medical_boundary_never_creates_an_activation(client, monkeypatch):
    monkeypatch.setattr(
        appmod.client.chat.completions, "create", lambda **_kwargs: pytest.fail("LLM ran"))

    response = client.post(
        "/chat", headers={"X-APEX-Activation-Confirmation": "1"},
        json={
            "message": "My chest feels tight and I feel dizzy. Build a workout.",
            "lang": "en", "profile": _profile(),
        },
    )

    assert any(event.get("medical_hold") is True for event in _events(response))
    assert store.get_free_activation(device_id=_device_id(client)) is None


def test_analytics_confirmation_failure_never_breaks_delivery_or_activation_truth(client, monkeypatch):
    _stub_chat(monkeypatch)

    def fail_analytics(*_args, **_kwargs):
        raise RuntimeError("analytics unavailable")

    monkeypatch.setattr(free_activation, "analytics_payload", fail_analytics)
    events = _qualifying_training(client, monkeypatch)

    assert events[-1] == {"done": True}
    assert _activation_events(events) == []
    assert store.get_free_activation(device_id=_device_id(client))["activation_type"] == "training"


def test_server_truth_is_persisted_without_a_browser_confirmation_request(client, monkeypatch):
    events = _qualifying_training(client, monkeypatch, headers=False)

    assert _activation_events(events) == []
    assert store.get_free_activation(device_id=_device_id(client))["activation_type"] == "training"
