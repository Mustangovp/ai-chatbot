"""Controlled-release gates. SQLite process checks are not PostgreSQL runtime proof."""
import json
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import create_engine

import app as appmod
from voice import realtime
from voice.session_store import Denied, SessionStore
from voice.safety import SafetyStore


@pytest.fixture
def account(monkeypatch):
    uid = appmod.store.get_or_create_user("voice-security@example.invalid")
    sid = appmod.store.create_session(uid)
    monkeypatch.setenv("APEX_LIVE_VOICE_ENABLED", "true")
    monkeypatch.setenv("APEX_LIVE_VOICE_TRANSPORT", "relay")
    monkeypatch.setenv("APP_URL", "https://apexpulse.pro")
    control = SafetyStore(require_postgres=False)
    control.provision(uid, global_micro_usd=5_000_000, account_micro_usd=5_000_000,
                      max_operations=128, expires_at=time.time() + 3600)
    control.set_enabled(True)
    monkeypatch.setattr(realtime.charging, "control", control)
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, sid, domain="apexpulse.pro")
    return uid, sid, client


def offer(client, **changes):
    options = {"base_url": "https://apexpulse.pro", "headers": {"Origin": "https://apexpulse.pro"},
               "data": "v=0\r\ns=synthetic\r\n", "content_type": "application/sdp"}
    options.update(changes)
    return client.post("/api/live-voice/connect?lang=bg", **options)


@pytest.mark.parametrize("path,method", [("/live-voice-test", "get"),
    ("/api/live-voice/connect", "post"), ("/api/live-voice/stop", "post"),
    ("/api/live-voice/media", "get")])
def test_all_entry_points_deny_non_testers_and_browser_asserted_identity(account, path, method):
    uid, sid, client = account
    response = getattr(client, method)(path, base_url="https://apexpulse.pro",
        headers={"Origin": "https://apexpulse.pro", "X-Account-ID": str(uid)},
        query_string={"account_id": str(uid)})
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"


def test_authorization_uses_account_id_not_email(account):
    uid, sid, client = account
    other = appmod.store.get_or_create_user("other-voice-security@example.invalid")
    realtime.sessions.configure(other, authorized=True)
    assert offer(client).status_code == 403
    realtime.sessions.configure(uid, authorized=True)
    body = client.get("/live-voice-test", base_url="https://apexpulse.pro")
    assert body.status_code == 200
    assert '"enabled": true' in body.get_data(as_text=True)
    assert str(uid) not in body.get_data(as_text=True)


def test_flag_is_independent_and_default_off(account, monkeypatch):
    uid, sid, client = account
    realtime.sessions.configure(uid, authorized=True)
    monkeypatch.delenv("APEX_LIVE_VOICE_ENABLED")
    assert client.get("/live-voice-test", base_url="https://apexpulse.pro").status_code == 403
    assert offer(client).status_code == 403
    assert '"enabled": false' in client.get("/app", base_url="https://apexpulse.pro").get_data(as_text=True)


def test_shared_state_failure_never_falls_back_to_authorization(account, monkeypatch):
    uid, sid, client = account
    def unavailable(*args):
        raise RuntimeError("private-database-value")
    monkeypatch.setattr(realtime.sessions, "authorized", unavailable)
    response = offer(client)
    # Task 02.1 distinguishes unavailable authorization storage from a genuine
    # non-tester (403), while still denying access before provider submission.
    assert response.status_code == 503
    assert response.json == {"error": "pilot_unavailable", "terminal": True}
    assert "private-database-value" not in response.get_data(as_text=True)


def test_cross_origin_and_unknown_auth_session_are_rejected(account):
    uid, sid, client = account
    realtime.sessions.configure(uid, authorized=True)
    assert offer(client, headers={"Origin": "https://attacker.invalid"}).status_code == 403
    client.set_cookie(appmod.SESSION_COOKIE, str(uuid.uuid4()), domain="apexpulse.pro")
    assert offer(client).status_code == 403


