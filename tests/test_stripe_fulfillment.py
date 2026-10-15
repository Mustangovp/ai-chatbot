"""Signed synthetic events exercise the real Flask/SQLAlchemy payment boundary."""
import datetime as dt
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, select, update, func

import app as appmod
import db as store
from test_payment_security import client, login, checkout_payload, purchase


def deliver(client, monkeypatch, event_id, event_type, payload, created):
    secret = 'whsec_synthetic_fulfillment'
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', secret)
    body = json.dumps({'id': event_id, 'object': 'event', 'type': event_type,
        'created': created, 'data': {'object': payload}})
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f'{timestamp}.{body}'.encode(), hashlib.sha256).hexdigest()
    return client.post('/webhook', data=body, content_type='application/json',
        headers={'Stripe-Signature': f't={timestamp},v1={signature}'})


def test_duplicate_event_has_one_durable_receipt(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    payload = checkout_payload(uid)
    created = int(time.time()) - 60
    for _ in range(2):
        assert deliver(client, monkeypatch, 'evt_duplicate', 'checkout.session.completed', payload, created).status_code == 200
    with store.engine.connect() as connection:
        rows = connection.execute(select(store.stripe_event_receipts)).mappings().all()
    assert len(rows) == 1 and rows[0]['status'] == 'succeeded'


def test_older_purchase_event_cannot_replace_newer_entitlement(client, monkeypatch):
    uid = login(client)
    created = int(time.time()) - 300
    for sid, offset in [('cs_new', 120), ('cs_old', 0)]:
        store.bind_pending_checkout(uid, sid, 'core', 999)
        payload = checkout_payload(uid, sid, payment_intent='pi_' + sid)
        assert deliver(client, monkeypatch, 'evt_' + sid, 'checkout.session.completed', payload, created + offset).status_code == 200
    with store.engine.connect() as connection:
        sid = connection.execute(select(store.subscriptions.c.stripe_session_id)).scalar_one()
    assert sid == 'cs_new'


def test_paid_period_uses_verified_event_time_once(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    created = int(time.time()) - 3600
    assert deliver(client, monkeypatch, 'evt_paid_time', 'checkout.session.completed', checkout_payload(uid), created).status_code == 200
    record = store.get_owned_payment(uid)
    assert store._aware(record['paid_at']) == dt.datetime.fromtimestamp(created, dt.timezone.utc)
    assert store._aware(record['period_end']) - store._aware(record['paid_at']) == dt.timedelta(days=30)


def test_legacy_reconciliation_report_is_read_only(client):
    uid = login(client)
    purchase(uid)
    before = store.get_subscription(uid)
    report = store.payment_reconciliation_report()
    assert any(item['issue'] == 'legacy_payment_facts_incomplete' for item in report['purchases'])
    assert store.get_subscription(uid) == before


def receipt(event_id):
    with store.engine.connect() as connection:
        return dict(connection.execute(select(store.stripe_event_receipts).where(
            store.stripe_event_receipts.c.event_id == event_id)).mappings().one())


def paid_checkout(client, monkeypatch, sid='cs_test_pending', plan='core', offset=0):
    uid = login(client)
    amount = 999 if plan == 'core' else 1499
    store.bind_pending_checkout(uid, sid, plan, amount)
    created = int(time.time()) - 300 + offset
    payload = checkout_payload(uid, sid, metadata={'plan': plan, 'account_id': uid},
        amount_total=amount, payment_intent='pi_' + sid)
    assert deliver(client, monkeypatch, 'evt_' + sid, 'checkout.session.completed', payload, created).status_code == 200
    return uid, payload, created


@pytest.mark.parametrize('failure_at', ['entitlement', 'commit'])
def test_database_failure_rolls_back_and_retry_recovers(client, monkeypatch, failure_at):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    payload, created = checkout_payload(uid), int(time.time()) - 300
    failures = []
    processing = []
    def fail_update(connection, cursor, statement, parameters, context, executemany):
        if 'INSERT INTO stripe_event_receipts' in statement:
            processing.append(True)
        if (failure_at == 'entitlement' and not failures and
                'UPDATE subscriptions SET' in statement and 'stripe_session_id=' in statement):
            failures.append(True)
            raise RuntimeError('private failure details must not escape')
    def fail_commit(connection):
        if processing and not failures:
            failures.append(True)
            raise RuntimeError('private commit failure')
    event.listen(store.engine, 'before_cursor_execute', fail_update)
    if failure_at == 'commit':
        event.listen(store.engine, 'commit', fail_commit)
    try:
        response = deliver(client, monkeypatch, 'evt_recover', 'checkout.session.completed', payload, created)
    finally:
        event.remove(store.engine, 'before_cursor_execute', fail_update)
        if failure_at == 'commit':
            event.remove(store.engine, 'commit', fail_commit)
    assert failures and response.status_code == 503
    assert 'private' not in response.get_data(as_text=True)
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'pending'
    assert store.get_subscription(uid)['plan'] == 'free'
    assert receipt('evt_recover')['status'] == 'retryable'
    assert receipt('evt_recover')['attempt_count'] == 1
    with store.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(store.stripe_payment_intents)).scalar_one() == 0
    assert deliver(client, monkeypatch, 'evt_recover', 'checkout.session.completed', payload, created).status_code == 200
    assert receipt('evt_recover')['status'] == 'succeeded'
    assert receipt('evt_recover')['attempt_count'] == 2
    expiry = store.get_subscription(uid)['current_period_end']
    assert deliver(client, monkeypatch, 'evt_recover', 'checkout.session.completed', payload, created).status_code == 200
    assert store.get_subscription(uid)['current_period_end'] == expiry


@pytest.mark.parametrize('same_event', [True, False])
def test_concurrent_webhook_workers_do_not_extend_purchase(client, monkeypatch, same_event):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    created, payload = int(time.time()) - 300, checkout_payload(uid)
    barrier = threading.Barrier(2)
    def worker(index):
        with appmod.app.test_client() as independent_client:
            barrier.wait(timeout=10)
            return deliver(independent_client, monkeypatch, 'evt_concurrent' if same_event else f'evt_concurrent_{index}',
                'checkout.session.completed', payload, created).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(worker, range(2))) == [200, 200]
    record = store.get_owned_payment(uid)
    assert store._aware(record['paid_at']).timestamp() == created
    assert store._aware(record['period_end']).timestamp() == created + 30 * 86400
    with store.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(store.payments)).scalar_one() == 1
        rows = connection.execute(select(store.stripe_event_receipts)).mappings().all()
    assert len(rows) == (1 if same_event else 2)
    assert all(row['status'] == 'succeeded' for row in rows)


