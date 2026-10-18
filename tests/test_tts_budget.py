"""Local operational controls; no test claims a mini-TTS invoice ceiling."""
from types import SimpleNamespace

import pytest

import app as appmod
from voice import charging, tts
from voice.session_store import Denied
from test_live_voice_safety_controls import Client, controlled


def speech_parameters():
    # Legacy fixture exercises the shared reservation lifecycle, NOT a model
    # substitution. Production's gpt-4o-mini-tts remains denied by the strict gate.
    return dict(model="tts-1", input="Synthetic test", voice="alloy")


class AudioClient(Client):
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(read=lambda: b"synthetic-audio", close=lambda: None)


@pytest.mark.parametrize("text", [None, {}, 12, "", "  ", "x" * 1601])
def test_speak_rejects_invalid_or_oversized_input_without_provider(monkeypatch, text):
    def forbidden(*args, **kwargs): pytest.fail("invalid input reached provider")
    monkeypatch.setattr(appmod.apex_voice, "synthesize", forbidden)
    response = appmod.app.test_client().post("/speak", json={"text": text})
    assert response.status_code == 400


@pytest.mark.parametrize("error", [TypeError("synthetic"), ConnectionError("synthetic")])
def test_adapter_has_one_submission_no_fallback_retry_or_model_change(error):
    class Failed(AudioClient):
        def create(self, **kwargs): self.calls.append(kwargs); raise error
    raw = Failed()
    provider = tts._OpenAITTS()
    with pytest.raises(type(error)):
        provider.synthesize("Synthetic", "bg", raw)
    assert len(raw.calls) == 1
    assert raw.calls[0]["model"] == "gpt-4o-mini-tts"
    assert raw.options == [dict(max_retries=0, timeout=20)]


def test_adapter_rejects_oversized_input_even_without_route():
    raw = AudioClient()
    with pytest.raises(ValueError): tts._OpenAITTS().synthesize("x" * 1601, "bg", raw)
    assert not raw.calls


