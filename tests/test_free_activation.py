"""Server-authoritative first-value activation contract tests."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import uuid

import pytest
from sqlalchemy import create_engine, func, inspect, select, text, update

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


def _stub_chat(monkeypatch, *, explanations=("Keep the prescribed form controlled.",), stream_text="ok"):
    def fake_create(**kwargs):
        if kwargs.get("response_format"):
            return _StructuredCompletion({"explanations": list(explanations)})

        def stream():
            yield _Chunk(stream_text)

        return stream()

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)


def _activation_events(events):
    return [event["activation"] for event in events if "activation" in event]


def _candidate_events(events):
    return [event["activation_candidate"] for event in events if "activation_candidate" in event]


def _device_id(client):
    cookie = client.get_cookie(appmod.DEVICE_COOKIE)
    assert cookie is not None
    return cookie.value


def _activation_device_link(device_id):
    with store.engine.begin() as connection:
        row = connection.execute(select(store.free_activation_device_links).where(
            store.free_activation_device_links.c.device_id == device_id)).mappings().first()
    return dict(row) if row is not None else None


def _verify_login(client, user_id, device_id):
    client.set_cookie(appmod.DEVICE_COOKIE, device_id)
    token = store.create_login_token(user_id)
    response = client.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"] == "/app?auth=ok"
    return response


def _qualifying_training(client, monkeypatch, *, explanations=("Keep the prescribed form controlled.",)):
    _stub_chat(monkeypatch, explanations=explanations)
    response = client.post(
        "/chat",
        json={"message": "Build a workout", "lang": "en", "profile": _profile()},
    )
    assert response.status_code == 200
    return _events(response)


def _confirm(client, candidate):
    response = client.post("/api/free-activation/confirm", json={"candidate": candidate["token"]})
    assert response.status_code == 200
    return response.get_json()


def _workout_blueprint():
    return WorkoutBlueprint(
        goal="strength", difficulty="moderate", mobility_requirement="standard",
        joint_impact="moderate", balance_demand="low", equipment=["dumbbells"],
        session_minutes=35, exercise_families=["squat", "hinge"], contraindications=[],
        rotation_anchor="lower_body", meal_diversity=[], explanations=[],
    )


def test_activation_qualification_is_closed_to_normal_verified_delivery():
    qualifying = free_activation.qualify_server_eligibility(
        activation_type="training",
        recommendation_outcome=recommendation_planning.RecommendationOutcome.RECOMMEND,
        profile_completeness=recommendation_planning.ProfileCompleteness.SUFFICIENT,
        delivery_class=free_activation.DeliveryClass.NORMAL,
        safety_controlled=False,
        training_delivery_verified=True,
    )

    assert qualifying is not None
    assert qualifying.activation_type is free_activation.ActivationType.TRAINING
    for invalid in (
        {"recommendation_outcome": "clarify"},
        {"profile_completeness": "incomplete"},
        {"safety_controlled": True},
        {"activation_type": "nutrition"},
        {"delivery_class": free_activation.DeliveryClass.RENDER_REJECTED},
        {"delivery_class": free_activation.DeliveryClass.GENERATION_FALLBACK},
        {"delivery_class": free_activation.DeliveryClass.EXPLANATION_FALLBACK},
        {"training_delivery_verified": False},
    ):
        args = {
            "activation_type": "training",
            "recommendation_outcome": "recommend",
            "profile_completeness": "sufficient",
            "delivery_class": free_activation.DeliveryClass.NORMAL,
            "safety_controlled": False,
            "training_delivery_verified": True,
        }
        args.update(invalid)
        assert free_activation.qualify_server_eligibility(**args) is None

    assert free_activation.qualify_server_eligibility(
        activation_type="coaching", recommendation_outcome="recommend",
        profile_completeness="sufficient", delivery_class="normal_verified",
        safety_controlled=False, coaching_value_verified=False,
    ) is None


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


def test_existing_account_suppresses_anonymous_device_measurement_on_login():
    """A second device may not retain a separate acquisition delivery lease."""
    user_id = store.get_or_create_user("activation-suppress@example.com")
    account_device = uuid.uuid4().hex
    anonymous_device = uuid.uuid4().hex

    assert store.claim_free_activation(
        user_id=user_id, device_id=account_device, activation_type="training")["created"]
    account_lease = store.claim_free_activation_analytics_delivery(
        user_id=user_id, device_id=account_device)
    assert account_lease is not None
    assert store.acknowledge_free_activation_analytics_delivery(
        token=account_lease["token"], user_id=user_id, device_id=account_device)

    assert store.claim_free_activation(
        device_id=anonymous_device, activation_type="coaching")["created"]
    assert store.get_free_activation(user_id=user_id, device_id=anonymous_device)["user_id"]

    with store.engine.begin() as connection:
        duplicate = connection.execute(select(store.free_activations).where(
            store.free_activations.c.device_id == anonymous_device)).mappings().one()
    assert duplicate["user_id"] is None
    assert duplicate["analytics_state"] == "suppressed"
    assert store.claim_free_activation_analytics_delivery(
        user_id=user_id, device_id=anonymous_device) is None
    # Logging out on the same device cannot restart anonymous acquisition.
    assert store.claim_free_activation(
        device_id=anonymous_device, activation_type="training") == {"created": False}
    assert store.claim_free_activation_analytics_delivery(device_id=anonymous_device) is None


def test_account_bound_device_cannot_restart_anonymous_activation_after_logout():
    user_id = store.get_or_create_user("activation-logout@example.com")
    device_id = uuid.uuid4().hex

    assert store.claim_free_activation(
        user_id=user_id, device_id=device_id, activation_type="training")["created"]
    assert store.claim_free_activation(
        device_id=device_id, activation_type="coaching") == {"created": False}
    record = store.get_free_activation(device_id=device_id)
    assert str(record["user_id"]) == user_id


def test_auth_verify_durably_reconciles_anonymous_activation_before_session(client):
    user_id = store.get_or_create_user("activation-auth-transition@example.com")
    device_id = uuid.uuid4().hex

    assert store.claim_free_activation(
        device_id=device_id, activation_type="training")["created"]
    _verify_login(client, user_id, device_id)

    record = store.get_free_activation(user_id=user_id, device_id=device_id)
    link = _activation_device_link(device_id)
    assert str(record["user_id"]) == user_id
    assert link is not None and str(link["user_id"]) == user_id

    assert client.post("/auth/logout").get_json() == {"ok": True}
    assert store.claim_free_activation(
        device_id=device_id, activation_type="coaching") == {"created": False}
    assert store.issue_free_activation_candidate(
        device_id=device_id, activation_type="coaching", locale="en") is None
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None


def test_auth_verify_suppresses_second_anonymous_device_before_logout(client):
    user_id = store.get_or_create_user("activation-second-device-login@example.com")
    account_device = uuid.uuid4().hex
    duplicate_device = uuid.uuid4().hex

    assert store.claim_free_activation(
        user_id=user_id, device_id=account_device, activation_type="training")["created"]
    assert store.claim_free_activation(
        device_id=duplicate_device, activation_type="coaching")["created"]

    _verify_login(client, user_id, duplicate_device)
    with store.engine.begin() as connection:
        duplicate = connection.execute(select(store.free_activations).where(
            store.free_activations.c.device_id == duplicate_device)).mappings().one()
    link = _activation_device_link(duplicate_device)
    assert duplicate["user_id"] is None
    assert duplicate["analytics_state"] == "suppressed"
    assert link is not None and str(link["user_id"]) == user_id

    assert client.post("/auth/logout").get_json() == {"ok": True}
    assert store.claim_free_activation(
        device_id=duplicate_device, activation_type="training") == {"created": False}
    assert store.claim_free_activation_analytics_delivery(device_id=duplicate_device) is None


def test_auth_verify_marks_new_device_for_an_already_activated_account(client):
    user_id = store.get_or_create_user("activation-new-device-login@example.com")
    activated_device = uuid.uuid4().hex
    new_device = uuid.uuid4().hex

    assert store.claim_free_activation(
        user_id=user_id, device_id=activated_device, activation_type="training")["created"]
    _verify_login(client, user_id, new_device)

    link = _activation_device_link(new_device)
    assert link is not None and str(link["user_id"]) == user_id
    assert client.post("/auth/logout").get_json() == {"ok": True}
    assert store.claim_free_activation(
        device_id=new_device, activation_type="coaching") == {"created": False}
    assert store.issue_free_activation_candidate(
        device_id=new_device, activation_type="coaching", locale="en") is None


def test_auth_verify_never_cross_links_a_device_between_accounts(client):
    first_user = store.get_or_create_user("activation-device-account-a@example.com")
    second_user = store.get_or_create_user("activation-device-account-b@example.com")
    device_id = uuid.uuid4().hex

    assert store.claim_free_activation(
        user_id=first_user, device_id=device_id, activation_type="training")["created"]
    _verify_login(client, first_user, device_id)
    _verify_login(client, second_user, device_id)

    link = _activation_device_link(device_id)
    assert link is not None and str(link["user_id"]) == first_user
    second = store.claim_free_activation(
        user_id=second_user, device_id=device_id, activation_type="coaching")
    assert second["created"] is True
    second_record = store.get_free_activation(user_id=second_user, device_id=device_id)
    assert second_record["device_id"] is None
    assert str(_activation_device_link(device_id)["user_id"]) == first_user


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
        "/chat",
        json={"message": "hello", "lang": "en", "profile": _profile()},
    )
    device_id = _device_id(client)

    assert _activation_events(_events(generic)) == []
    assert store.get_free_activation(device_id=device_id) is None

    def fail_create(**_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(appmod.client.chat.completions, "create", fail_create)
    failed = client.post(
        "/chat",
        json={"message": "hello", "lang": "en", "profile": _profile()},
    )

    assert any(event.get("error") is True for event in _events(failed))
    assert store.get_free_activation(device_id=device_id) is None


def test_first_personalized_training_requires_browser_presentation_confirmation(client, monkeypatch):
    events = _qualifying_training(client, monkeypatch)
    candidates = _candidate_events(events)
    device_id = _device_id(client)

    assert len(candidates) == 1
    assert candidates[0]["activation_type"] == "training"
    assert _activation_events(events) == []
    assert store.get_free_activation(device_id=device_id) is None
    assert _confirm(client, candidates[0]) == {"ok": True}
    record = store.get_free_activation(device_id=device_id)
    assert record["activation_type"] == "training"
    assert record["activated_at"] is not None
    assert record["analytics_state"] == "pending"
    assert any("training_completion" in event for event in events)

    replay = _qualifying_training(client, monkeypatch)
    replay_candidate = _candidate_events(replay)[0]
    assert _confirm(client, replay_candidate) == {"ok": True}
    with store.engine.begin() as connection:
        assert connection.execute(
            select(func.count()).select_from(store.free_activations)
        ).scalar_one() == 1


def test_first_personalized_training_delivery_uses_authenticated_identity(client, monkeypatch):
    user_id = store.get_or_create_user("activation-authenticated@example.com")
    store.save_profile(user_id, _profile())
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(user_id))

    events = _qualifying_training(client, monkeypatch)
    candidates = _candidate_events(events)

    assert len(candidates) == 1
    assert _confirm(client, candidates[0]) == {"ok": True}
    assert store.get_free_activation(user_id=user_id)["activation_type"] == "training"


def test_structured_personalized_coaching_delivery_can_be_the_first_activation(client, monkeypatch):
    blueprint = _workout_blueprint()
    blueprint = WorkoutBlueprint(
        goal=blueprint.goal, difficulty=blueprint.difficulty,
        mobility_requirement=blueprint.mobility_requirement,
        joint_impact=blueprint.joint_impact, balance_demand=blueprint.balance_demand,
        equipment=blueprint.equipment, session_minutes=blueprint.session_minutes,
        exercise_families=blueprint.exercise_families,
        contraindications=blueprint.contraindications,
        rotation_anchor=blueprint.rotation_anchor, meal_diversity=blueprint.meal_diversity,
        explanations=[("Use dumbbells", "They match your equipment.")],
    )
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "false")
    monkeypatch.setenv("RECOMMENDATION_ENGINE_ACTIVE", "true")
    monkeypatch.setattr(appmod.recommendation_architect, "design", lambda *_args, **_kwargs: blueprint)
    _stub_chat(monkeypatch, stream_text=json.dumps({
        "blueprint": to_dict(blueprint), "explanations": to_dict(blueprint)["explanations"],
    }))

    response = client.post(
        "/chat",
        json={"message": "Build a workout", "lang": "en", "profile": _profile()},
    )
    events = _events(response)

    candidates = _candidate_events(events)
    assert len(candidates) == 1
    assert candidates[0]["activation_type"] == "coaching"
    assert _confirm(client, candidates[0]) == {"ok": True}
    assert store.get_free_activation(device_id=_device_id(client))["activation_type"] == "coaching"


def test_medical_boundary_never_creates_an_activation(client, monkeypatch):
    monkeypatch.setattr(
        appmod.client.chat.completions, "create", lambda **_kwargs: pytest.fail("LLM ran"))

    response = client.post(
        "/chat",
        json={
            "message": "My chest feels tight and I feel dizzy. Build a workout.",
            "lang": "en", "profile": _profile(),
        },
    )

    assert any(event.get("medical_hold") is True for event in _events(response))
    assert store.get_free_activation(device_id=_device_id(client)) is None


def test_analytics_delivery_failure_never_breaks_product_activation_truth(client, monkeypatch):
    _stub_chat(monkeypatch)

    def fail_analytics(*_args, **_kwargs):
        raise RuntimeError("analytics unavailable")

    monkeypatch.setattr(free_activation, "analytics_payload", fail_analytics)
    events = _qualifying_training(client, monkeypatch)
    candidate = _candidate_events(events)[0]

    assert events[-1] == {"done": True}
    assert _activation_events(events) == []
    assert _confirm(client, candidate) == {"ok": True}
    delivery = client.post("/api/free-activation/delivery", json={})
    assert delivery.get_json() == {"delivery": None}
    assert store.get_free_activation(device_id=_device_id(client))["analytics_state"] == "pending"


def test_server_eligibility_without_browser_confirmation_is_not_product_truth(client, monkeypatch):
    events = _qualifying_training(client, monkeypatch)

    assert _activation_events(events) == []
    assert len(_candidate_events(events)) == 1
    assert store.get_free_activation(device_id=_device_id(client)) is None


def test_owner_marker_excludes_candidate_confirmation(client, monkeypatch):
    candidate = _candidate_events(_qualifying_training(client, monkeypatch))[0]
    client.set_cookie("apexOwner", "true")

    assert _confirm(client, candidate) == {"ok": False}
    assert store.get_free_activation(device_id=_device_id(client)) is None


def test_cross_account_candidate_and_expired_candidate_fail_closed(client, monkeypatch):
    first = store.get_or_create_user("activation-first@example.com")
    second = store.get_or_create_user("activation-second@example.com")
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(first))
    candidate = _candidate_events(_qualifying_training(client, monkeypatch))[0]

    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(second))
    assert _confirm(client, candidate) == {"ok": False}
    with store.engine.begin() as connection:
        connection.execute(update(store.free_activation_candidates).where(
            store.free_activation_candidates.c.token_hash == store._hash(candidate["token"])
        ).values(expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)))
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(first))
    assert _confirm(client, candidate) == {"ok": False}
    assert store.get_free_activation(user_id=first) is None


def test_account_device_reconciliation_never_cross_links_or_recounts():
    device_id = uuid.uuid4().hex
    first = store.get_or_create_user("activation-device-first@example.com")
    second = store.get_or_create_user("activation-device-second@example.com")

    assert store.claim_free_activation(user_id=first, device_id=device_id, activation_type="training")["created"]
    assert store.claim_free_activation(user_id=second, device_id=device_id, activation_type="coaching")["created"]
    assert store.claim_free_activation(device_id=device_id, activation_type="coaching") == {"created": False}
    first_record = store.get_free_activation(user_id=first)
    second_record = store.get_free_activation(user_id=second)
    assert first_record["device_id"] == device_id
    assert second_record["device_id"] is None


def test_concurrent_candidate_confirmations_create_one_activation_record():
    device_id = uuid.uuid4().hex
    candidates = [store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en") for _ in range(8)]

    def confirm(candidate):
        return store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(confirm, candidates))
    with store.engine.begin() as connection:
        count = connection.execute(select(func.count()).select_from(store.free_activations)).scalar_one()

    assert sum(result.get("created") is True for result in results) == 1
    assert count == 1


def test_one_candidate_token_confirms_exactly_once_under_concurrency():
    device_id = uuid.uuid4().hex
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")

    def confirm_once(_index):
        return store.confirm_free_activation_candidate(
            token=candidate["token"], device_id=device_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(confirm_once, range(8)))

    assert sum(result.get("confirmed") is True for result in results) == 1
    assert store.confirm_free_activation_candidate(
        token=candidate["token"], device_id=device_id) == {"confirmed": False}
    with store.engine.begin() as connection:
        count = connection.execute(
            select(func.count()).select_from(store.free_activations)).scalar_one()
    assert count == 1


def test_forged_candidate_token_is_never_confirmation_authority():
    device_id = uuid.uuid4().hex
    assert store.confirm_free_activation_candidate(
        token="f" * 32, device_id=device_id) == {"confirmed": False}
    assert store.get_free_activation(device_id=device_id) is None


def test_analytics_delivery_uses_one_lease_and_callback_checkpoint_for_dedupe():
    device_id = uuid.uuid4().hex
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]

    first = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert first and first["activation_type"] == "training"
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None
    assert store.release_free_activation_analytics_delivery(token=first["token"], device_id=device_id) is True
    retry = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert retry and retry["token"] != first["token"]
    assert store.acknowledge_free_activation_analytics_delivery(token=retry["token"], device_id=device_id) is True
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_state"] == "callback_completed"
    assert record["analytics_delivered_at"] is not None


def test_analytics_delivery_retry_and_lease_recovery_are_bounded():
    device_id = uuid.uuid4().hex
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]

    first = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert first is not None
    # A browser close before callback leaves a lease that may be reclaimed once.
    with store.engine.begin() as connection:
        connection.execute(update(store.free_activations).where(
            store.free_activations.c.device_id == device_id).values(
            analytics_lease_expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)))
    second = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert second is not None and second["token"] != first["token"]
    assert store.release_free_activation_analytics_delivery(
        token=second["token"], device_id=device_id) is True
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_state"] == "exhausted"
    assert record["analytics_attempt_count"] == store._FREE_ACTIVATION_MAX_DELIVERY_ATTEMPTS
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None


def test_concurrent_analytics_delivery_claims_hold_one_active_lease():
    device_id = uuid.uuid4().hex
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        leases = list(pool.map(
            lambda _index: store.claim_free_activation_analytics_delivery(device_id=device_id), range(8)))

    assert sum(lease is not None for lease in leases) == 1


def test_concurrent_first_delivery_lease_is_atomic_and_sets_one_true_t0(monkeypatch):
    device_id = uuid.uuid4().hex
    t0 = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(store, "_now", lambda: t0)
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(
            lambda _index: store.claim_free_activation_analytics_delivery(device_id=device_id), range(2)))

    assert sum(lease is not None for lease in leases) == 1
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_attempt_count"] == 1
    assert store._activation_timestamp(record["analytics_first_attempt_at"]) == t0


def test_concurrent_expired_retry_lease_is_atomic_and_cannot_reset_t0(monkeypatch):
    device_id = uuid.uuid4().hex
    t0 = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    now = [t0]
    monkeypatch.setattr(store, "_now", lambda: now[0])
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]
    first = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert first is not None

    now[0] = t0 + dt.timedelta(minutes=1)
    with store.engine.begin() as connection:
        connection.execute(update(store.free_activations).where(
            store.free_activations.c.device_id == device_id).values(
            analytics_lease_expires_at=now[0] - dt.timedelta(seconds=1)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(
            lambda _index: store.claim_free_activation_analytics_delivery(device_id=device_id), range(2)))

    assert sum(lease is not None for lease in leases) == 1
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_attempt_count"] == 2
    assert store._activation_timestamp(record["analytics_first_attempt_at"]) == t0


def test_delivery_retry_budget_blocks_a_third_lease(monkeypatch):
    device_id = uuid.uuid4().hex
    t0 = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(store, "_now", lambda: t0)
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]

    first = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert first is not None
    assert store.release_free_activation_analytics_delivery(token=first["token"], device_id=device_id)
    second = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert second is not None
    assert store.release_free_activation_analytics_delivery(token=second["token"], device_id=device_id)

    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_attempt_count"] == store._FREE_ACTIVATION_MAX_DELIVERY_ATTEMPTS
    assert record["analytics_state"] == "exhausted"
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None


def test_delivery_retry_window_cannot_be_reopened_after_true_t0(monkeypatch):
    device_id = uuid.uuid4().hex
    t0 = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    now = [t0]
    monkeypatch.setattr(store, "_now", lambda: now[0])
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]
    first = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert first is not None
    assert store.release_free_activation_analytics_delivery(token=first["token"], device_id=device_id)

    now[0] = t0 + dt.timedelta(minutes=16)
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_state"] == "exhausted"
    assert record["analytics_attempt_count"] == 1
    assert store._activation_timestamp(record["analytics_first_attempt_at"]) == t0


def test_acknowledgement_release_race_cannot_exceed_delivery_budget(monkeypatch):
    device_id = uuid.uuid4().hex
    t0 = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(store, "_now", lambda: t0)
    candidate = store.issue_free_activation_candidate(
        device_id=device_id, activation_type="training", locale="en")
    assert store.confirm_free_activation_candidate(token=candidate["token"], device_id=device_id)["created"]
    first = store.claim_free_activation_analytics_delivery(device_id=device_id)
    assert first is not None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda fn: fn(), (
            lambda: store.acknowledge_free_activation_analytics_delivery(
                token=first["token"], device_id=device_id),
            lambda: store.release_free_activation_analytics_delivery(
                token=first["token"], device_id=device_id),
        )))

    assert sum(bool(outcome) for outcome in outcomes) == 1
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_attempt_count"] == 1
    if record["analytics_state"] == "pending":
        second = store.claim_free_activation_analytics_delivery(device_id=device_id)
        assert second is not None
        assert store.release_free_activation_analytics_delivery(
            token=second["token"], device_id=device_id)
    assert store.claim_free_activation_analytics_delivery(device_id=device_id) is None
    record = store.get_free_activation(device_id=device_id)
    assert record["analytics_attempt_count"] <= store._FREE_ACTIVATION_MAX_DELIVERY_ATTEMPTS


def test_public_templates_are_identical_for_browser_googlebot_and_adsbot(client):
    for path in ("/", "/en", "/app"):
        browser = client.get(path, headers={"User-Agent": "APEX Browser"})
        adsbot = client.get(path, headers={"User-Agent": "AdsBot-Google"})
        googlebot = client.get(path, headers={"User-Agent": "Googlebot"})
        assert browser.status_code == adsbot.status_code == googlebot.status_code == 200
        assert browser.get_data() == adsbot.get_data() == googlebot.get_data()


def _legacy_activation_engine(monkeypatch, *, user_index_sql, omit_activation_type=False):
    """Build a v22/v23-marked SQLite ledger with a controllable index defect."""
    engine = create_engine("sqlite://", future=True)
    activation_type = "" if omit_activation_type else ", activation_type VARCHAR(16) NOT NULL"
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at DATETIME)"))
        connection.execute(text(
            "CREATE TABLE free_activations (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), "
            f"device_id VARCHAR(32){activation_type}, activated_at DATETIME NOT NULL)"))
        connection.execute(text(
            "CREATE TABLE free_activation_candidates (id VARCHAR(36) PRIMARY KEY, "
            "token_hash VARCHAR(64) NOT NULL, user_id VARCHAR(36), device_id VARCHAR(32), "
            "activation_type VARCHAR(16) NOT NULL, locale VARCHAR(2) NOT NULL, "
            "expires_at DATETIME NOT NULL, confirmed_at DATETIME, created_at DATETIME NOT NULL)"))
        connection.execute(text(user_index_sql))
        connection.execute(text(
            "CREATE UNIQUE INDEX ix_free_activation_device_unique ON free_activations (device_id)"))
        connection.execute(text(
            "CREATE UNIQUE INDEX ix_free_activation_candidate_token_unique "
            "ON free_activation_candidates (token_hash)"))
        for version in range(1, 24):
            connection.execute(text("INSERT INTO schema_version (version) VALUES (:version)"),
                               {"version": version})
    monkeypatch.setattr(store, "engine", engine)
    return engine


def _index(engine, table_name, name):
    return next(index for index in inspect(engine).get_indexes(table_name)
                if index["name"] == name)


def _assert_exact_unique_index(engine, table_name, name, column):
    index = _index(engine, table_name, name)
    assert bool(index["unique"])
    assert index["column_names"] == [column]
    assert not any(
        key.endswith("_where") and value is not None
        for key, value in (index.get("dialect_options") or {}).items()
    )


def test_fresh_database_applies_real_activation_migration(monkeypatch):
    engine = create_engine("sqlite://", future=True)
    monkeypatch.setattr(store, "engine", engine)

    store.run_migrations()
    names = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        versions = {row[0] for row in connection.execute(select(store.schema_version.c.version))}

    assert {
        "free_activations", "free_activation_candidates", "free_activation_device_links",
    } <= names
    assert {22, 23, 24, 25} <= versions


def test_legacy_activation_table_is_upgraded_with_required_ledger_columns(monkeypatch):
    engine = _legacy_activation_engine(
        monkeypatch,
        user_index_sql=(
            "CREATE UNIQUE INDEX ix_free_activation_user_unique ON free_activations (user_id)"),
    )

    store.run_migrations()
    columns = {column["name"] for column in inspect(engine).get_columns("free_activations")}

    assert {
        "locale", "analytics_state", "analytics_token_hash", "analytics_lease_expires_at",
        "analytics_attempt_count", "analytics_first_attempt_at", "analytics_delivered_at",
    } <= columns
    _assert_exact_unique_index(
        engine, "free_activations", "ix_free_activation_user_unique", "user_id")


@pytest.mark.parametrize("user_index_sql", (
    "CREATE INDEX ix_free_activation_user_unique ON free_activations (user_id)",
    "CREATE UNIQUE INDEX ix_free_activation_user_unique ON free_activations (device_id)",
    "CREATE UNIQUE INDEX ix_free_activation_user_unique ON free_activations (user_id) WHERE user_id IS NOT NULL",
))
def test_marked_v22_schema_repairs_nonunique_or_wrong_column_identity_index(monkeypatch, user_index_sql):
    engine = _legacy_activation_engine(monkeypatch, user_index_sql=user_index_sql)

    store.run_migrations()

    _assert_exact_unique_index(
        engine, "free_activations", "ix_free_activation_user_unique", "user_id")
    with engine.begin() as connection:
        versions = {row[0] for row in connection.execute(select(store.schema_version.c.version))}
    assert 24 in versions


def test_marked_v22_partial_schema_fails_before_v24_is_recorded(monkeypatch):
    engine = _legacy_activation_engine(
        monkeypatch,
        user_index_sql=(
            "CREATE UNIQUE INDEX ix_free_activation_user_unique ON free_activations (user_id)"),
        omit_activation_type=True,
    )

    with pytest.raises(RuntimeError, match="required columns missing"):
        store.run_migrations()
    with engine.begin() as connection:
        versions = {row[0] for row in connection.execute(select(store.schema_version.c.version))}
    assert 24 not in versions


def test_activation_migration_failure_is_not_recorded(monkeypatch):
    engine = create_engine("sqlite://", future=True)
    monkeypatch.setattr(store, "engine", engine)

    def fail(_connection):
        raise RuntimeError("activation schema unavailable")

    monkeypatch.setattr(store, "_MIGRATIONS", [(22, fail)])
    with pytest.raises(RuntimeError, match="activation schema unavailable"):
        store.run_migrations()
    with engine.begin() as connection:
        versions = {row[0] for row in connection.execute(select(store.schema_version.c.version))}
    assert 22 not in versions
