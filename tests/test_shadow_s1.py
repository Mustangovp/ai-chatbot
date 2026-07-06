"""
M1 — S1 shadow-pipeline wiring (v2 inspector trace).
BRAIN_SHADOW OFF (default) writes nothing; ON writes one traceable S1 record
whose decision_id matches the ledger row id.
"""
import json
import types
import app as app_module
import db as store
from sqlalchemy import select


def _mock_openai(monkeypatch, reply="Good work. Controlled tempo."):
    NS = types.SimpleNamespace
    monkeypatch.setattr(app_module, "client",
                        NS(chat=NS(completions=NS(
                            create=lambda *a, **k: [NS(choices=[NS(delta=NS(content=reply))])]))))


def _brain_rows():
    with store.engine.begin() as c:
        return c.execute(select(store.brain_decisions)).mappings().all()


def _trace(row):
    tr = row["trace"]
    return json.loads(tr) if isinstance(tr, str) else tr


def test_shadow_off_writes_nothing(monkeypatch):
    monkeypatch.delenv("BRAIN_SHADOW", raising=False)
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={"message": "make me a workout", "lang": "en",
                                   "profile": {"healthNotes": "prior stroke, high blood pressure"}})
    assert r.status_code == 200
    r.get_data()
    assert len(_brain_rows()) == 0


def test_shadow_on_writes_one_traceable_record(monkeypatch):
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={
        "message": "make me a workout", "lang": "en",
        "profile": {"age": 69, "level": "beginner", "activityLevel": "sedentary",
                    "healthNotes": "prior stroke, high blood pressure"}})
    assert r.status_code == 200
    r.get_data()

    rows = _brain_rows()
    assert len(rows) == 1
    row = rows[0]
    assert not row["enforced"]
    assert row["verdict"] is None

    tr = _trace(row)
    # Decision ID is stable: trace id == ledger row id.
    assert tr["decision_id"] == str(row["id"])
    assert tr["trace_schema"] == "brain-trace-v2"
    assert "S1" in tr["cascade"]["stations_executed"]
    s1 = tr["stations"]["S1"]
    assert s1["executed"] is True
    assert "stroke_history" in s1["evidence_changed_state"]["detected_conditions"]
    assert any(c["movement"] == "valsalva" and c["tier"] == "absolute" for c in s1["constraints_added"])
    assert s1["envelope"]["supported"] is True
    # S2 now runs in the same shadow pass.
    assert tr["stations"]["S2"]["executed"] is True


def test_shadow_on_logs_s2_red_flag_and_halt(monkeypatch):
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={
        "message": "i get a tight, heavy feeling in my chest going uphill — make me a workout",
        "lang": "en", "profile": {}})
    assert r.status_code == 200
    r.get_data()
    tr = _trace(_brain_rows()[0])
    s2 = tr["stations"]["S2"]
    assert s2["halt"] is True and tr["cascade"]["halt"] is True
    assert any(f["class_key"] == "exertional_chest" for f in s2["red_flags"])


def test_shadow_on_anonymous_logs_with_null_user(monkeypatch):
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={"message": "workout please", "lang": "en",
                                   "profile": {"healthNotes": "osteoporosis"}})
    assert r.status_code == 200
    r.get_data()
    rows = _brain_rows()
    assert len(rows) == 1
    assert rows[0]["user_id"] is None
    s1 = _trace(rows[0])["stations"]["S1"]
    assert "loaded_spinal_flexion" in [c["movement"] for c in s1["constraints_added"]]
