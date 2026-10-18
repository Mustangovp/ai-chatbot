"""Deterministic media ownership/authority gates; not live provider evidence."""
import json

import pytest

import db
from voice import media, realtime
from voice.session_store import SessionStore


class Clock:
    value = 0.0
    def __call__(self): return self.value


class Downstream:
    def __init__(self, clock, frames=(), action=None):
        self.clock, self.frames, self.action = clock, list(frames), action
        self.output = []
        self.closed = False
    def send(self, text): self.output.append(json.loads(text))
    def receive(self, timeout):
        self.clock.value += .1
        if self.action:
            action, self.action = self.action, None
            action()
        return self.frames.pop(0) if self.frames else None
    def close(self): self.closed = True


class Provider:
    def __init__(self, events=(), confirmed=True):
        self.events, self.frames = list(events), []
        self.confirmed, self.closed, self.aborted = confirmed, False, False
    def receive(self): return self.events.pop(0) if self.events else None
    def audio(self, frame): self.frames.append(frame)
    def close(self): self.closed = True; return self.confirmed
    def abort(self): self.aborted = True


@pytest.fixture
def session():
    uid = db.get_or_create_user("relay-unit@example.invalid")
    sid = db.create_session(uid)
    store = SessionStore()
    store.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    lease = store.reserve(uid, sid)
    return uid, sid, store, lease


def run(session, down, provider, clock):
    uid, sid, store, lease = session
    media.serve(down, uid, lease, store, db.get_session_user, lambda: True,
                realtime.session_config("bg"), factory=lambda _: provider,
                clock=clock, wall=lambda: lease["deadline"] - 2)


def test_relay_expires_closes_both_transports_and_preserves_provider_usage(session):
    clock = Clock()
    down = Downstream(clock, [b"\0" * 4800])
    provider = Provider([{"type": "conversation.item.input_audio_transcription.completed",
        "item_id": "private-provider-identity", "transcript": "Здравей!", "usage": {"total_tokens": 8}}])
    run(session, down, provider, clock)
    assert down.closed and provider.closed
    assert provider.frames == [b"\0" * 4800]
    assert "private-provider-identity" not in json.dumps(down.output)
    assert any(item.get("transcript") == "Здравей!" for item in down.output)
    facts = session[2].read(session[0])
    assert facts["lease"] is None
    assert facts["last_media"]["usage"] == [{"total_tokens": 8}]
    assert facts["last_media"]["accepted_samples"] == 2400


@pytest.mark.parametrize("frame", [b"\0" * 4802, b"\0", '{"type":"response.create"}', '{"account_id":"other"}'])
def test_client_cannot_forward_provider_commands_or_invalid_frames(session, frame):
    clock = Clock()
    down = Downstream(clock, [frame])
    provider = Provider()
    run(session, down, provider, clock)
    assert provider.frames == [] and provider.closed and down.closed
    assert any(item.get("code") == "media_unavailable" for item in down.output)


@pytest.mark.parametrize("reason", ["logout", "revoked", "db_offline"])
def test_authority_loss_closes_upstream_not_just_ui(session, reason, monkeypatch):
    uid, sid, store, lease = session
    def action():
        if reason == "logout": db.revoke_session(sid)
        elif reason == "revoked": store.configure(uid, authorized=False, session_seconds=15, aggregate_seconds=30)
        else:
            def offline(*args): raise RuntimeError("private-db-error")
            monkeypatch.setattr(store, "require_lease", offline)
    clock = Clock()
    down, provider = Downstream(clock, action=action), Provider()
    run(session, down, provider, clock)
    assert provider.closed and down.closed
    assert "private-db-error" not in json.dumps(down.output)


def test_unconfirmed_provider_close_does_not_release_account_lease(session):
    clock = Clock()
    down, provider = Downstream(clock), Provider(confirmed=False)
    run(session, down, provider, clock)
    data = session[2].read(session[0])
    assert data["lease"]["state"] == "termination_unconfirmed"
    assert data["last_media"]["provider_close_ack"] is False


