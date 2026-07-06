"""§7.2 — athlete_models get/save round-trip, upsert (not duplicate), uniqueness."""
import db as store
from sqlalchemy import select, func


def _uid(email="athlete_model@example.com"):
    return store.get_or_create_user(email)


def test_get_absent_returns_none():
    uid = _uid("absent@example.com")
    assert store.get_athlete_state(uid) is None


def test_save_then_get_roundtrip():
    uid = _uid()
    state = {"schema": "athlete-model-v1",
             "vars": {"physical_fatigue": {"value": 0.5, "confidence": 0.3}},
             "updated_at": "2026-01-01T00:00:00+00:00"}
    store.save_athlete_state(uid, state)
    got = store.get_athlete_state(uid)
    assert got is not None
    assert got["vars"]["physical_fatigue"]["value"] == 0.5


def test_upsert_updates_not_duplicates():
    uid = _uid()
    store.save_athlete_state(uid, {"schema": "athlete-model-v1", "n": 1})
    store.save_athlete_state(uid, {"schema": "athlete-model-v1", "n": 2})
    got = store.get_athlete_state(uid)
    assert got["n"] == 2
    with store.engine.begin() as c:
        rows = c.execute(select(func.count()).select_from(store.athlete_models)
                         .where(store.athlete_models.c.user_id == store._as_uuid(uid))).scalar()
    assert rows == 1
