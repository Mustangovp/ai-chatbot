"""Local operational controls; no test claims a mini-TTS invoice ceiling."""
from types import SimpleNamespace
import copy

import pytest

import app as appmod
from voice import charging, tts, realtime
from voice.errors import public_error
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


@pytest.fixture
def pilot_browser(pilot, monkeypatch):
    uid, sid, policy = pilot
    monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    monkeypatch.setenv("APP_URL", "https://apexpulse.pro")
    realtime.sessions.configure(uid, authorized=True, session_seconds=120, aggregate_seconds=120)
    browser = appmod.app.test_client()
    browser.set_cookie("apex_session", sid, domain="apexpulse.pro")
    return uid, sid, policy, browser


def pilot_status(browser):
    return browser.get("/api/live-voice/allowances", base_url="https://apexpulse.pro")


def test_preflight_is_read_only_and_exposes_only_allowances(pilot_browser):
    uid, _, policy, browser = pilot_browser
    before = copy.deepcopy((policy.read(), realtime.sessions.read(uid)))
    response = pilot_status(browser)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json == {
        "tts": {"remaining_requests": 4, "available": True, "error": None},
        "media": {"remaining_seconds": 120, "session_seconds": 120, "available": True, "error": None}}
    assert (policy.read(), realtime.sessions.read(uid)) == before


def test_four_tts_requests_exhaust_preflight_and_route_without_fifth_submission(pilot_browser, monkeypatch):
    uid, sid, policy, browser = pilot_browser
    raw = AudioClient()
    with charging.scope(charging.Principal(str(uid), sid)):
        for _ in range(4):
            assert charging.protect(raw).audio.speech.create(**mini_parameters()).read()
    monkeypatch.setattr(appmod, "client", charging.protect(raw))
    monkeypatch.setattr(tts, "_active", tts._OpenAITTS())
    before = copy.deepcopy(policy.read())
    assert pilot_status(browser).json["tts"] == {
        "remaining_requests": 0, "available": False, "error": "tts_quota_exhausted"}
    result = browser.post("/speak", base_url="https://apexpulse.pro", json={"text": "Synthetic"})
    assert result.status_code == 429
    assert result.json == {"error": "tts_quota_exhausted", "terminal": True}
    assert len(raw.calls) == 4 and policy.read() == before


def test_media_reservation_is_not_actual_elapsed_time_and_status_never_refills(pilot_browser):
    uid, sid, policy, browser = pilot_browser
    lease = realtime.sessions.reserve(uid, sid)
    assert pilot_status(browser).json["media"]["error"] == "media_session_active"
    realtime.sessions.finish(uid, lease["id"], provider_confirmed=True)
    before = copy.deepcopy((policy.read(), realtime.sessions.read(uid)))
    for _ in range(2):
        assert pilot_status(browser).json["media"] == {
            "remaining_seconds": 0, "session_seconds": 120,
            "available": False, "error": "media_quota_exhausted"}
    with pytest.raises(Denied, match="usage_exhausted"):
        realtime.sessions.reserve(uid, sid)
    assert (policy.read(), realtime.sessions.read(uid)) == before


def test_media_quota_response_denies_before_transcription_reservation(pilot_browser, monkeypatch):
    from flask import g
    uid, sid, policy, _ = pilot_browser
    lease = realtime.sessions.reserve(uid, sid)
    realtime.sessions.finish(uid, lease["id"], provider_confirmed=True)
    before = copy.deepcopy((policy.read(), realtime.sessions.read(uid)))
    monkeypatch.setattr(policy, "reserve", lambda *a, **kw: pytest.fail("exhausted media reached charging"))
    with appmod.app.test_request_context("/api/live-voice/media?lang=bg", base_url="https://apexpulse.pro",
            headers={"Origin": "https://apexpulse.pro", "Cookie": "apex_session=" + sid}):
        g.user = appmod.store.get_session_user(sid)
        response = appmod.app.make_response(realtime.media_socket())
        assert response.status_code == 429
        assert response.json == {"error": "media_quota_exhausted", "terminal": True}
    assert (policy.read(), realtime.sessions.read(uid)) == before


def test_preflight_allowlist_flag_and_kill_switch_remain_authoritative(pilot_browser, monkeypatch):
    _, sid, policy, browser = pilot_browser
    other = appmod.store.get_or_create_user("not-voice-tester@example.invalid")
    other_session = appmod.store.create_session(other)
    browser.set_cookie("apex_session", other_session, domain="apexpulse.pro")
    response = pilot_status(browser)
    assert response.status_code == 403 and response.json == {"error": "forbidden"}
    browser.set_cookie("apex_session", sid, domain="apexpulse.pro")
    policy.set_enabled(False)
    assert pilot_status(browser).status_code == 403
    policy.set_enabled(True)
    monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "false")
    assert pilot_status(browser).status_code == 403