def test_unexpected_realtime_model_response_never_becomes_a_second_coach(session):
    clock = Clock()
    down = Downstream(clock)
    provider = Provider([{"type": "response.output_audio.delta", "delta": "private-unvalidated-audio"}])
    run(session, down, provider, clock)
    assert "private-unvalidated-audio" not in json.dumps(down.output)
    assert provider.closed


def test_partially_failed_provider_handshake_does_not_release_the_lease(session):
    uid, sid, store, lease = session
    clock = Clock()
    down = Downstream(clock)
    def failed(config): raise RuntimeError("private-handshake-detail")
    media.serve(down, uid, lease, store, db.get_session_user, lambda: True,
                realtime.session_config("bg"), factory=failed, clock=clock,
                wall=lambda: lease["deadline"] - 2)
    assert down.closed
    assert store.read(uid)["lease"]["state"] == "termination_unconfirmed"
    assert "private-handshake-detail" not in json.dumps(down.output)


def test_absolute_audio_budget_is_independent_of_pacing(session):
    uid, sid, store, lease = session
    clock = Clock()
    # An already-expiring reservation may never forward more audio than its
    # original allocation, even with a deliberately generous pacing clock.
    lease = dict(lease, seconds=1)
    down = Downstream(clock, [b"\0" * media.FRAME_BYTES] * 11)
    provider = Provider()
    media.serve(down, uid, lease, store, db.get_session_user, lambda: True,
                realtime.session_config("bg"), factory=lambda _: provider,
                clock=clock, wall=lambda: lease["deadline"] - 15)
    assert sum(len(frame) // 2 for frame in provider.frames) == media.SAMPLE_RATE
    assert provider.closed and down.closed
    assert store.read(uid)["last_media"]["accepted_samples"] == media.SAMPLE_RATE


@pytest.mark.parametrize("change", [
    {"max_output_tokens": "inf"}, {"max_output_tokens": 33},
    {"max_output_tokens": True}, {"output_modalities": ["audio"]},
    {"transcription_model": "different-model"}, {"rate": 16000},
    {"create_response": True}, {"tools": [{"type": "function"}]},
])
def test_provider_cost_contract_must_be_acknowledged_before_audio(monkeypatch, change):
    config = realtime.session_config("bg")
    actual = json.loads(json.dumps(config))
    for name, value in change.items():
        if name == "transcription_model": actual["audio"]["input"]["transcription"]["model"] = value
        elif name == "rate": actual["audio"]["input"]["format"]["rate"] = value
        elif name == "create_response": actual["audio"]["input"]["turn_detection"][name] = value
        else: actual[name] = value
    class Socket:
        sent = []
        shut = False
        def settimeout(self, _value): pass
        def send(self, value): self.sent.append(json.loads(value))
        def recv(self): return json.dumps({"type": "session.updated", "session": actual})
        def shutdown(self): self.shut = True
    sock = Socket()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-stub")
    monkeypatch.setattr(media.websocket, "create_connection", lambda *_args, **_kwargs: sock)
    with pytest.raises(RuntimeError, match="provider_(cost_contract|authority)_mismatch"):
        media.Upstream(config)
    assert sock.shut and [item["type"] for item in sock.sent] == ["session.update"]


def test_upstream_can_only_update_session_and_append_audio(monkeypatch):
    config = realtime.session_config("en")
    class Socket:
        def __init__(self): self.sent = []
        def settimeout(self, _value): pass
        def send(self, value): self.sent.append(json.loads(value))
        def recv(self): return json.dumps({"type": "session.updated", "session": config})
        def shutdown(self): pass
    sock = Socket()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-stub")
    monkeypatch.setattr(media.websocket, "create_connection", lambda *_args, **_kwargs: sock)
    upstream = media.Upstream(config)
    upstream.audio(b"\0" * media.FRAME_BYTES)
    assert [event["type"] for event in sock.sent] == ["session.update", "input_audio_buffer.append"]
    assert sock.sent[0]["session"]["max_output_tokens"] == 32
    assert sock.sent[0]["session"]["audio"]["input"]["turn_detection"]["create_response"] is False
