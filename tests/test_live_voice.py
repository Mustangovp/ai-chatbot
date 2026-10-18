"""MOCK_PASS only: provider transport, not real model access or voice quality."""
import json
import types
import time

import pytest

import app as appmod
from voice import realtime
from voice.safety import SafetyStore


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "mock")
    uid = appmod.store.get_or_create_user("synthetic@example.invalid")
    realtime.sessions.configure(uid, authorized=True)
    control = SafetyStore(require_postgres=False)
    control.provision(uid, global_micro_usd=5_000_000, account_micro_usd=5_000_000,
                      max_operations=128, expires_at=time.time() + 3600)
    control.set_enabled(True)
    monkeypatch.setattr(realtime.charging, "control", control)
    guard = realtime.SessionGuard(realtime.sessions, realtime.hangup_call,
                                  lambda _sid: {"id": uid}, lambda: True)
    monkeypatch.setattr(realtime, "start_guardian", lambda: guard)
    monkeypatch.setattr(appmod.store, "get_session_user", lambda sid: (
        {"id": uid, "email": "synthetic@example.invalid"} if sid == "verified-session" else None
    ))
    realtime._attempts.clear()
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, "verified-session")
    return client


def post(client, **kwargs):
    options = dict(data="v=0\r\ns=synthetic\r\n", content_type="application/sdp",
                   headers={"Origin": "http://localhost"})
    options.update(kwargs)
    return client.post("/api/live-voice/connect?lang=en", **options)


def test_default_off_and_no_browser_transport(monkeypatch):
    monkeypatch.delenv("APEX_LIVE_VOICE_ENABLED", raising=False)
    client = appmod.app.test_client()
    assert post(client).status_code == 403
    body = client.get("/app").get_data(as_text=True)
    assert '<script src="/static/live_voice.js">' not in body
    assert '"enabled": false' in body


def test_mock_connection_never_calls_provider_or_projects_private_data(local, monkeypatch):
    def forbidden(*_args):
        pytest.fail("mock must not call OpenAI")
    monkeypatch.setattr(realtime, "exchange_sdp", forbidden)
    response = post(local)
    assert response.status_code == 200
    assert response.get_json() == {"transport": "mock", "live_tested": False}
    assert response.headers["Cache-Control"] == "no-store"
    assert "synthetic-account" not in response.get_data(as_text=True)


@pytest.mark.parametrize("cookie", [None, "forged-session"])
def test_verified_account_cookie_required(local, cookie):
    local.delete_cookie(appmod.SESSION_COOKIE)
    if cookie:
        local.set_cookie(appmod.SESSION_COOKIE, cookie)
    assert post(local).status_code == 403


@pytest.mark.parametrize("origin", [None, "https://attacker.invalid", "http://localhost:9999", "null"])
def test_cross_origin_and_missing_origin_rejected(local, origin):
    response = post(local, headers={} if origin is None else {"Origin": origin})
    assert response.status_code == 403


@pytest.mark.parametrize("host,remote,headers", [
    ("https://apexpulse.pro", "127.0.0.1", {}),
    ("http://localhost", "203.0.113.5", {}),
    ("http://localhost", "127.0.0.1", {"X-Forwarded-For": "127.0.0.1"}),
    ("http://localhost", "127.0.0.1", {"X-Forwarded-Host": "localhost"}),
])
def test_production_and_forwarded_requests_cannot_enable_local_prototype(local, host, remote, headers):
    assert post(local, base_url=host, environ_base={"REMOTE_ADDR": remote}, headers=headers).status_code == 403


@pytest.mark.parametrize("data,content_type", [("bad", "application/sdp"), ("v=0" + "x" * 66000, "application/sdp"),
                                                  ('{"account_id":"other"}', "application/json")], ids=["invalid", "oversize", "identity-body"])
def test_malformed_or_account_asserting_body_rejected(local, data, content_type):
    assert post(local, data=data, content_type=content_type).status_code == 400


def test_bounded_connection_cost_guard(local):
    assert [post(local).status_code for _ in range(7)] == [200] * 6 + [429]


def test_invalid_encoding_language_and_fetch_site_fail_closed(local):
    assert post(local, data=b"v=0\xff").status_code == 400
    assert local.post("/api/live-voice/connect?lang=xx", data="v=0", content_type="application/sdp",
                      headers={"Origin": "http://localhost"}).status_code == 400
    assert post(local, headers={"Origin": "http://localhost", "Sec-Fetch-Site": "cross-site"}).status_code == 403


