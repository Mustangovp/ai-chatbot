"""
M1 Commit 3 — developer inspection endpoint. Must be 404 unless BRAIN_DEBUG is
set (never exposed in production), and must inspect stored decisions + replay
from provided evidence when enabled.
"""
import types
import app as app_module
import db as store
from sqlalchemy import select


def _mock_openai(monkeypatch, reply="Good work."):
    NS = types.SimpleNamespace
    monkeypatch.setattr(app_module, "client",
                        NS(chat=NS(completions=NS(
                            create=lambda *a, **k: [NS(choices=[NS(delta=NS(content=reply))])]))))


def test_endpoints_404_when_debug_off(monkeypatch):
    monkeypatch.delenv("BRAIN_DEBUG", raising=False)
    client = app_module.app.test_client()
    assert client.get("/debug/brain/decision/abc").status_code == 404
    assert client.post("/debug/brain/replay", json={"profile": {}}).status_code == 404


def test_replay_from_evidence_when_debug_on(monkeypatch):
    monkeypatch.setenv("BRAIN_DEBUG", "1")
    client = app_module.app.test_client()
    r = client.post("/debug/brain/replay",
                    json={"profile": {"healthNotes": "stroke, hypertension"}, "model": "gpt-4o"})
    assert r.status_code == 200
    tr = r.get_json()
    assert tr["stations"]["S1"]["executed"] is True
    assert any(c["movement"] == "valsalva" for c in tr["stations"]["S1"]["constraints_added"])
    assert tr["versions"]["model"] == "gpt-4o"


def test_inspect_stored_decision_by_id(monkeypatch):
    # Create a real shadow decision, then fetch it by its stable Decision ID.
    monkeypatch.setenv("BRAIN_SHADOW", "1")
    monkeypatch.setenv("BRAIN_DEBUG", "1")
    _mock_openai(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/chat", json={"message": "workout", "lang": "en",
                                   "profile": {"healthNotes": "osteoporosis"}})
    assert r.status_code == 200
    r.get_data()
    with store.engine.begin() as c:
        row = c.execute(select(store.brain_decisions)).mappings().first()
    did = str(row["id"])

    got = client.get(f"/debug/brain/decision/{did}")
    assert got.status_code == 200
    payload = got.get_json()
    assert payload["id"] == did
    assert payload["trace"]["decision_id"] == did
    assert payload["trace"]["stations"]["S1"]["executed"] is True


def test_unknown_decision_id_404_when_debug_on(monkeypatch):
    monkeypatch.setenv("BRAIN_DEBUG", "1")
    client = app_module.app.test_client()
    r = client.get("/debug/brain/decision/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