def test_separate_processes_cannot_reserve_two_sessions(account, tmp_path):
    uid, sid, _ = account
    realtime.sessions.configure(uid, authorized=True)
    # Both independently imported processes/engines contend on the same DB row.
    script = """
import sys, time
from sqlalchemy import create_engine
from voice.session_store import SessionStore, Denied
store = SessionStore(create_engine(sys.argv[1], connect_args={'timeout': 10}))
while time.time() < float(sys.argv[4]): time.sleep(.002)
try:
    store.reserve(sys.argv[2], sys.argv[3])
    print('RESERVED')
except Denied as error:
    print(str(error))
"""
    start = time.time() + 2
    commands = [sys.executable, "-c", script, str(appmod.store.engine.url), str(uid), sid, str(start)]
    children = [subprocess.Popen(commands, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = []
    for child in children:
        output, error = child.communicate(timeout=20)
        assert child.returncode == 0, error
        results.append(output.strip())
    assert sorted(results) == ["RESERVED", "session_already_reserved"]
    fresh = SessionStore(create_engine(str(appmod.store.engine.url)))
    assert fresh.read(uid)["used_seconds"] == 120
    with pytest.raises(Denied, match="session_already_reserved"):
        fresh.reserve(uid, sid)


def test_two_independent_http_workers_cannot_create_direct_provider_sessions(account):
    uid, sid, _ = account
    realtime.sessions.configure(uid, authorized=True)
    script = """
import json, sys, time
import app as appmod
from voice import realtime
from voice.safety import SafetyStore
realtime.charging.control = SafetyStore(require_postgres=False)
calls = []
def exchange(*args):
    calls.append(True)
    return 'v=0\\r\\ns=synthetic\\r\\n', 'rtc_synthetic'
realtime.exchange_sdp = exchange
guard = realtime.SessionGuard(realtime.sessions, lambda _: None, appmod.store.get_session_user, lambda: True)
realtime.start_guardian = lambda: guard
client = appmod.app.test_client()
client.set_cookie(appmod.SESSION_COOKIE, sys.argv[1], domain='apexpulse.pro')
while time.time() < float(sys.argv[2]): time.sleep(.002)
reply = client.post('/api/live-voice/connect?lang=bg', base_url='https://apexpulse.pro',
    headers={'Origin':'https://apexpulse.pro'}, content_type='application/sdp', data='v=0\\r\\n')
print('RESULT:' + json.dumps({'status':reply.status_code,'provider_calls':len(calls)}))
"""
    start = time.time() + 4
    command = [sys.executable, "-c", script, sid, str(start)]
    children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = []
    for child in children:
        output, error = child.communicate(timeout=30)
        assert child.returncode == 0, error
        results.append(json.loads(next(line[7:] for line in output.splitlines() if line.startswith("RESULT:"))))
    assert [result["status"] for result in results] == [410, 410]
    assert sum(result["provider_calls"] for result in results) == 0
    assert realtime.sessions.read(uid)["used_seconds"] == 0


def test_budget_charged_atomically_and_cannot_reset_on_restart(account):
    uid, sid, _ = account
    realtime.sessions.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    for _ in range(2):
        lease = realtime.sessions.reserve(uid, sid)
        realtime.sessions.attach(uid, lease["id"], "rtc_synthetic")
        realtime.sessions.finish(uid, lease["id"], provider_confirmed=True)
    restarted = SessionStore(create_engine(str(appmod.store.engine.url)))
    with pytest.raises(Denied, match="usage_exhausted"):
        restarted.reserve(uid, sid)
    assert restarted.read(uid)["used_seconds"] == 30


def test_expired_unconfirmed_provider_session_never_releases_next_lease(account):
    uid, sid, _ = account
    clock = [1000.0]
    store = SessionStore(appmod.store.engine, clock=lambda: clock[0])
    store.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    lease = store.reserve(uid, sid)
    store.attach(uid, lease["id"], "rtc_synthetic")
    clock[0] += 16
    with pytest.raises(Denied, match="session_already_reserved"):
        store.reserve(uid, sid)
    store.finish(uid, lease["id"], provider_confirmed=False)
    with pytest.raises(Denied, match="session_already_reserved"):
        SessionStore(appmod.store.engine, clock=lambda: clock[0]).reserve(uid, sid)


@pytest.mark.parametrize("reason", ["expiration", "logout", "revocation", "flag_off", "budget"])
def test_guard_terminates_upstream_before_releasing_authority(account, reason):
    uid, sid, _ = account
    clock = [1000.0]
    store = SessionStore(appmod.store.engine, clock=lambda: clock[0])
    store.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    lease = store.reserve(uid, sid)
    store.attach(uid, lease["id"], "rtc_synthetic")
    calls = []
    def terminate(call_id):
        # Still reserved until provider has ACKed. A browser stop is not enough.
        assert store.read(uid)["lease"]["id"] == lease["id"]
        calls.append(call_id)
    guard = realtime.SessionGuard(store, terminate, appmod.store.get_session_user,
                                  lambda: reason != "flag_off", clock=lambda: clock[0])
    if reason == "expiration": clock[0] += 16
    if reason == "logout": appmod.store.revoke_session(sid)
    if reason == "revocation": store.configure(uid, authorized=False, session_seconds=15, aggregate_seconds=30)
    if reason == "budget":
        with store.locked(uid) as data: data["used_seconds"] = 31
    assert guard.tick() is True
    assert calls == ["rtc_synthetic"]
    assert store.read(uid)["lease"] is None


def test_failed_provider_hangup_is_bounded_and_blocks_new_session(account):
    uid, sid, _ = account
    clock = [1000.0]
    store = SessionStore(appmod.store.engine, clock=lambda: clock[0])
    store.configure(uid, authorized=True)
    lease = store.reserve(uid, sid)
    store.attach(uid, lease["id"], "rtc_synthetic")
    calls = []
    def fail(call_id):
        calls.append(call_id)
        raise RuntimeError("private-provider-error")
    guard = realtime.SessionGuard(store, fail, lambda _: None, lambda: True, clock=lambda: clock[0])
    for _ in range(10):
        guard.tick()
        clock[0] += 11
    assert calls == ["rtc_synthetic"] * 2
    assert store.read(uid)["lease"]["state"] == "termination_unconfirmed"
    with pytest.raises(Denied, match="session_already_reserved"):
        store.reserve(uid, sid)


def test_provider_hangup_uses_server_key_fixed_host_and_bounded_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    calls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def send(request, timeout):
        calls.append(request.full_url)
        assert timeout == 5
        assert request.get_header("Authorization") == "Bearer synthetic-secret"
        return Response()
    monkeypatch.setattr(realtime.urlrequest, "urlopen", send)
    realtime.hangup_call("rtc_synthetic")
    assert calls == ["https://api.openai.com/v1/realtime/calls/rtc_synthetic/hangup"]
    with pytest.raises(ValueError): realtime.hangup_call("https://attacker.invalid")


def test_shared_state_outage_terminates_known_call_without_unlocking(account, monkeypatch):
    uid, sid, _ = account
    store = SessionStore(appmod.store.engine)
    store.configure(uid, authorized=True)
    lease = store.reserve(uid, sid)
    lease = store.attach(uid, lease["id"], "rtc_synthetic")
    calls = []
    guard = realtime.SessionGuard(store, calls.append, appmod.store.get_session_user, lambda: True)
    guard.known[(str(uid), lease["id"])] = lease
    def unavailable(*args, **kwargs):
        raise RuntimeError("shared-state-offline")
    monkeypatch.setattr(store, "active", unavailable)
    monkeypatch.setattr(store, "claim_stop", unavailable)
    monkeypatch.setattr(store, "finish", unavailable)
    assert guard.tick() is False
    assert calls == ["rtc_synthetic"]
    assert realtime.sessions.read(uid)["lease"]["id"] == lease["id"]


def test_actual_logout_revokes_identity_and_calls_provider_hangup(account, monkeypatch):
    uid, sid, client = account
    realtime.sessions.configure(uid, authorized=True)
    lease = realtime.sessions.reserve(uid, sid)
    realtime.sessions.attach(uid, lease["id"], "rtc_synthetic")
    calls = []
    monkeypatch.setattr(realtime, "hangup_call", calls.append)
    response = client.post("/auth/logout", base_url="https://apexpulse.pro")
    assert response.status_code == 200
    assert appmod.store.get_session_user(sid) is None
    assert calls == ["rtc_synthetic"]
    assert realtime.sessions.read(uid)["lease"] is None


def test_logout_does_not_claim_provider_shutdown_when_hangup_fails(account, monkeypatch):
    uid, sid, client = account
    realtime.sessions.configure(uid, authorized=True)
    lease = realtime.sessions.reserve(uid, sid)
    realtime.sessions.attach(uid, lease["id"], "rtc_synthetic")
    def unavailable(*args):
        raise RuntimeError("private-upstream-error")
    monkeypatch.setattr(realtime, "hangup_call", unavailable)
    response = client.post("/auth/logout", base_url="https://apexpulse.pro")
    assert response.status_code == 503
    assert appmod.store.get_session_user(sid) is None
    assert "private-upstream-error" not in response.get_data(as_text=True)
    assert realtime.sessions.read(uid)["lease"]["state"] == "termination_unconfirmed"


def test_non_tester_logout_does_not_consume_or_terminate_another_account_session(account, monkeypatch):
    uid, sid, client = account
    other = appmod.store.get_or_create_user("separate-tester@example.invalid")
    realtime.sessions.configure(other, authorized=True)
    lease = realtime.sessions.reserve(other, "synthetic-other-session")
    realtime.sessions.attach(other, lease["id"], "rtc_other")
    monkeypatch.setattr(realtime, "hangup_call", lambda _: pytest.fail("other account's session must not be affected"))
    response = client.post("/auth/logout", base_url="https://apexpulse.pro")
    assert response.status_code == 200
    assert appmod.store.get_session_user(sid) is None
    assert realtime.sessions.read(other)["lease"]["id"] == lease["id"]


def test_private_control_state_is_not_account_profile_or_coaching_preferences(account):
    uid, sid, _ = account
    realtime.sessions.configure(uid, authorized=True)
    realtime.sessions.reserve(uid, sid)
    assert appmod.store.get_profile(uid) in (None, {})
    assert appmod.store.get_preferences("user:" + str(uid)) is None
    assert appmod.store.get_preferences("voice-test:" + str(uid))["lease"]


def test_stop_cannot_reference_another_accounts_lease(account, monkeypatch):
    uid, sid, client = account
    other = appmod.store.get_or_create_user("other-authorized@example.invalid")
    realtime.sessions.configure(uid, authorized=True)
    realtime.sessions.configure(other, authorized=True)
    lease = realtime.sessions.reserve(other, "synthetic-other-session")
    response = client.post("/api/live-voice/stop", base_url="https://apexpulse.pro",
                           headers={"Origin": "https://apexpulse.pro"}, json={"lease": lease["id"], "account_id": str(other)})
    assert response.status_code == 403
    assert realtime.sessions.read(other)["lease"]["id"] == lease["id"]
