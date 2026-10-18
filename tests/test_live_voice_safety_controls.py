"""Shared control invariants. SQLite unit tests are NOT PostgreSQL runtime proof."""
import json
import time
from types import SimpleNamespace

import pytest

import db
import app as appmod
from voice import charging, media, realtime
from voice.safety import SafetyStore
from voice.session_store import Denied


@pytest.fixture
def controlled(monkeypatch):
    uid = db.get_or_create_user("shared-safety@example.invalid")
    sid = db.create_session(uid)
    policy = SafetyStore(require_postgres=False)
    policy.provision(uid, global_micro_usd=1_000_000, account_micro_usd=900_000,
                     max_operations=32, expires_at=time.time() + 60)
    monkeypatch.setattr(charging, "control", policy)
    return str(uid), sid, policy


def test_defaults_off_and_sqlite_not_release_authority(controlled):
    uid, sid, policy = controlled
    with pytest.raises(Denied, match="test_disabled"):
        policy.reserve(uid, sid, "gpt6", 100)
    with pytest.raises(Denied, match="postgres_safety_required"):
        SafetyStore().require(uid)


def test_same_budget_covers_all_operations_without_refill(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    grants = [policy.reserve(uid, sid, kind, 300_000) for kind in ("transcription", "gpt6", "tts")]
    data = policy.read()
    assert data["global_used"] == data["account_used"] == 900_000
    with pytest.raises(Denied, match="exhausted"): policy.reserve(uid, sid, "gpt6", 1)
    policy.clock = lambda: time.time() + 86401
    with pytest.raises(Denied): policy.reserve(uid, sid, "gpt6", 1)
    assert policy.read()["global_used"] == 900_000
    assert len(grants) == 3


def test_trustworthy_actual_usage_reconciles_once_unknown_stays_reserved(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    grant = policy.reserve(uid, sid, "gpt6", 1000)
    policy.reconcile(grant, None)
    assert policy.read()["global_used"] == 1000
    policy.reconcile(grant, 100)
    policy.reconcile(grant, 0)
    assert policy.read()["global_used"] == policy.read()["account_used"] == 100
    assert policy.read()["operation_count"] == 1


def test_kill_switch_and_epoch_survive_new_instance(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    grant = policy.reserve(uid, sid, "transcription", 1000)
    other = SafetyStore(require_postgres=False)
    other.set_enabled(False)
    with pytest.raises(Denied): policy.require(uid, grant["epoch"])
    with pytest.raises(Denied): other.reserve(uid, sid, "tts", 1)
    other.set_enabled(True)
    with pytest.raises(Denied): policy.require(uid, grant["epoch"])
    assert other.read()["global_used"] == 1000


def test_ownership_revoked_auth_and_bound_violation_fail_closed(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    other = db.get_or_create_user("not-the-allowed-tester@example.invalid")
    with pytest.raises(Denied): policy.reserve(str(other), sid, "gpt6", 1)
    with pytest.raises(Denied, match="test_disabled"):
        policy.reserve(str(other), db.create_session(other), "gpt6", 1)
    grant = policy.reserve(uid, sid, "gpt6", 100)
    policy.reconcile(grant, 101)
    assert policy.read()["enabled"] is False
    with pytest.raises(Denied): policy.set_enabled(True)
    with pytest.raises(Denied): policy.require(uid)
    db.revoke_session(sid)
    with pytest.raises(Denied, match="unauthenticated"): policy.reserve(uid, sid, "gpt6", 1)


def test_provisioning_cannot_refill_or_reassign(controlled):
    uid, sid, policy = controlled
    with pytest.raises(Denied, match="already_provisioned"):
        policy.provision(uid, global_micro_usd=1000, account_micro_usd=1000,
                         max_operations=1, expires_at=time.time() + 60)
    assert policy.read()["enabled"] is False


def test_repeated_media_sessions_do_not_reset_global_allocation(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    realtime.sessions.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    for _ in range(2):
        lease = realtime.sessions.reserve(uid, sid)
        policy.reserve(uid, sid, "transcription", (lease["seconds"] + 256) * 1000)
        realtime.sessions.finish(uid, lease["id"], provider_confirmed=True)
    assert policy.read()["global_used"] == policy.read()["account_used"] == 542000
    assert policy.read()["operation_count"] == 2
    with pytest.raises(Denied): realtime.sessions.reserve(uid, sid)


@pytest.mark.parametrize("usage", [{"seconds": 2}, {}])
def test_only_complete_transcription_duration_usage_can_settle(controlled, usage):
    from test_live_voice_media import Clock, Downstream, Provider
    uid, sid, policy = controlled
    policy.set_enabled(True)
    realtime.sessions.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    lease = realtime.sessions.reserve(uid, sid)
    grant = policy.reserve(uid, sid, "transcription", 271000)
    clock = Clock()
    provider = Provider([{"type": "input_audio_buffer.committed", "item_id": "provider-only-id"},
        {"type": "conversation.item.input_audio_transcription.completed", "item_id": "provider-only-id",
         "transcript": "Synthetic", "usage": usage}])
    media.serve(Downstream(clock), uid, lease, realtime.sessions, db.get_session_user, lambda: True,
                realtime.session_config("en"), factory=lambda _: provider, clock=clock,
                wall=lambda: lease["deadline"] - 2, safety=(policy, grant))
    assert policy.read()["global_used"] == (150 if usage else 271000)


class Client:
    def __init__(self):
        self.calls, self.options = [], []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=self.create))
    def with_options(self, **kwargs): self.options.append(kwargs); return self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def params():
    return {"model": "gpt-6-luna", "max_completion_tokens": 100,
            "messages": [{"role": "user", "content": "Synthetic coaching question"}]}


def test_real_client_boundary_reserves_each_retry_and_reconciles(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw = Client()
    client = charging.protect(raw)
    with charging.scope(charging.Principal(uid, sid)):
        client.chat.completions.create(**params())
        client.chat.completions.create(**params())
    assert len(raw.calls) == 2
    assert raw.options == [{"max_retries": 0, "timeout": 20}] * 2
    assert policy.read()["operation_count"] == 2
    assert policy.read()["global_used"] == 8  # ceil(10*.1 + 5*.5) for each request.


@pytest.mark.parametrize("change", [{"model": "unknown"}, {"max_completion_tokens": None},
    {"messages": [{"role": "user", "content": [{"type": "image_url"}]}]},
    {"extra_body": {"max_completion_tokens": 100000}}, {"n": 2},
    {"response_format": {"type": "json_schema", "json_schema": {"schema": {}}}}])
def test_unknown_cost_bounds_do_not_reach_provider(controlled, change):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw = Client()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(Denied): charging.protect(raw).chat.completions.create(**(params() | change))
    assert raw.calls == [] and policy.read()["global_used"] == 0


def test_current_tts_without_supported_output_bound_is_denied_before_charge(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw = Client()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(Denied, match="tts_cost_bound_unavailable"):
            charging.protect(raw).audio.speech.create(model="gpt-4o-mini-tts", input="Synthetic speech")
    assert raw.calls == [] and policy.read()["operation_count"] == 0


def test_character_billed_tts_and_gpt6_use_same_global_pool(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw = Client()
    with charging.scope(charging.Principal(uid, sid)):
        charging.protect(raw).audio.speech.create(model="tts-1", input="Test")
        charging.protect(raw).chat.completions.create(**params())
    assert {op["kind"] for op in policy.read()["operations"].values()} == {"gpt6", "tts"}
    assert policy.read()["global_used"] == 4 * 60 + 4


def test_existing_endpoints_cannot_bypass_off_switch_with_voice_false(controlled, monkeypatch):
    uid, sid, policy = controlled
    realtime.sessions.configure(uid, authorized=True)
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "true")
    client = appmod.app.test_client()
    client.set_cookie("apex_session", sid)
    for path in ("/chat", "/speak"):
        assert client.post(path, json={"voice": False, "message": "Synthetic", "text": "Synthetic"}).status_code == 403


def test_global_tester_is_budgeted_even_without_a_media_policy_row(controlled, monkeypatch):
    uid, sid, policy = controlled
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    client = appmod.app.test_client()
    client.set_cookie("apex_session", sid)
    for path in ("/chat", "/speak"):
        assert client.post(path, json={"voice": False, "message": "Synthetic", "text": "Synthetic"}).status_code == 403


def test_auth_lookup_outage_cannot_fall_back_to_anonymous_billable_calls(controlled, monkeypatch):
    uid, sid, policy = controlled
    def offline(*args): raise RuntimeError("synthetic account lookup unavailable")
    monkeypatch.setattr(appmod.store, "get_session_user", offline)
    client = appmod.app.test_client()
    client.set_cookie("apex_session", sid)
    for path in ("/chat", "/speak"):
        assert client.post(path, json={"message": "Synthetic", "text": "Synthetic"}).status_code == 503


def test_revoked_cookie_never_turns_test_coaching_into_unmetered_anonymous_call(controlled, monkeypatch):
    from flask import g
    uid, sid, policy = controlled
    policy.set_enabled(True)
    realtime.sessions.configure(uid, authorized=True)
    db.revoke_session(sid)
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    raw = Client()
    with appmod.app.test_request_context("/chat", headers={"Cookie": "apex_session=" + sid}):
        g.user = None
        assert charging.capture() == charging.Principal(uid, sid)
        with pytest.raises(Denied, match="unauthenticated"):
            charging.protect(raw).chat.completions.create(**params())
    assert raw.calls == []


def test_shared_outage_blocks_provider(controlled, monkeypatch):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    def offline(): raise RuntimeError("private-db-detail")
    monkeypatch.setattr(policy, "read", offline)
    raw = Client()
    with charging.scope(charging.Principal(uid, sid)):
        with pytest.raises(RuntimeError): charging.protect(raw).chat.completions.create(**params())
    assert raw.calls == []


def test_failed_attempt_and_application_retry_each_keep_their_maximum(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    class Failed(Client):
        def create(self, **kwargs): self.calls.append(kwargs); raise ConnectionError("synthetic failure")
    raw = Failed()
    with charging.scope(charging.Principal(uid, sid)):
        for _ in range(2):
            with pytest.raises(ConnectionError): charging.protect(raw).chat.completions.create(**params())
    maximum = charging.quote("gpt6", params())[0]
    assert policy.read()["global_used"] == policy.read()["account_used"] == 2 * maximum
    assert policy.read()["operation_count"] == len(raw.calls) == 2


def test_off_switch_interrupts_stream_and_unknown_usage_keeps_reservation(controlled):
    uid, sid, policy = controlled
    policy.set_enabled(True)
    class Stream:
        closed = False
        def __iter__(self):
            yield SimpleNamespace(choices=[], usage=None)
            policy.set_enabled(False)
            yield SimpleNamespace(choices=[], usage=None)
        def close(self): self.closed = True
    stream = Stream()
    raw = Client()
    raw.chat.completions.create = lambda **kwargs: stream
    with charging.scope(charging.Principal(uid, sid)):
        result = charging.protect(raw).chat.completions.create(**(params() | {"stream": True}))
        assert next(result).usage is None
        with pytest.raises(Denied): next(result)
    assert stream.closed and policy.read()["global_used"] == charging.quote("gpt6", params())[0]


def test_detached_learning_retains_verified_principal_without_flask_context(controlled, monkeypatch):
    from flask import has_request_context
    uid, sid, policy = controlled
    policy.set_enabled(True)
    raw, seen = Client(), []
    def learn(*args):
        seen.append(has_request_context())
        charging.protect(raw).chat.completions.create(**params())
    monkeypatch.setattr(appmod.HumanLearningEngine, "process_exchange", learn)
    with charging.scope(charging.Principal(uid, sid)):
        future = appmod._update_learning_engine(uid, "Synthetic question", "Synthetic answer", {})
    future.result(timeout=5)
    assert seen == [False] and len(raw.calls) == 1 and policy.read()["operation_count"] == 1


@pytest.mark.parametrize("action", ["kill", "exhaust", "outage"])
def test_active_media_stops_from_an_independent_shared_control(controlled, action):
    from test_live_voice_media import Clock, Downstream, Provider
    uid, sid, policy = controlled
    policy.set_enabled(True)
    realtime.sessions.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    lease = realtime.sessions.reserve(uid, sid)
    grant = policy.reserve(uid, sid, "transcription", 1000)
    other = SafetyStore(require_postgres=False)
    def switch():
        if action == "kill": other.set_enabled(False)
        elif action == "exhaust":
            with pytest.raises(Denied): other.reserve(uid, sid, "gpt6", 900_000)
        else:
            policy.read = lambda: (_ for _ in ()).throw(RuntimeError("private-offline"))
    clock, provider = Clock(), Provider()
    down = Downstream(clock, action=switch)
    media.serve(down, uid, lease, realtime.sessions, db.get_session_user, lambda: True,
                realtime.session_config("bg"), factory=lambda _: provider, clock=clock,
                wall=lambda: lease["deadline"] - 5, safety=(policy, grant))
    assert down.closed and provider.closed and clock.value < 1
    assert "private-offline" not in json.dumps(down.output)
    assert not any(event["type"] == "error" for event in down.output)
    assert down.output[-1]["type"] == "session.ended"