def test_two_purchases_concurrent_order_is_verified_payment_time(client, monkeypatch):
    uid = login(client)
    created = int(time.time()) - 300
    for sid in ('cs_old', 'cs_new'):
        store.bind_pending_checkout(uid, sid, 'core', 999)
    barrier = threading.Barrier(2)
    def worker(item):
        sid, offset = item
        barrier.wait(timeout=10)
        with appmod.app.test_client() as independent_client:
            return deliver(independent_client, monkeypatch, 'evt_' + sid, 'checkout.session.completed',
                checkout_payload(uid, sid, payment_intent='pi_' + sid), created + offset).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(worker, [('cs_old', 0), ('cs_new', 60)])) == [200, 200]
    with store.engine.connect() as connection:
        assert connection.execute(select(store.subscriptions.c.stripe_session_id)).scalar_one() == 'cs_new'


@pytest.mark.parametrize('before_payment', [True, False])
def test_full_refund_and_payment_event_order_cannot_restore_access(client, monkeypatch, before_payment):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    created = int(time.time()) - 300
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs:
        type('Sessions', (), {'data': [type('Session', (), {'id': 'cs_test_pending', 'payment_intent': 'pi_test_owned'})()]})())
    payment = lambda: deliver(client, monkeypatch, 'evt_payment', 'checkout.session.completed', checkout_payload(uid), created)
    refund = lambda: deliver(client, monkeypatch, 'evt_refund', 'charge.refunded',
        {'object': 'charge', 'id': 'ch_test', 'payment_intent': 'pi_test_owned', 'refunded': True}, created + 60)
    assert (refund() if before_payment else payment()).status_code == 200
    assert (payment() if before_payment else refund()).status_code == 200
    assert payment().status_code == 200 and refund().status_code == 200
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'refunded'
    assert store.get_subscription(uid)['plan'] == 'free'


def test_discounted_refund_before_checkout_is_not_lost(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    created = int(time.time()) - 300
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs:
        type('Sessions', (), {'data': [type('Session', (), {'id': 'cs_test_pending', 'payment_intent': 'pi_test_owned'})()]})())
    refund = {'id': 're_discounted', 'object': 'refund', 'payment_intent': 'pi_test_owned',
        'status': 'succeeded', 'amount': 899, 'currency': 'eur'}
    assert deliver(client, monkeypatch, 'evt_early_refund', 'refund.updated', refund, created + 60).status_code == 200
    assert deliver(client, monkeypatch, 'evt_discounted_paid', 'checkout.session.completed',
        checkout_payload(uid, amount_total=899), created).status_code == 200
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'refunded'
    assert store.get_subscription(uid)['plan'] == 'free'


