"""§7.3 — athlete_store: fresh load, observe persists + moves value, reads never
persist, observe never raises on malformed input."""
import athlete_store
import db as store
import athlete_model as am


def _uid(email="store@example.com"):
    return store.get_or_create_user(email)


def test_fresh_load_returns_fresh_state():
    uid = _uid()
    st = athlete_store.load(uid)
    assert st["schema"] == am.SCHEMA
    assert "vars" in st and "physical_fatigue" in st["vars"]


def test_observe_workout_persists_and_raises_fatigue():
    uid = _uid()
    before = athlete_store.load(uid)["vars"]["physical_fatigue"]["value"]
    athlete_store.observe(uid, "workout_completed",
                          {"exercises": [{"name": "squat", "sets": "5", "reps": "5", "weight": "100"}]})
    after = store.get_athlete_state(uid)                     # must be persisted
    assert after is not None
    assert after["vars"]["physical_fatigue"]["value"] > before


def test_reads_never_persist():
    uid = _uid()
    old = am.fresh_state()
    old["updated_at"] = "2020-01-01T00:00:00+00:00"
    store.save_athlete_state(uid, old)
    athlete_store.load(uid)                                  # integrates in memory only
    raw = store.get_athlete_state(uid)
    assert raw["updated_at"] == "2020-01-01T00:00:00+00:00"  # unchanged on disk


def test_observe_malformed_does_not_raise():
    uid = _uid()
    # exercises is a string, not a list → athlete_model would raise internally;
    # athlete_store must isolate it and return None, never propagate.
    res = athlete_store.observe(uid, "workout_completed", {"exercises": "not-a-list"})
    assert res is None
