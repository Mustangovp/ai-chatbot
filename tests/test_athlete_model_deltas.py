"""§7.5 — pin a couple of pure athlete_model observe deltas (no DB)."""
import athlete_model as am


def test_workout_raises_physical_fatigue():
    st = am.fresh_state()
    before = st["vars"]["physical_fatigue"]["value"]
    am.observe(st, "workout_completed", {"exercises": [{"name": "squat", "sets": "5", "reps": "5"}]})
    assert st["vars"]["physical_fatigue"]["value"] > before


def test_self_report_poor_sleep_lowers_sleep_quality():
    st = am.fresh_state()
    before = st["vars"]["sleep_quality"]["value"]
    am.observe(st, "self_report", {"sleepQuality": "poor"})
    assert st["vars"]["sleep_quality"]["value"] < before


def test_bounded_step_never_jumps():
    # A single observation may not move a value more than MAX_STEP of the way.
    st = am.fresh_state()
    base = st["vars"]["physical_fatigue"]["value"]
    am.observe(st, "workout_completed", {"exercises": [{"name": "x", "sets": "20"}]})
    moved = st["vars"]["physical_fatigue"]["value"] - base
    assert 0 < moved <= (1.0 - base) * am.MAX_STEP + 1e-9
