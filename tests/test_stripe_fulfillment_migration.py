"""v30 adds event identity/outcomes without rewriting historical authority."""
import pytest
from sqlalchemy import inspect, select, text

import db as store
from test_payment_security_migration import legacy_database, versions


def v29_database(monkeypatch):
    engine = legacy_database(monkeypatch)
    with engine.begin() as connection:
        store._ensure_payment_security_schema(connection)
        connection.execute(text('INSERT INTO schema_version (version) VALUES (29)'))
    return engine


def test_v30_upgrade_is_additive_and_preserves_legacy_purchase(monkeypatch):
    engine = v29_database(monkeypatch)
    with engine.connect() as connection:
        before = dict(connection.execute(text('SELECT * FROM payments')).mappings().one())
    store.run_migrations()
    store.run_migrations()
    with engine.connect() as connection:
        after = dict(connection.execute(text('SELECT * FROM payments')).mappings().one())
        assert not connection.execute(select(store.stripe_event_receipts)).all()
        assert not connection.execute(select(store.stripe_payment_intents)).all()
    assert all(after[key] == value for key, value in before.items())
    assert after['refund_attempt_count'] == 0 and after['refund_status'] is None
    assert 30 in versions(engine)
    assert inspect(engine).get_pk_constraint('stripe_event_receipts')['constrained_columns'] == ['event_id']
    assert inspect(engine).get_pk_constraint('stripe_payment_intents')['constrained_columns'] == ['payment_intent_id']


def test_failed_v30_verification_is_not_recorded(monkeypatch):
    engine = v29_database(monkeypatch)
    def fail(connection):
        raise RuntimeError('synthetic verification failure')
    monkeypatch.setattr(store, '_ensure_stripe_fulfillment_schema', fail)
    with pytest.raises(RuntimeError, match='verification failure'):
        store.run_migrations()
    assert 30 not in versions(engine)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM payments')).scalar_one() == 1


def test_partial_event_journal_fails_closed(monkeypatch):
    engine = v29_database(monkeypatch)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE stripe_event_receipts (event_id VARCHAR(120) PRIMARY KEY)'))
    with pytest.raises(RuntimeError, match='schema is incomplete'):
        store.run_migrations()
    assert 30 not in versions(engine)