def test_refund_outcomes_are_durable_and_monotonic(client, monkeypatch):
    uid, payload, created = paid_checkout(client, monkeypatch)
    assert store.claim_owned_refund(uid, 'cs_test_pending', (), 'pi_cs_test_pending')
    refund = {'id': 're_outcome', 'object': 'refund', 'payment_intent': 'pi_cs_test_pending',
        'amount': 999, 'currency': 'eur', 'status': 'failed'}
    assert deliver(client, monkeypatch, 'evt_failed', 'refund.failed', refund, created + 60).status_code == 200
    row = store.get_owned_payment(uid, 'cs_test_pending')
    assert row['state'] == 'refund_pending' and row['refund_status'] == 'failed'
    assert row['refund_error_code'] == 'provider_refund_failed'
    refund['status'] = 'pending'
    assert deliver(client, monkeypatch, 'evt_older', 'refund.updated', refund, created + 30).status_code == 200
    assert store.get_owned_payment(uid, 'cs_test_pending')['refund_status'] == 'failed'
    refund['status'] = 'succeeded'
    assert deliver(client, monkeypatch, 'evt_succeeded', 'refund.updated', refund, created + 120).status_code == 200
    refund['status'] = 'failed'
    assert deliver(client, monkeypatch, 'evt_late_failed', 'refund.failed', refund, created + 180).status_code == 200
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'refunded'
    assert store.get_subscription(uid)['status'] == 'revoked'


def test_old_refund_cannot_revoke_new_purchase(client, monkeypatch):
    uid, old, created = paid_checkout(client, monkeypatch, 'cs_old')
    store.bind_pending_checkout(uid, 'cs_new', 'pro', 1499)
    new = checkout_payload(uid, 'cs_new', metadata={'plan': 'pro', 'account_id': uid},
        amount_total=1499, payment_intent='pi_new')
    assert deliver(client, monkeypatch, 'evt_new', 'checkout.session.completed', new, created + 60).status_code == 200
    assert deliver(client, monkeypatch, 'evt_old_refund', 'charge.refunded',
        {'id': 'ch_old', 'object': 'charge', 'refunded': True, 'payment_intent': 'pi_cs_old'}, created + 120).status_code == 200
    assert store.get_subscription(uid)['plan'] == 'pro'


def test_event_identity_conflict_cannot_mutate_owner_or_tier(client, monkeypatch):
    uid, payload, created = paid_checkout(client, monkeypatch)
    before = store.get_subscription(uid)
    payload['metadata'] = {'plan': 'pro', 'account_id': 'forged'}
    assert deliver(client, monkeypatch, 'evt_cs_test_pending', 'checkout.session.completed', payload, created).status_code == 409
    assert store.get_subscription(uid) == before
    assert receipt('evt_cs_test_pending')['error_code'] == 'event_identity_conflict'
    assert 'unverified-victim@example.test' not in json.dumps(receipt('evt_cs_test_pending'), default=str)


def test_one_payment_intent_cannot_fulfill_two_accounts(client, monkeypatch):
    first, payload, created = paid_checkout(client, monkeypatch)
    second = login(client, 'second@example.test')
    store.bind_pending_checkout(second, 'cs_second', 'core', 999)
    response = deliver(client, monkeypatch, 'evt_second', 'checkout.session.completed',
        checkout_payload(second, 'cs_second', payment_intent=payload['payment_intent']), created + 60)
    assert response.status_code == 409
    assert store.get_subscription(second)['plan'] == 'free'
    assert store.get_subscription(first)['plan'] == 'core'


