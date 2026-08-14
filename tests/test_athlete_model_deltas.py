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


def test_core_presence_projection_is_bounded_and_confidence_gated():
    st = am.fresh_state()
    st["vars"]["physical_fatigue"].update(value=0.80, confidence=0.60)
    st["vars"]["motivation"].update(value=0.75, confidence=0.50)

    projection = am.core_presence_projection(st)

    assert projection == {"recovery_bias": "protective", "attention_bias": "focused"}
    assert not {"value", "confidence", "source", "stress", "fatigue"} & set(projection)


def test_core_presence_projection_omits_low_confidence_estimates():
    st = am.fresh_state()
    st["vars"]["physical_fatigue"].update(value=0.95, confidence=0.20)
    st["vars"]["motivation"].update(value=0.95, confidence=0.20)

    assert am.core_presence_projection(st) is None
