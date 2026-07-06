"""§7.4 — the ledger writes a row when called; the wrapper never raises."""
import db as store
import brain.ledger as ledger
from sqlalchemy import select, func


def test_log_decision_writes_row():
    uid = store.get_or_create_user("ledger@example.com")
    store.log_decision(uid, verdict="GO", intervention="training",
                       enforced=False, message_hash="abc123")
    with store.engine.begin() as c:
        rows = c.execute(select(func.count()).select_from(store.brain_decisions)
                         .where(store.brain_decisions.c.user_id == store._as_uuid(uid))).scalar()
    assert rows == 1


def test_ledger_wrapper_never_raises():
    # anonymous (user_id=None) is allowed; a bad kwarg is swallowed by the wrapper.
    ledger.log_decision(None, verdict="GO")
    ledger.log_decision("not-a-uuid", verdict="GO")  # invalid id → swallowed, no raise
