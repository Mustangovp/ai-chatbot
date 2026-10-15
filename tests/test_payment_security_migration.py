"""v29 is additive and preserves existing account-owned paid purchases."""
import uuid

import pytest
from sqlalchemy import create_engine, inspect, select, text

import db as store


def versions(engine):
    with engine.connect() as connection:
        return set(connection.execute(select(store.schema_version.c.version)).scalars())


def legacy_database(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at DATETIME)'))
        for version in range(1, 29):
            connection.execute(text('INSERT INTO schema_version (version) VALUES (:v)'), {'v': version})
        connection.execute(text('CREATE TABLE payments (id CHAR(32) PRIMARY KEY, user_id CHAR(32) NOT NULL, '
            'stripe_session_id VARCHAR(120) UNIQUE, amount_cents INTEGER, currency VARCHAR(8), '
            'plan VARCHAR(16), created_at DATETIME)'))
        connection.execute(text("INSERT INTO payments VALUES (:id, :uid, 'cs_legacy', 1499, 'eur', 'pro', '2026-10-01')"),
            {'id': uuid.uuid4().hex, 'uid': uuid.uuid4().hex})
    monkeypatch.setattr(store, 'engine', engine)
    return engine


def test_fresh_payment_security_schema(monkeypatch):
    engine = create_engine('sqlite://')
    monkeypatch.setattr(store, 'engine', engine)
    store.run_migrations()
    columns = {c['name']: c for c in inspect(engine).get_columns('payments')}
    assert {'state', 'period_end', 'paid_at', 'payment_intent_id', 'refund_id'} <= columns.keys()
    assert not columns['state']['nullable']
    assert 'paid' in columns['state']['default']
    assert inspect(engine).get_pk_constraint('payment_token_revocations')['constrained_columns'] == ['token_hash']
    assert 29 in versions(engine)


def test_legacy_purchase_upgrade_preserves_rows_and_is_idempotent(monkeypatch):
    engine = legacy_database(monkeypatch)
    with engine.connect() as connection:
        before = dict(connection.execute(text('SELECT * FROM payments')).mappings().one())
    store.run_migrations()
    store.run_migrations()
    with engine.connect() as connection:
        after = dict(connection.execute(text('SELECT * FROM payments')).mappings().one())
    assert all(after[key] == value for key, value in before.items())
    assert after['state'] == 'paid'
    assert after['period_end'] is None and after['paid_at'] is None
    assert 29 in versions(engine)


def test_failed_upgrade_does_not_record_v29(monkeypatch):
    engine = legacy_database(monkeypatch)
    def fail(_):
        raise RuntimeError('synthetic schema verification failure')
    monkeypatch.setattr(store, '_ensure_payment_security_schema', fail)
    with pytest.raises(RuntimeError, match='schema verification'):
        store.run_migrations()
    assert 29 not in versions(engine)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM payments')).scalar_one() == 1


def test_partial_revocation_table_fails_before_migration_is_recorded(monkeypatch):
    engine = legacy_database(monkeypatch)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE payment_token_revocations (token_hash VARCHAR(64))'))
    with pytest.raises(RuntimeError, match='schema is incomplete'):
        store.run_migrations()
    assert 29 not in versions(engine)


def test_revocation_stores_hash_only_and_is_idempotent():
    token = 'synthetic-private-token'
    store.revoke_payment_tokens([token, token])
    store.revoke_payment_tokens([token])
    with store.engine.connect() as connection:
        rows = connection.execute(select(store.payment_token_revocations)).mappings().all()
    assert len(rows) == 1
    assert rows[0]['token_hash'] == store._hash(token)
    assert token not in str(rows)