def test_independent_processes_and_restart_replay_are_idempotent(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    created = int(time.time()) - 300
    document = {'id': 'evt_processes', 'object': 'event', 'type': 'checkout.session.completed',
        'created': created, 'data': {'object': checkout_payload(uid)}}
    program = """import json,sys,time,hmac,hashlib,app
data=json.loads(sys.stdin.readline())
print('READY',flush=True)
sys.stdin.readline()
body=json.dumps(data)
now=int(time.time())
sig=hmac.new(b'whsec_processes',f'{now}.{body}'.encode(),hashlib.sha256).hexdigest()
response=app.app.test_client().post('/webhook',data=body,content_type='application/json',headers={'Stripe-Signature':f't={now},v1={sig}'})
print('RESULT '+str(response.status_code),flush=True)
"""
    environment = {**os.environ, 'DATABASE_URL': store.DATABASE_URL, 'STRIPE_WEBHOOK_SECRET': 'whsec_processes'}
    processes = [subprocess.Popen([sys.executable, '-c', program], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment) for _ in range(2)]
    try:
        for process in processes:
            process.stdin.write(json.dumps(document) + '\n'); process.stdin.flush()
        for process in processes:
            for _ in range(20):
                if process.stdout.readline().strip() == 'READY': break
            else: pytest.fail('independent app did not start')
        for process in processes:
            process.stdin.write('GO\n'); process.stdin.flush()
        for process in processes:
            output, errors = process.communicate(timeout=45)
            assert process.returncode == 0, errors
            assert 'RESULT 200' in output, output
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait(timeout=10)
    assert receipt('evt_processes')['attempt_count'] == 1
    before = store.get_subscription(uid)
    assert deliver(client, monkeypatch, 'evt_processes', 'checkout.session.completed', checkout_payload(uid), created).status_code == 200
    assert store.get_subscription(uid) == before


def test_refund_lookup_failure_retries_with_newly_available_binding(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    charge = {'id': 'ch_retry', 'object': 'charge', 'refunded': True, 'payment_intent': 'pi_test_owned'}
    created = int(time.time()) - 60
    def unavailable(**kwargs):
        raise RuntimeError('private Stripe failure')
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', unavailable)
    assert deliver(client, monkeypatch, 'evt_lookup_retry', 'charge.refunded', charge, created).status_code == 503
    assert receipt('evt_lookup_retry')['status'] == 'retryable'
    assert 'private' not in str(receipt('evt_lookup_retry'))
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs:
        type('Sessions', (), {'data': [type('Session', (), {'id': 'cs_test_pending', 'payment_intent': 'pi_test_owned'})()]})())
    assert deliver(client, monkeypatch, 'evt_lookup_retry', 'charge.refunded', charge, created).status_code == 200
    assert receipt('evt_lookup_retry')['status'] == 'succeeded'
    assert receipt('evt_lookup_retry')['attempt_count'] == 2
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'refunded'


def test_concurrent_full_refund_and_payment_never_restore_access(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs:
        type('Sessions', (), {'data': [type('Session', (), {'id': 'cs_test_pending', 'payment_intent': 'pi_test_owned'})()]})())
    created = int(time.time()) - 300
    barrier = threading.Barrier(2)
    def worker(kind):
        barrier.wait(timeout=10)
        with appmod.app.test_client() as independent_client:
            if kind == 'payment':
                return deliver(independent_client, monkeypatch, 'evt_race_paid', 'checkout.session.completed', checkout_payload(uid), created).status_code
            return deliver(independent_client, monkeypatch, 'evt_race_refund', 'charge.refunded',
                {'id': 'ch_race', 'object': 'charge', 'refunded': True, 'payment_intent': 'pi_test_owned'}, created + 60).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(worker, ['payment', 'refund'])) == [200, 200]
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'refunded'
    assert store.get_subscription(uid)['plan'] == 'free'


def test_ambiguous_legacy_binding_is_reported_without_mutation(client, monkeypatch):
    first = login(client)
    purchase(first, 'cs_legacy_a')
    second = store.get_or_create_user('legacy-b@example.test')
    purchase(second, 'cs_legacy_b')
    with store.engine.begin() as connection:
        connection.execute(update(store.payments).values(payment_intent_id='pi_ambiguous'))
    before = [store.get_subscription(uid) for uid in (first, second)]
    response = deliver(client, monkeypatch, 'evt_ambiguous', 'charge.refunded',
        {'id': 'ch_ambiguous', 'object': 'charge', 'refunded': True, 'payment_intent': 'pi_ambiguous'}, int(time.time()))
    assert response.status_code == 409
    assert [store.get_subscription(uid) for uid in (first, second)] == before
    report = store.payment_reconciliation_report()
    assert report['ambiguous_payment_intents'] == ['pi_ambiguous']
    assert any(row['event_id'] == 'evt_ambiguous' for row in report['events'])


def test_unmatched_legacy_expiry_is_not_invented_or_persisted(client):
    uid = login(client)
    purchase(uid, 'cs_legacy_old')
    purchase(uid, 'cs_legacy_current')
    old = store.get_owned_payment(uid, 'cs_legacy_old')
    assert old['period_end'] is None
    before = store.get_subscription(uid)
    assert client.get('/poll-token?session_id=cs_legacy_old').get_json()['ready'] is False
    assert store.get_subscription(uid) == before