@pytest.mark.parametrize("language", ["bg", "en"])
def test_provider_session_cannot_generate_its_own_coaching(language):
    config = realtime.session_config(language)
    assert config["output_modalities"] == ["text"]
    assert config["tools"] == [] and config["tracing"] is None
    assert config["audio"]["input"]["transcription"]["languages"] == [language]
    assert config["audio"]["input"]["turn_detection"] == {
        "type": "server_vad", "create_response": False, "interrupt_response": False,
    }
    assert "Transcription transport only" in config["instructions"]
    personality = realtime.speaking_instructions(language)
    for phrase in ["Disagree respectfully", "Accept corrections", "without forced theatrics", "persistent constraints"]:
        assert phrase in personality


def test_direct_live_handshake_is_disabled_and_never_calls_provider(local, monkeypatch, capsys):
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    secret = "private-provider-message-never-export"
    def failed(*_args):
        pytest.fail("direct SDP must not create a provider session")
    monkeypatch.setattr(realtime, "exchange_sdp", failed)
    response = post(local)
    assert response.status_code == 410
    assert response.get_json() == {"error": "direct_media_disabled"}
    assert secret not in response.get_data(as_text=True) + capsys.readouterr().out


def test_browser_config_selects_only_the_server_owned_relay(local, monkeypatch):
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    seen = []
    def exchange(sdp, config):
        seen.append((sdp, config))
        return "v=0\r\ns=provider-answer\r\n", "rtc_synthetic"
    monkeypatch.setattr(realtime, "exchange_sdp", exchange)
    response = local.get("/app")
    assert '"transport": "relay"' in response.get_data(as_text=True)
    assert seen == []
    assert post(local).status_code == 410


def test_provider_adapter_has_one_bounded_call_and_keeps_key_server_side(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    calls = []
    class Reply:
        status = 201
        headers = {"Location": "/v1/realtime/calls/rtc_synthetic"}
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, limit):
            assert limit == 65537
            return b"v=0\r\ns=synthetic\r\n"
    def open_request(req, timeout):
        assert req.full_url == "https://api.openai.com/v1/realtime/calls"
        assert req.get_header("Authorization") == "Bearer synthetic-test-key"
        assert b"synthetic-test-key" not in req.data
        assert timeout == 15
        calls.append(req)
        return Reply()
    monkeypatch.setattr(realtime.urlrequest, "urlopen", open_request)
    assert realtime.exchange_sdp("v=0", realtime.session_config("bg"))[0].startswith("v=0")
    assert len(calls) == 1


def test_missing_credentials_or_unknown_model_fail_closed(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="local_credentials_missing"):
        realtime.exchange_sdp("v=0", {})
    monkeypatch.setenv("APEX_REALTIME_MODEL", "unapproved-model")
    with pytest.raises(ValueError, match="unsupported_realtime_model"):
        realtime.session_config("en")


@pytest.mark.parametrize("language", ["bg", "en"])
def test_live_voice_style_reaches_existing_chat_only_for_authenticated_local_voice(local, monkeypatch, language):
    captured = []
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "false")
    def generate(**kwargs):
        captured.append(kwargs)
        return iter([types.SimpleNamespace(choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="A small step is a useful start."), finish_reason="stop")])])
    monkeypatch.setattr(appmod.client.chat.completions, "create", generate)
    # Use the real /chat boundary. No realtime response event can call generation.
    response = local.post("/chat", json={"message": "How can I stay motivated?", "lang": language, "voice": True})
    text = response.get_data(as_text=True)
    assert response.status_code == 200 and '"done": true' in text
    assert captured and captured[0]["model"] == "gpt-6-luna"
    assert realtime.speaking_instructions(language) in captured[0]["messages"][0]["content"]


