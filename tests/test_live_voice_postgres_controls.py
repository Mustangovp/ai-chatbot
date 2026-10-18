"""Opt-in real PostgreSQL, separate-process control tests. Never production DB."""
import datetime
import os
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import create_engine, delete

import db
from voice.safety import SUBJECT, SafetyStore
from voice.session_store import Denied


@pytest.fixture
def postgres(request):
    url = os.getenv("APEX_VOICE_TEST_POSTGRES_URL")
    if not url: pytest.skip("isolated PostgreSQL URL not supplied")
    if url != "postgresql+psycopg://postgres@127.0.0.1:55439/apex_voice_test":
        pytest.fail("only the explicitly isolated localhost test cluster is permitted")
    engine = create_engine(url)
    db.metadata.create_all(engine)
    uid, sid = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(delete(db.user_preferences).where(db.user_preferences.c.subject == SUBJECT))
        connection.execute(db.users.insert().values(id=uid, email="pg-safety-" + uid.hex + "@example.invalid"))
        connection.execute(db.sessions.insert().values(id=sid, user_id=uid,
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)))
    policy = SafetyStore(engine)
    config = getattr(request, "param", 1500)
    global_limit = config["global"] if isinstance(config, dict) else 2000
    account_limit = config["account"] if isinstance(config, dict) else config
    policy.provision(uid, global_micro_usd=global_limit, account_micro_usd=account_limit,
                     max_operations=10, expires_at=time.time() + 60)
    policy.set_enabled(True)
    yield str(uid), str(sid), policy, url
    engine.dispose()


