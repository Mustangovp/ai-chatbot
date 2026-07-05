"""
APEX — Athlete Model store (M0).

Thin, failure-isolated persistence glue between the pure `athlete_model` state
functions and the database. No Flask, no OpenAI.

Contract:
  • Reads are READ-ONLY: `load()` integrates the model in memory but never
    persists (so a read can never race or clobber a write).
  • Only `observe()` persists, and it is failure-isolated — it never raises to
    the caller (M0 exit-gate: observe must not throw in production).
"""
import db as store
import athlete_model as am


def load(user_id) -> dict:
    """Return the user's Athlete Model, integrated to now. READ-ONLY — never persists."""
    st = store.get_athlete_state(user_id) or am.fresh_state()
    return am.integrate(st)


def observe(user_id, fact, payload=None):
    """Apply one world-fact to the model and persist it. load → observe → save.
    Failure-isolated: logs and returns None on any error, never raises."""
    try:
        st = load(user_id)
        am.observe(st, fact, payload or {})
        store.save_athlete_state(user_id, st)
        return st
    except Exception as e:
        print(f"[athlete_store] observe failed (fact={fact}): {e}")
        return None


def prompt_block(user_id, lang="en"):
    """READ-ONLY: the [ATHLETE MODEL] prompt block for this user."""
    return am.prompt_block(load(user_id), lang)


def physiology(user_id):
    """READ-ONLY: the somatic projection {recovery, fatigue, stress}."""
    return am.project_physiology(load(user_id))


def signals(user_id):
    """READ-ONLY: confidence-gated coach signals."""
    return am.coach_signals(load(user_id))
