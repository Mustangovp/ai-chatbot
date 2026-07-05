"""
APEX Brain — decision-ledger wrapper (M0).

Failure-isolated wrapper over `db.log_decision`. Created inert: nothing calls it
until M1, when the first shadow decisions are recorded. It must never raise.
"""
import db as store


def log_decision(user_id, **kwargs):
    """Append one decision record to the ledger; never raises to the caller."""
    try:
        store.log_decision(user_id, **kwargs)
    except Exception as e:
        print(f"[ledger] log_decision failed: {e}")