def test_successful_external_refund_with_failed_local_write_remains_recoverable(client, monkeypatch):
    uid, payload, created = paid_checkout(client, monkeypatch)
    calls = []
    def refund(**kwargs):
        calls.append(kwargs)
        return type('Refund', (), {'id': 're_succeeded', 'status': 'succeeded'})()
    monkeypatch.setattr(appmod.stripe.Refund, 'create', refund)
    with monkeypatch.context() as failing:
        def unavailable(*args):
            raise RuntimeError('private write failure')
        failing.setattr(store, 'complete_owned_refund', unavailable)
        response = client.post('/withdraw', json={'session_id': 'cs_test_pending'})
    assert response.status_code == 503
    row = store.get_owned_payment(uid, 'cs_test_pending')
    assert row['state'] == 'refund_pending' and row['refund_status'] == 'pending'
    assert row['refund_attempt_count'] == 1
    assert store.get_subscription(uid)['status'] == 'revoked'
    assert deliver(client, monkeypatch, 'evt_refund_recovery', 'refund.updated', {
        'id': 're_succeeded', 'object': 'refund', 'status': 'succeeded', 'amount': 999,
        'currency': 'eur', 'payment_intent': payload['payment_intent']}, created + 60).status_code == 200
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'refunded'
    client.post('/withdraw', json={'session_id': 'cs_test_pending'})
    assert len(calls) == 1


def test_late_api_snapshot_cannot_replace_terminal_refund_outcome(client, monkeypatch):
    uid, payload, created = paid_checkout(client, monkeypatch)
    assert store.claim_owned_refund(uid, 'cs_test_pending', (), payload['payment_intent'])
    store.record_owned_refund_outcome(uid, 'cs_test_pending', 'failed', 're_terminal')
    store.record_owned_refund_outcome(uid, 'cs_test_pending', 'pending', 're_terminal')
    store.record_owned_refund_outcome(uid, 'cs_test_pending', 'unconfirmed')
    row = store.get_owned_payment(uid, 'cs_test_pending')
    assert row['refund_status'] == 'failed' and row['refund_error_code'] == 'provider_refund_failed'
    assert store.get_subscription(uid)['status'] == 'revoked'


def test_processed_early_refund_duplicate_needs_no_stripe_lookup(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs:
        type('Sessions', (), {'data': [type('Session', (), {'id': 'cs_test_pending', 'payment_intent': 'pi_test_owned'})()]})())
    payload = {'id': 're_early_partial', 'object': 'refund', 'payment_intent': 'pi_test_owned',
        'status': 'succeeded', 'amount': 100, 'currency': 'eur'}
    created = int(time.time()) - 60
    assert deliver(client, monkeypatch, 'evt_early_partial', 'refund.updated', payload, created).status_code == 200
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs: pytest.fail('duplicate must use durable receipt'))
    assert deliver(client, monkeypatch, 'evt_early_partial', 'refund.updated', payload, created).status_code == 200


def test_refund_transport_failure_is_recorded_as_unconfirmed(client, monkeypatch):
    uid, payload, created = paid_checkout(client, monkeypatch)
    def timeout(**kwargs):
        raise TimeoutError('private network detail')
    monkeypatch.setattr(appmod.stripe.Refund, 'create', timeout)
    response = client.post('/withdraw', json={'session_id': 'cs_test_pending'})
    assert response.status_code == 200 and response.get_json()['refunded'] is False
    row = store.get_owned_payment(uid, 'cs_test_pending')
    assert row['refund_status'] == 'unconfirmed' and row['refund_attempt_count'] == 1
    report = store.payment_reconciliation_report()
    assert report['purchases'][0]['refund_error_code'] == 'provider_request_failed'


def test_orphan_legacy_payment_is_reviewed_without_reprovisioning(client, monkeypatch):
    uid = login(client)
    store.record_payment(uid, 'cs_orphan', 999, 'eur', 'core')
    response = deliver(client, monkeypatch, 'evt_orphan', 'checkout.session.completed',
        checkout_payload(uid, 'cs_orphan'), int(time.time()) - 60)
    assert response.status_code == 409
    assert receipt('evt_orphan')['status'] == 'review'
    assert store.get_subscription(uid)['plan'] == 'free'


def test_valid_legacy_entitlement_event_is_acknowledged_without_rewrite(client, monkeypatch):
    uid = login(client)
    purchase(uid)
    before = store.get_subscription(uid)
    response = deliver(client, monkeypatch, 'evt_legacy', 'checkout.session.completed',
        checkout_payload(uid, 'cs_test_owned'), int(time.time()) - 60)
    assert response.status_code == 200
    assert receipt('evt_legacy')['status'] == 'ignored'
    assert store.get_subscription(uid) == before