@pytest.mark.parametrize("language", ["bg", "en"])
@pytest.mark.parametrize("enforcement", ["false", "true"])
def test_live_voice_keeps_real_training_constraints_and_harder_followup_authoritative(local, monkeypatch, language, enforcement):
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("BRAIN_ENFORCE", enforcement)
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    uid = appmod.store.get_or_create_user("synthetic@example.invalid")
    appmod.store.save_profile(uid, {"goal": "strength", "equipment": "gym", "level": "intermediate",
                                  "age": "30", "height": "180", "weight": "80",
                                  "sleepQuality": "good", "stressLevel": "low", "recoveryFeel": "good"})
    def generate(**_kwargs):
        return iter([types.SimpleNamespace(choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="The recorded restriction remains authoritative."), finish_reason="stop")])])
    monkeypatch.setattr(appmod.client.chat.completions, "create", generate)
    messages = (["Направи ми тренировка, но избягвай преси над глава.", "Направи тренировката по-трудна."]
                if language == "bg" else ["Create a workout, avoid overhead pressing.", "Make the workout harder."])
    library = appmod.load_exercise_library()
    for message in messages:
        response = local.post("/chat", json={"message": message, "lang": language, "voice": True,
                                             "conversation_id": "local-live-voice-0001"})
        events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]
        assert response.status_code == 200 and events[-1] == {"done": True}
        completion = next(event["training_completion"] for event in events if "training_completion" in event)
        exercises = completion["sessions"][0]["exercises"]
        assert exercises
        assert all(library.require(item["exercise_id"], item["exercise_version"]).movement_pattern
                   != appmod.MovementPattern.VERTICAL_PUSH for item in exercises)


@pytest.mark.parametrize("language", ["bg", "en"])
def test_transcription_uses_supported_language_hints(language):
    transcription = realtime.session_config(language)["audio"]["input"]["transcription"]
    assert transcription["languages"] == [language]
    assert "language" not in transcription
    assert transcription["prompt"]


@pytest.mark.parametrize("message,preferred,expected", [
    ("Аз говоря на български.", "en", "bg"),
    ("Отговаряй на български, моля.", "en", "bg"),
    ("Please speak English.", "bg", "en"),
    ("Why are you speaking English?", "bg", "bg"),
    ("Защо тренировката е на английски?", "bg", "bg"),
    ("Не говори на английски.", "bg", "bg"),
    ("Дай ми workout с dumbbells.", "bg-BG", "bg"),
])
def test_only_explicit_language_choice_changes_response_language(message, preferred, expected):
    assert realtime.response_language(message, preferred) == expected


@pytest.mark.parametrize("message", [
    "Защо ми го даваш на английски?", "Защо тренировката е на английски?",
    "Why are you speaking English?", "Аз говоря на български.",
])
@pytest.mark.parametrize("enforcement", ["false", "true"])
def test_language_turn_does_not_modify_an_active_workout(local, monkeypatch, message, enforcement):
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("BRAIN_ENFORCE", enforcement)
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    uid = appmod.store.get_or_create_user("synthetic@example.invalid")
    appmod.store.save_profile(uid, {"goal": "strength", "equipment": "home", "level": "intermediate",
                                  "age": "30", "height": "180", "weight": "80",
                                  "sleepQuality": "good", "stressLevel": "low", "recoveryFeel": "good"})
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
            content=json.dumps({"explanations": ["Движенията са съобразени с потвърденото оборудване."]})))])
    monkeypatch.setattr(appmod.client.chat.completions, "create", generate)
    body = {"lang": "bg", "voice": True, "conversation_id": "language-active-workout-01"}
    workout = local.post("/chat", json={**body, "message": "Дай ми тренировъчен план за днес."})
    assert '"training_completion"' in workout.get_data(as_text=True)
    scope = appmod._workout_conversation_scope(body, uid, None)
    before = appmod._last_workout_for(scope)
    assert before is not None
    call_count = len(calls)
    reply = local.post("/chat", json={**body, "message": message})
    events = [json.loads(line[6:]) for line in reply.get_data(as_text=True).splitlines() if line.startswith("data: ")]
    text = "".join(event.get("t", "") for event in events)
    assert reply.headers["Content-Language"] == "bg-BG"
    assert "български" in text
    assert "не успях" not in text.lower() and "unavailable" not in text.lower()
    assert not any("training_completion" in event for event in events)
    assert appmod._last_workout_for(scope).blueprint_hash == before.blueprint_hash
    assert len(calls) == call_count
    assert events[-1] == {"done": True}


def test_bg_session_language_is_explicit_in_the_real_model_request(local, monkeypatch):
    captured = []
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    def generate(**kwargs):
        captured.append(kwargs)
        return iter([types.SimpleNamespace(choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="Здравей! С какво да помогна?"), finish_reason="stop")])])
    monkeypatch.setattr(appmod.client.chat.completions, "create", generate)
    response = local.post("/chat", json={"message": "Здравей, чуваш ли ме?", "lang": "bg-BG", "voice": True})
    text = response.get_data(as_text=True)
    assert '"done": true' in text and "Здравей" in text
    assert response.headers["Content-Language"] == "bg-BG"
    assert "[RESPONSE LANGUAGE: bg-BG]" in captured[0]["messages"][0]["content"]