def child(url, uid, sid, action, start, maximum=1000):
    script = """
import os,sys,time
os.environ['DATABASE_URL']=sys.argv[1]
from sqlalchemy import create_engine
from voice.safety import SafetyStore
from voice.session_store import Denied
store=SafetyStore(create_engine(sys.argv[1]))
while time.time()<float(sys.argv[5]): time.sleep(.001)
try:
    if sys.argv[4]=='off': store.set_enabled(False); print('OFF')
    elif sys.argv[4]=='exhaust':
        store.reserve(sys.argv[2],sys.argv[3],'gpt6',1000)
        store.reserve(sys.argv[2],sys.argv[3],'gpt6',1000)
    elif sys.argv[4]=='pilot':
        store.reserve(sys.argv[2],sys.argv[3],'tts',100000,tts_pilot=True); print('RESERVED')
    else: store.reserve(sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[6])); print('RESERVED')
except Denied: print('DENIED')
"""
    return subprocess.Popen([sys.executable, "-c", script, url, uid, sid, action, str(start), str(maximum)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def output(process):
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, stderr
    return stdout.strip()


@pytest.mark.parametrize("postgres", [1500, 3000], indirect=True)
def test_postgres_independent_workers_race_last_global_and_account_budget(postgres):
    uid, sid, policy, url = postgres
    policy.reserve(uid, sid, "transcription", 500)
    start = time.time() + 2
    workers = [child(url, uid, sid, "gpt6", start) for _ in range(2)]
    assert sorted(output(worker) for worker in workers) == ["DENIED", "RESERVED"]
    data = SafetyStore(create_engine(url)).read()
    assert data["global_used"] == data["account_used"] == 1500
    assert data["operation_count"] == 2
    with pytest.raises(Denied): policy.reserve(uid, sid, "tts", 1)


def test_postgres_three_operation_types_share_allocation_and_restart_retains_it(postgres):
    uid, sid, policy, url = postgres
    for kind in ("transcription", "gpt6", "tts"): policy.reserve(uid, sid, kind, 400)
    fresh = SafetyStore(create_engine(url))
    assert fresh.read()["global_used"] == fresh.read()["account_used"] == 1200
    assert {item["kind"] for item in fresh.read()["operations"].values()} == {"transcription", "gpt6", "tts"}
    with pytest.raises(Denied): fresh.reserve(uid, sid, "gpt6", 400)
    assert fresh.read()["enabled"] is False


def test_postgres_other_process_kills_existing_grant_and_restart_stays_off(postgres):
    uid, sid, policy, url = postgres
    grant = policy.reserve(uid, sid, "transcription", 400)
    assert output(child(url, uid, sid, "off", time.time())) == "OFF"
    with pytest.raises(Denied): policy.require(uid, grant["epoch"])
    fresh = SafetyStore(create_engine(url))
    assert fresh.read()["enabled"] is False
    with pytest.raises(Denied): fresh.reserve(uid, sid, "gpt6", 1)
    # A newly started Python worker cannot reset the durable OFF/budget state.
    assert output(child(url, uid, sid, "gpt6", time.time())) == "DENIED"


def test_postgres_unavailable_fails_closed_without_local_authority():
    dead = SafetyStore(create_engine("postgresql+psycopg://postgres@127.0.0.1:1/apex_voice_test",
                                   connect_args={"connect_timeout": 1}))
    with pytest.raises(Exception): dead.require(str(uuid.uuid4()))


def test_postgres_tts_concurrency_and_attempt_budget_survive_worker_restart(postgres):
    uid, sid, policy, url = postgres
    start = time.time() + 2
    workers = [child(url, uid, sid, "tts", start, maximum=200) for _ in range(2)]
    assert sorted(output(worker) for worker in workers) == ["DENIED", "RESERVED"]
    fresh = SafetyStore(create_engine(url))
    data = fresh.read()
    assert data["global_used"] == data["account_used"] == 200
    assert data["operation_count"] == 1
    ident = next(iter(data["operations"]))
    grant = {"id": ident, "epoch": data["epoch"], "maximum": 200}
    # Unknown worker/provider outcome is not reclaimed automatically.
    assert output(child(url, uid, sid, "tts", time.time(), maximum=200)) == "DENIED"
    fresh.tts_submitted(grant)
    fresh.finish_tts(grant)
    for _ in range(3):
        grant = fresh.reserve(uid, sid, "tts", 200)
        fresh.finish_tts(grant, unused=True)
    assert output(child(url, uid, sid, "tts", time.time(), maximum=200)) == "DENIED"
    assert fresh.read()["operation_count"] == 4
    assert fresh.read()["global_used"] == 200


@pytest.mark.parametrize("postgres", [{"global": 1_000_000, "account": 1_000_000}], indirect=True)
def test_postgres_pilot_four_cross_worker_races_cannot_exceed_allocation(postgres):
    uid, sid, policy, url = postgres
    policy.set_enabled(False)
    policy.approve_tts_pilot(uid)
    policy.set_enabled(True)
    for attempt in range(1, 5):
        workers = [child(url, uid, sid, "pilot", time.time() + 2) for _ in range(2)]
        assert sorted(output(worker) for worker in workers) == ["DENIED", "RESERVED"]
        fresh = SafetyStore(create_engine(url))
        data = fresh.read()
        assert data["operation_count"] == attempt and data["global_used"] == attempt * 100_000
        ident = next(key for key, op in data["operations"].items() if op["tts_open"])
        grant = {"id": ident, "epoch": data["epoch"], "maximum": 100_000}
        fresh.tts_submitted(grant)
        fresh.finish_tts(grant)
    assert output(child(url, uid, sid, "pilot", time.time())) == "DENIED"
    policy.approve_tts_pilot(uid)
    assert policy.read()["global_used"] == policy.read()["account_used"] == 400_000
    assert policy.read()["operation_count"] == 4


@pytest.mark.parametrize("action", ["off", "exhaust"])
def test_postgres_live_media_worker_observes_another_workers_off_switch(postgres, action):
    import json
    from voice.session_store import SessionStore
    uid, sid, policy, url = postgres
    sessions = SessionStore(policy.engine)
    sessions.configure(uid, authorized=True, session_seconds=15, aggregate_seconds=30)
    lease = sessions.reserve(uid, sid)
    grant = policy.reserve(uid, sid, "transcription", 100)
    script = """
import os,sys,json,time
os.environ['DATABASE_URL']=sys.argv[1]
from voice import media,realtime
from voice.safety import SafetyStore
from voice.session_store import SessionStore
import db
control=SafetyStore()
store=SessionStore()
class Down:
    def send(self,text):
        if json.loads(text).get('type')=='session.ready': print('MEDIA_READY',flush=True)
    def receive(self,timeout): time.sleep(.02); return None
    def close(self): pass
class Provider:
    def __init__(self): self.closed=False
    def receive(self): time.sleep(.01); return None
    def close(self): self.closed=True; return True
    def abort(self): self.closed=True
provider=Provider()
started=time.monotonic()
media.serve(Down(),sys.argv[2],json.loads(sys.argv[3]),store,db.get_session_user,lambda:True,
            realtime.session_config('bg'),factory=lambda _:provider,
            safety=(control,json.loads(sys.argv[4])))
print(json.dumps({'closed':provider.closed,'elapsed':time.monotonic()-started,
                  'lease_released':store.read(sys.argv[2])['lease'] is None}),flush=True)
"""
    process = subprocess.Popen([sys.executable, "-u", "-c", script, url, uid, json.dumps(lease), json.dumps(grant)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "MEDIA_READY"
        assert output(child(url, uid, sid, action, time.time())) == ("OFF" if action == "off" else "DENIED")
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr
        result = json.loads(stdout.strip())
        assert result["closed"] and result["lease_released"] and result["elapsed"] < 4
    finally:
        if process.poll() is None: process.kill(); process.wait(5)
