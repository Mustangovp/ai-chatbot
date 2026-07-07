"""
BUILD-001 — Human State ingestion: unit + regression.
Extractor, confidence, TTL rules, never-downgrade, conflict resolution, view,
feature flag, and Brain-independence.
"""
import datetime as _dt

import human_state
from human_state import extractor, engine
from human_state.schema import Reading, CONF_NUMERIC, CONF_EXPLICIT, CONF_HEDGED, KEY_TTL
import db as store


UTC = _dt.timezone.utc
def _t(**kw):
    return _dt.datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC) + _dt.timedelta(**kw)


def _keys(readings):
    return {r.key: r for r in readings}


# ── Extractor ────────────────────────────────────────────────────────────────
def test_extract_core_signals():
    k = _keys(extractor.extract("I've slept 4 hours and I'm exhausted, my knee hurts"))
    assert k["sleep"].value == "4" and k["sleep"].confidence == CONF_NUMERIC
    assert k["fatigue"].value == "high" and k["fatigue"].confidence == CONF_EXPLICIT
    assert k["pain"].key == "pain" and "knee" in k["pain"].note


def test_extract_time_illness_travel_motivation():
    assert _keys(extractor.extract("I only have 15 minutes today"))["time_availability"].value == "15"
    assert "illness" in _keys(extractor.extract("I'm sick with the flu"))
    assert "travel" in _keys(extractor.extract("I'm travelling for work this week"))
    assert _keys(extractor.extract("I have no motivation, I want to quit"))["motivation"].value == "low"


def test_extract_preferences_multivalue():
    rs = extractor.extract("I hate oats but I love eggs")
    prefs = [r for r in rs if r.key == "preference"]
    vals = [r.value for r in prefs]
    assert {"avoid": "oats"} in vals and {"prefer": "eggs"} in vals


def test_extract_benign_message_is_empty():
    assert extractor.extract("what time are you open") == []


def test_ttl_assigned_by_key():
    r = extractor.extract("my back is sore")[0]
    assert r.key == "pain" and r.ttl_seconds == KEY_TTL["pain"]


# ── Confidence ordering ──────────────────────────────────────────────────────
def test_confidence_tiers_ordered():
    assert CONF_NUMERIC > CONF_EXPLICIT > CONF_HEDGED


# ── Engine: never-downgrade, TTL, conflict ───────────────────────────────────
def test_never_overwrite_high_conf_with_low_conf():
    now = _t()
    engine.apply("device:a", [Reading("fatigue", "high", CONF_EXPLICIT, observed_at=now)], now)
    # a later, lower-confidence inference must NOT overwrite the live high-confidence value
    later = now + _dt.timedelta(minutes=5)
    res = engine.apply("device:a", [Reading("fatigue", "moderate", CONF_HEDGED, observed_at=later)], later)
    assert res["kept"] == ["fatigue"] and res["applied"] == []
    assert store.hs_get("device:a", "fatigue")["value"] == "high"


def test_higher_conf_overwrites():
    now = _t()
    engine.apply("device:b", [Reading("sleep", "low", CONF_HEDGED, observed_at=now)], now)
    res = engine.apply("device:b", [Reading("sleep", "8", CONF_NUMERIC, observed_at=now)], now)
    assert res["applied"] == ["sleep"]
    assert store.hs_get("device:b", "sleep")["value"] == "8"


def test_expired_value_yields_to_fresh_even_if_lower_conf():
    now = _t()
    old = now - _dt.timedelta(days=2)          # fatigue TTL is 1 day → expired
    store.hs_upsert("device:c", "fatigue", "high", CONF_EXPLICIT, "message", old, KEY_TTL["fatigue"])
    res = engine.apply("device:c", [Reading("fatigue", "moderate", CONF_HEDGED, observed_at=now)], now)
    assert res["applied"] == ["fatigue"]
    assert store.hs_get("device:c", "fatigue")["value"] == "moderate"


def test_effective_confidence_decays():
    now = _t()
    store.hs_upsert("device:d", "stress", "high", 0.8, "message",
                    now - _dt.timedelta(hours=12), KEY_TTL["stress"])   # half of 24h TTL
    eff = engine.effective_confidence(store.hs_get("device:d", "stress"), now)
    assert 0.35 < eff < 0.45                     # ~0.8 * 0.5


# ── View ─────────────────────────────────────────────────────────────────────
def test_view_marks_stale_not_fresh():
    now = _t()
    store.hs_upsert("device:e", "pain", "present", 0.8, "message",
                    now - _dt.timedelta(days=5), KEY_TTL["pain"])       # long expired
    v = human_state.view("device:e", now=now)
    assert v["pain"]["fresh"] is False and v["pain"]["confidence"] == 0.0


# ── ingest() end-to-end ──────────────────────────────────────────────────────
def test_ingest_writes_state():
    now = _t()
    human_state.ingest("device:f", "I'm exhausted and only have 20 minutes", now=now)
    v = human_state.view("device:f", now=now)
    assert v["fatigue"]["value"] == "high" and v["time_availability"]["value"] == "20"
    assert v["fatigue"]["fresh"] is True


# ── Feature flag ─────────────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("HSE_INGEST", raising=False)
    assert human_state.enabled() is False
    monkeypatch.setenv("HSE_INGEST", "1")
    assert human_state.enabled() is True


# ── Brain independence (regression) ──────────────────────────────────────────
def test_ingestion_does_not_touch_the_brain():
    from brain import cascade
    profile = {"healthNotes": "high blood pressure", "goal": "strength"}
    before = cascade.decide(profile, message="give me a workout")
    human_state.ingest("device:g", "I'm exhausted, my knee hurts, I want to quit", now=_t())
    after = cascade.decide(profile, message="give me a workout")
    # the Brain reads athlete_models, never human_state → identical decision
    assert (before.verdict, before.halt, before.generate_training) == \
           (after.verdict, after.halt, after.generate_training)
    # ingestion wrote to human_state but NOTHING to the Brain's athlete_models substrate
    assert store.hs_get_all("device:g")
    with store.engine.begin() as c:
        n = c.execute(store.select(store.func.count()).select_from(store.athlete_models)).scalar()
    assert n == 0