def test_preflight_shared_state_outage_fails_closed_without_private_details(pilot_browser, monkeypatch):
    _, _, _, browser = pilot_browser
    def offline(*args):
        raise RuntimeError("private-db-connection")
    monkeypatch.setattr(realtime.sessions, "read", offline)
    response = pilot_status(browser)
    # An unavailable store is not evidence that the account is unauthorized.
    assert response.status_code == 503 and response.json["error"] == "pilot_unavailable"
    assert "private-db" not in response.get_data(as_text=True)


@pytest.mark.parametrize("reason,code,status_code", [
    ("tts_pilot_exhausted", "tts_quota_exhausted", 429),
    ("tts_operation_limit", "tts_quota_exhausted", 429),
    ("usage_exhausted", "media_quota_exhausted", 429),
    ("unauthenticated", "forbidden", 403),
    ("pilot_expired", "pilot_expired", 403),
    ("test_disabled", "pilot_disabled", 403),
    ("private-provider-detail", "pilot_unavailable", 503),
])
def test_public_error_allowlist(reason, code, status_code):
    body, http = public_error(Denied(reason))
    assert http == status_code and body == {"error": code, "terminal": True}


def test_provider_failure_remains_distinct_from_quota_and_is_not_retried(pilot_browser, monkeypatch):
    _, _, _, browser = pilot_browser
    calls = []
    def failed(*args, **kwargs):
        calls.append(True)
        raise ConnectionError("private provider details")
    monkeypatch.setattr(appmod.apex_voice, "synthesize", failed)
    response = browser.post("/speak", base_url="https://apexpulse.pro", json={"text": "Synthetic"})
    assert response.status_code == 502 and response.json == {"error": "tts_unavailable"}
    assert calls == [True]


def test_expired_pilot_denies_preflight_and_speech_without_charging(pilot_browser, monkeypatch):
    _, _, policy, browser = pilot_browser
    policy.clock = lambda: policy.read()["expires_at"] + 1
    before = copy.deepcopy(policy.read())
    def forbidden(*args, **kwargs):
        pytest.fail("expired access reached TTS")
    monkeypatch.setattr(appmod.apex_voice, "synthesize", forbidden)
    for response in (pilot_status(browser), browser.post("/speak", base_url="https://apexpulse.pro",
                                                        json={"text": "Synthetic"})):
        assert response.status_code == 403
        assert response.json == {"error": "pilot_expired", "terminal": True}
    html = browser.get("/app", base_url="https://apexpulse.pro").get_data(as_text=True)
    assert '"pilot_error": "pilot_expired"' in html
    assert policy.read() == before


@pytest.mark.parametrize("reason", ["kill_switch", "flag_off"])
def test_disabled_pilot_cannot_enter_legacy_voice_from_rendered_config(pilot_browser, monkeypatch, reason):
    _, _, policy, browser = pilot_browser
    if reason == "kill_switch":
        policy.set_enabled(False)
    else:
        monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "false")
    before = copy.deepcopy(policy.read())
    response = pilot_status(browser)
    assert response.status_code == 403
    assert response.json == {"error": "pilot_disabled", "terminal": True}
    html = browser.get("/app", base_url="https://apexpulse.pro").get_data(as_text=True)
    assert '"pilot_error": "pilot_disabled"' in html and '"enabled": false' in html
    assert policy.read() == before


def test_anonymous_preflight_reveals_no_pilot_state(pilot_browser):
    _, _, policy, browser = pilot_browser
    policy.set_enabled(False)
    browser.delete_cookie("apex_session", domain="apexpulse.pro")
    response = pilot_status(browser)
    assert response.status_code == 403 and response.json == {"error": "forbidden"}


def test_kill_switch_speech_response_is_not_misreported_as_unauthorized(pilot_browser, monkeypatch):
    _, _, policy, browser = pilot_browser
    policy.set_enabled(False)
    before = copy.deepcopy(policy.read())
    monkeypatch.setattr(appmod.apex_voice, "synthesize", lambda *a, **kw: pytest.fail("disabled pilot reached TTS"))
    response = browser.post("/speak", base_url="https://apexpulse.pro", json={"text": "Synthetic"})
    assert response.status_code == 403
    assert response.json == {"error": "pilot_disabled", "terminal": True}
    assert policy.read() == before