def test_spoken_language_choice_is_acknowledged_before_presentation(local, monkeypatch):
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs: pytest.fail("language choice is not a model turn"))
    response = local.post("/chat", json={"message": "Аз говоря на български.", "lang": "en", "voice": True})
    assert response.headers["Content-Language"] == "bg-BG"
    text = response.get_data(as_text=True)
    assert "български" in text
    assert any("български" in json.loads(line[6:]).get("speech_text", "")
               for line in text.splitlines() if line.startswith("data: "))


def test_demo_context_is_explicit_and_not_enabled_by_the_normal_app(local):
    from flask import render_template
    normal = local.get("/app").get_data(as_text=True)
    assert 'id="local-demo-notice"' not in normal
    with appmod.app.test_request_context("/app"):
        demo = render_template("apex.html", live_voice_config={"enabled": True, "transport": "mock"}, live_voice_demo=True)
    assert 'id="local-demo-notice"' in demo
    assert "DEMO" in demo and "Synthetic" in demo


def test_bg_workout_rejects_untranslated_model_explanation_not_the_valid_workout(local, monkeypatch):
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("BRAIN_ENFORCE", "true")
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "true")
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    uid = appmod.store.get_or_create_user("synthetic@example.invalid")
    appmod.store.save_profile(uid, {"goal": "strength", "equipment": "home", "level": "intermediate",
                                  "age": "30", "height": "180", "weight": "80",
                                  "sleepQuality": "good", "stressLevel": "low", "recoveryFeel": "good"})
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs:
        types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
            content=json.dumps({"explanations": ["This workout is perfect for your goals."]}))) ]))
    response = local.post("/chat", json={"message": "Дай ми тренировъчен план за днес.", "lang": "bg", "voice": True,
                                         "conversation_id": "bg-training-language-contract"})
    events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]
    text = "".join(event.get("t", "") for event in events)
    completion = next(event["training_completion"] for event in events if "training_completion" in event)
    assert "This workout" not in text and "Защо тази тренировка" in text
    assert all(realtime.explanation_language_matches(item["display_name"], "bg")
               for item in completion["sessions"][0]["exercises"])
    assert any("Тренировката ти е готова" in event.get("speech_text", "") for event in events)
    assert events[-1] == {"done": True}


@pytest.mark.parametrize("mode", ["text", "legacy_voice", "unauthorized_voice", "live_voice"])
def test_language_presentation_requires_voice_and_server_authorization(local, monkeypatch, mode):
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "false")
    monkeypatch.setenv("BRAIN_ENFORCE", "false")
    monkeypatch.setenv("CONVERSATION_COMPOSER_ACTIVE", "false")
    if mode == "legacy_voice":
        monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "false")
    if mode == "unauthorized_voice":
        local.delete_cookie(appmod.SESSION_COOKIE)
    captured = []
    def generate(**kwargs):
        captured.append(kwargs)
        return iter([types.SimpleNamespace(choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="Synthetic coaching reply."), finish_reason="stop")])])
    monkeypatch.setattr(appmod.client.chat.completions, "create", generate)
    response = local.post("/chat", json={"message": "How can I stay motivated?", "lang": "bg",
                                         "voice": mode != "text"})
    assert '"done": true' in response.get_data(as_text=True)
    assert captured and captured[0]["model"] == "gpt-6-luna"
    prompt = captured[0]["messages"][0]["content"]
    if mode == "live_voice":
        assert realtime.response_language_instructions("bg") in prompt
        assert realtime.speaking_instructions("bg") in prompt
        assert response.headers["Content-Language"] == "bg-BG"
    else:
        assert "[RESPONSE LANGUAGE:" not in prompt
        assert "APEX Live Voice communication:" not in prompt
        assert "Content-Language" not in response.headers


def test_text_chat_does_not_call_voice_language_or_routing_helpers(local, monkeypatch):
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *_args, **_kwargs: None)
    def forbidden(*_args, **_kwargs):
        pytest.fail("text chat called a Live Voice presentation/routing helper")
    for name in ("response_language", "is_language_turn", "response_language_instructions",
                 "speaking_instructions", "explanation_language_matches"):
        monkeypatch.setattr(realtime, name, forbidden)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **_kwargs:
        iter([types.SimpleNamespace(choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="Ordinary text coaching."), finish_reason="stop")])]))
    response = local.post("/chat", json={"message": "How can I stay motivated?", "lang": "en"})
    assert response.status_code == 200
    assert "Ordinary text coaching." in response.get_data(as_text=True)