def test_planning_estimate_does_not_authorize_current_model(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    parameters = dict(model="gpt-4o-mini-tts", input="Synthetic", voice="alloy")
    assert charging.mini_tts_pilot_estimate(parameters) == 100_000
    with pytest.raises(Denied): charging.mini_tts_pilot_estimate(parameters | {"input": "x" * 401})
    raw = AudioClient()
    # with_options must preserve the protected wrapper, not expose the raw SDK.
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(Denied, match="tts_cost_bound_unavailable"):
            tts._OpenAITTS().synthesize("Synthetic", "bg", charging.protect(raw))
    assert raw.calls == [] and policy.read()["operation_count"] == 0


def test_tts_slot_and_attempt_count_are_shared_and_never_refill(controlled):
    from voice.safety import SafetyStore
    uid, sid, policy = controlled
    policy.set_enabled(True)
    other = SafetyStore(require_postgres=False)
    first = policy.reserve(uid, sid, "tts", 100)
    with pytest.raises(Denied, match="tts_already_active"): other.reserve(uid, sid, "tts", 100)
    policy.tts_submitted(first)
    with pytest.raises(Denied, match="uncertain"): other.finish_tts(first, unused=True)
    policy.finish_tts(first)
    for _ in range(3):
        grant = other.reserve(uid, sid, "tts", 100)
        other.finish_tts(grant, unused=True)
    with pytest.raises(Denied, match="tts_operation_limit"): policy.reserve(uid, sid, "tts", 100)
    assert policy.read()["global_used"] == 100
    assert policy.read()["operation_count"] == 4


def test_full_binary_read_releases_slot_but_does_not_invent_usage(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw = AudioClient()
    with charging.scope(charging.Principal(uid, sid)):
        result = charging.protect(raw).audio.speech.create(**speech_parameters())
        with pytest.raises(Denied, match="tts_already_active"):
            charging.protect(raw).audio.speech.create(**speech_parameters())
        assert result.read() == b"synthetic-audio"
        result.close()
        assert charging.protect(raw).audio.speech.create(**speech_parameters()).read()
    data = policy.read()
    assert len(raw.calls) == data["operation_count"] == 2
    assert data["global_used"] == 2 * charging.quote("tts", speech_parameters())[0]
    assert all(not item["settled"] for item in data["operations"].values())


def test_failure_before_provider_submission_refunds_only_unused_reservation(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw = AudioClient()
    def fail(**kwargs): raise RuntimeError("local client configuration failed")
    raw.with_options = fail
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(RuntimeError): charging.protect(raw).audio.speech.create(**speech_parameters())
    data = policy.read()
    assert not raw.calls and data["global_used"] == data["account_used"] == 0
    assert data["operation_count"] == 1
    operation = next(iter(data["operations"].values()))
    assert operation["actual"] == 0 and operation["tts_open"] is False


@pytest.mark.parametrize("stage", ["create", "read"])
def test_unknown_provider_failure_holds_cost_and_slot_across_instances(controlled, stage):
    from voice.safety import SafetyStore
    uid, sid, policy = controlled
    policy.set_enabled(True)
    def fail(): raise ConnectionError("synthetic unknown result")
    class Failed(AudioClient):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            if stage == "create": fail()
            return SimpleNamespace(read=fail, close=lambda: None)
    raw = Failed()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(ConnectionError):
            charging.protect(raw).audio.speech.create(**speech_parameters()).read()
    assert policy.read()["global_used"] == charging.quote("tts", speech_parameters())[0]
    assert len(raw.calls) == 1
    other = SafetyStore(require_postgres=False)
    with pytest.raises(Denied, match="tts_already_active"): other.reserve(uid, sid, "tts", 1)


def test_tts_budget_exhaustion_has_zero_provider_calls(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    policy.reserve(uid, sid, "gpt6", 899_999)
    raw = AudioClient()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(Denied, match="budget_exhausted"):
            charging.protect(raw).audio.speech.create(**speech_parameters())
    assert not raw.calls and policy.read()["enabled"] is False


def test_tts_verified_usage_reconciliation_returns_only_unused_amount_once(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    grant = policy.reserve(uid, sid, "tts", 1000)
    policy.tts_submitted(grant)
    policy.finish_tts(grant)
    # Only a trusted server-side usage source may supply actual; binary success
    # above does NOT do this. The current mini-TTS response supplies no such usage.
    policy.reconcile(grant, 100)
    policy.reconcile(grant, 0)
    assert policy.read()["global_used"] == policy.read()["account_used"] == 100
    assert policy.read()["operation_count"] == 1


@pytest.fixture
def pilot(controlled):
    uid, sid, policy = controlled
    policy.approve_tts_pilot(uid)
    policy.set_enabled(True)
    return uid, sid, policy


def mini_parameters():
    return dict(model="gpt-4o-mini-tts", input="Synthetic speech", voice="alloy", response_format="mp3")


def test_approved_pilot_four_calls_then_fifth_denied_before_provider(pilot):
    uid, sid, policy = pilot
    raw = AudioClient()
    with charging.scope(charging.Principal(uid, sid)):
        for _ in range(4):
            assert charging.protect(raw).audio.speech.create(**mini_parameters()).read()
        with pytest.raises(Denied, match="tts_pilot_exhausted"):
            charging.protect(raw).audio.speech.create(**mini_parameters())
    assert len(raw.calls) == 4
    assert {call["model"] for call in raw.calls} == {"gpt-4o-mini-tts"}
    data = policy.read()
    assert data["global_used"] == data["account_used"] == 400_000
    assert data["operation_count"] == 4
    assert all(op["reserved"] == 100_000 and not op["settled"] for op in data["operations"].values())
    policy.approve_tts_pilot(uid)
    assert policy.read()["operation_count"] == 4  # Approval is not a refill.


@pytest.mark.parametrize("change", [{"input": "x" * 401}, {"input": " "}, {"model": "tts-1"},
    {"speed": .25}, {"extra_body": {}}, {"instructions": "x" * 513}])
def test_pilot_rejects_unsupported_or_oversized_request_before_reservation(pilot, change):
    uid, sid, policy = pilot
    raw = AudioClient()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(Denied):
            charging.protect(raw).audio.speech.create(**(mini_parameters() | change))
    assert not raw.calls and policy.read()["operation_count"] == 0


def test_pilot_400_character_boundary_and_concurrency(pilot):
    uid, sid, policy = pilot
    raw = AudioClient()
    with charging.scope(charging.Principal(uid, sid)):
        response = charging.protect(raw).audio.speech.create(**(mini_parameters() | {"input": "x" * 400}))
        with pytest.raises(Denied, match="tts_already_active"):
            charging.protect(raw).audio.speech.create(**mini_parameters())
        assert response.read()
    assert len(raw.calls) == policy.read()["operation_count"] == 1


def test_pilot_unknown_failure_keeps_reservation_and_cannot_retry(pilot):
    uid, sid, policy = pilot
    class Failed(AudioClient):
        def create(self, **kwargs): self.calls.append(kwargs); raise ConnectionError("synthetic")
    raw = Failed()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(ConnectionError): charging.protect(raw).audio.speech.create(**mini_parameters())
        with pytest.raises(Denied, match="tts_already_active"):
            charging.protect(raw).audio.speech.create(**mini_parameters())
    assert len(raw.calls) == 1 and policy.read()["global_used"] == 100_000


def test_pilot_unused_refunds_never_allow_more_than_four_attempts(pilot):
    uid, sid, policy = pilot
    for _ in range(4):
        grant = policy.reserve(uid, sid, "tts", 100_000, tts_pilot=True)
        policy.finish_tts(grant, unused=True)
    assert policy.read()["global_used"] == 0
    with pytest.raises(Denied, match="tts_pilot_exhausted"):
        policy.reserve(uid, sid, "tts", 100_000, tts_pilot=True)


def test_pilot_is_exact_account_owned_and_off_blocks_provider(pilot):
    import db
    uid, sid, policy = pilot
    other = db.get_or_create_user("not-pilot@example.invalid")
    other_sid = db.create_session(other)
    with pytest.raises(Denied, match="mismatch"): policy.approve_tts_pilot(other)
    raw = AudioClient()
    with charging.scope(charging.Principal(str(other), other_sid)):
        with pytest.raises(Denied): charging.protect(raw).audio.speech.create(**mini_parameters())
    policy.set_enabled(False)
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(Denied): charging.protect(raw).audio.speech.create(**mini_parameters())
    assert not raw.calls


def test_real_speak_route_enforces_pilot_before_fifth_provider_call(pilot, monkeypatch):
    uid, sid, policy = pilot
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    raw = AudioClient()
    monkeypatch.setattr(appmod, "client", charging.protect(raw))
    monkeypatch.setattr(tts, "_active", tts._OpenAITTS())
    browser = appmod.app.test_client()
    browser.set_cookie("apex_session", sid)
    for language in ("bg", "en", "bg", "en"):
        response = browser.post("/speak", json={"text": "Synthetic", "lang": language, "voice": "alloy"})
        assert response.status_code == 200 and response.data == b"synthetic-audio"
    assert browser.post("/speak", json={"text": "Synthetic"}).status_code == 429
    assert len(raw.calls) == 4 and policy.read()["global_used"] == 400_000
