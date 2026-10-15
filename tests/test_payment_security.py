"""Payment authorization uses real account sessions and an isolated DB; Stripe is stubbed."""
import datetime as dt
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select, update

import app as appmod
import db as store


UTC = dt.timezone.utc


@pytest.fixture
def client(monkeypatch):
    appmod.app.config['TESTING'] = True
    monkeypatch.delenv('PAID_ACCESS_ENABLED', raising=False)
    monkeypatch.setattr(appmod, 'send_email', lambda *a, **k: None)
    monkeypatch.setattr(appmod, '_save_revoked', lambda *a: None)
    monkeypatch.setattr(appmod, '_revoked_tokens', set())
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'retrieve',
                        lambda *a, **k: pytest.fail('unexpected Stripe request'))
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'create',
                        lambda *a, **k: pytest.fail('unexpected Stripe checkout'))
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'list',
                        lambda *a, **k: pytest.fail('unexpected Stripe list'))
    monkeypatch.setattr(appmod.stripe.Refund, 'create',
                        lambda *a, **k: pytest.fail('unexpected Stripe refund'))
    appmod._pending_tokens.clear()
    return appmod.app.test_client()


def login(client, email='owner@example.test'):
    uid = store.get_or_create_user(email)
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    return uid


def purchase(uid, sid='cs_test_owned', plan='core', age_days=1):
    expiry = dt.datetime.now(UTC) + dt.timedelta(days=30-age_days)
    store.upsert_subscription(uid, plan, expiry, stripe_session_id=sid)
    store.record_payment(uid, sid, 999 if plan == 'core' else 1499, 'eur', plan)
    with store.engine.begin() as connection:
        connection.execute(update(store.payments).where(store.payments.c.stripe_session_id == sid)
            .values(created_at=dt.datetime.now(UTC) - dt.timedelta(days=age_days)))
    return appmod.make_token(int(expiry.timestamp()), plan)


def stripe_session(sid, email='owner@example.test', plan='core'):
    return types.SimpleNamespace(id=sid, payment_status='paid', mode='payment',
        metadata={'plan': plan}, customer_details=types.SimpleNamespace(email=email),
        customer=None, amount_total=999, currency='eur', payment_intent='pi_test_owned')


def stub_stripe(monkeypatch, sid, calls):
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'retrieve', lambda *a, **k: stripe_session(sid))
    def refund(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(id='re_test', status='succeeded')
    monkeypatch.setattr(appmod.stripe.Refund, 'create', refund)


def test_unverified_checkout_email_and_session_cannot_log_in(client, monkeypatch):
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'retrieve', lambda *a, **k: stripe_session('cs_test_guest'))
    response = client.get('/poll-token?session_id=cs_test_guest')
    assert response.status_code == 401
    assert not response.headers.getlist('Set-Cookie') or not any(appmod.SESSION_COOKIE in s for s in response.headers.getlist('Set-Cookie'))
    assert client.get('/auth/me').get_json()['authenticated'] is False


def test_checkout_session_cannot_switch_authenticated_account(client):
    owner = store.get_or_create_user('owner@example.test')
    purchase(owner)
    other = login(client, 'other@example.test')
    response = client.get('/poll-token?session_id=cs_test_owned')
    assert response.status_code == 403
    assert client.get('/auth/me').get_json()['email'] == 'other@example.test'
    assert store.get_subscription(other)['plan'] == 'free'


def test_bare_token_and_session_cannot_authorize_refund(client, monkeypatch):
    owner = store.get_or_create_user('owner@example.test')
    token = purchase(owner)
    calls = []
    stub_stripe(monkeypatch, 'cs_test_owned', calls)
    response = client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'})
    assert response.status_code == 401
    assert calls == []


def test_cross_account_refund_is_rejected_before_stripe(client, monkeypatch):
    owner = store.get_or_create_user('owner@example.test')
    token = purchase(owner)
    login(client, 'other@example.test')
    calls = []
    stub_stripe(monkeypatch, 'cs_test_owned', calls)
    response = client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'})
    assert response.status_code == 403
    assert calls == []
    assert store.get_subscription(owner)['plan'] == 'core'


def test_refunded_purchase_is_not_grace(client, monkeypatch):
    owner = login(client)
    token = purchase(owner)
    calls = []
    stub_stripe(monkeypatch, 'cs_test_owned', calls)
    response = client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'})
    assert response.status_code == 200
    assert response.get_json()['refunded'] is True
    assert store.get_subscription(owner)['plan'] == 'free'
    assert client.get('/auth/me').get_json()['plan'] == 'free'


def test_revoked_token_stays_invalid_without_process_cache(client, monkeypatch):
    owner = login(client)
    token = purchase(owner)
    stub_stripe(monkeypatch, 'cs_test_owned', [])
    assert client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'}).status_code == 200
    appmod._revoked_tokens.clear()
    assert appmod.verify_token(token) == (False, None)


def test_existing_paid_account_continues_without_payment_token(client):
    owner = login(client)
    purchase(owner, plan='pro')
    state = client.get('/auth/me').get_json()
    assert state['authenticated'] is True
    assert state['plan'] == 'pro' and state['status'] == 'active'


def signed_event(client, monkeypatch, event_type, payload, valid=True):
    secret = 'whsec_synthetic_only'
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', secret)
    body = json.dumps({'id': 'evt_test_security', 'object': 'event',
        'type': event_type, 'data': {'object': payload}})
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f'{timestamp}.{body}'.encode(), hashlib.sha256).hexdigest()
    return client.post('/webhook', data=body, content_type='application/json',
        headers={'Stripe-Signature': f't={timestamp},v1={signature if valid else "invalid"}'})


def checkout_payload(uid, sid='cs_test_pending', **overrides):
    return {**vars(stripe_session(sid)), 'object': 'checkout.session',
        'customer_details': {'email': 'unverified-victim@example.test'},
        'metadata': {'plan': 'core', 'account_id': str(uid)}, **overrides}


def test_checkout_requires_verified_account_even_when_sales_locally_enabled(client, monkeypatch):
    monkeypatch.setenv('PAID_ACCESS_ENABLED', 'true')
    assert client.post('/create-checkout-session', json={'email': 'victim@example.test'}).status_code == 401


def test_checkout_binds_only_authenticated_identity(client, monkeypatch):
    uid = login(client)
    monkeypatch.setenv('PAID_ACCESS_ENABLED', 'true')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(id='cs_test_pending', url='https://checkout.stripe.com/synthetic')
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'create', create)
    response = client.post('/create-checkout-session', json={'plan': 'core',
        'email': 'victim@example.test', 'account_id': 'forged'})
    assert response.status_code == 200
    assert calls[0]['customer_email'] == 'owner@example.test'
    assert calls[0]['metadata'] == {'plan': 'core', 'account_id': uid}
    assert calls[0]['client_reference_id'] == uid
    assert calls[0]['mode'] == 'payment'
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'pending'
    assert store.get_subscription(uid)['plan'] == 'free'


@pytest.mark.parametrize('case', ['signature', 'owner', 'plan', 'unpaid', 'currency', 'session'])
def test_invalid_confirmation_never_grants_access(client, monkeypatch, case):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    payload = checkout_payload(uid)
    if case == 'owner': payload['metadata']['account_id'] = 'someone-else'
    if case == 'plan': payload['metadata']['plan'] = 'pro'
    if case == 'unpaid': payload['payment_status'] = 'unpaid'
    if case == 'currency': payload['currency'] = 'usd'
    if case == 'session': payload['id'] = 'cs_unbound'
    response = signed_event(client, monkeypatch, 'checkout.session.completed', payload, case != 'signature')
    assert response.status_code in (200, 400, 409)
    assert store.get_subscription(uid)['plan'] == 'free'
    assert store.get_owned_payment(uid, 'cs_test_pending')['state'] == 'pending'


def test_signed_checkout_ignores_unverified_email_and_replay_does_not_renew(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    payload = checkout_payload(uid)
    assert signed_event(client, monkeypatch, 'checkout.session.completed', payload).status_code == 200
    first = store.get_subscription(uid)
    assert first['plan'] == 'core'
    assert signed_event(client, monkeypatch, 'checkout.session.completed', payload).status_code == 200
    assert store.get_subscription(uid) == first
    with store.engine.begin() as connection:
        assert connection.execute(select(store.users.c.id).where(
            store.users.c.email == 'unverified-victim@example.test')).first() is None
    response = client.get('/poll-token?session_id=cs_test_pending')
    assert response.get_json()['ready'] is True
    assert not any(appmod.SESSION_COOKIE in value for value in response.headers.getlist('Set-Cookie'))
    token = response.get_json()['token']
    verified = client.post('/verify-token', json={'token': token}).get_json()
    assert verified['valid'] is True and verified['expiry'] > time.time()
    login(client, 'other@example.test')
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is False


@pytest.mark.parametrize('reference', ['other-session', 'wrong-token'])
def test_mismatched_refund_reference_is_rejected(client, reference):
    uid = login(client)
    token = purchase(uid)
    body = {'session_id': 'cs_test_owned', 'token': token}
    if reference == 'other-session': body['session_id'] = 'cs_test_not_owned'
    else: body['token'] = appmod.make_token(int(time.time()) + 100, 'pro')
    assert client.post('/withdraw', json=body).status_code == 403
    assert store.get_subscription(uid)['status'] == 'active'


def test_refund_without_browser_token_uses_authenticated_purchase_owner(client, monkeypatch):
    uid = login(client)
    purchase(uid)
    calls = []
    stub_stripe(monkeypatch, 'cs_test_owned', calls)
    response = client.post('/withdraw', json={'session_id': 'cs_test_owned'})
    assert response.get_json()['refunded'] is True
    assert len(calls) == 1 and calls[0]['idempotency_key'].startswith('apex-refund-')
    client.post('/withdraw', json={'session_id': 'cs_test_owned'})
    assert len(calls) == 1


def test_refund_failure_remains_durably_revoked(client, monkeypatch):
    uid = login(client)
    token = purchase(uid)
    stub_stripe(monkeypatch, 'cs_test_owned', [])
    def fail(**kwargs):
        raise RuntimeError('private-provider-error')
    monkeypatch.setattr(appmod.stripe.Refund, 'create', fail)
    response = client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'})
    assert response.status_code == 200
    assert response.get_json()['refunded'] is False
    assert 'private-provider-error' not in response.get_data(as_text=True)
    assert store.get_owned_payment(uid, 'cs_test_owned')['state'] == 'refund_pending'
    assert store.get_subscription(uid)['status'] == 'revoked'
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is False


def test_after_refund_window_keeps_paid_period_without_stripe_refund(client):
    uid = login(client)
    token = purchase(uid, age_days=8)
    response = client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'})
    assert response.status_code == 200 and response.get_json()['refunded'] is False
    assert store.get_subscription(uid)['plan'] == 'core'
    assert store.get_subscription(uid)['status'] == 'grace'
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is True


@pytest.mark.parametrize('stale_status', ['active', 'cancelled', 'grace'])
def test_refunded_ledger_overrides_stale_subscription_state(client, stale_status):
    uid = login(client)
    token = purchase(uid)
    with store.engine.begin() as connection:
        connection.execute(update(store.payments).values(state='refunded'))
        connection.execute(update(store.subscriptions).values(status=stale_status))
    assert client.get('/auth/me').get_json()['plan'] == 'free'
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is False
    assert client.get('/poll-token?session_id=cs_test_owned').get_json()['ready'] is False


def test_revocation_is_visible_to_independent_engine_and_restarted_process(client, monkeypatch):
    uid = login(client)
    token = purchase(uid)
    stub_stripe(monkeypatch, 'cs_test_owned', [])
    assert client.post('/withdraw', json={'token': token, 'session_id': 'cs_test_owned'}).status_code == 200
    independent = create_engine(store.DATABASE_URL)
    with monkeypatch.context() as isolated:
        isolated.setattr(store, 'engine', independent)
        isolated.setattr(appmod, '_revoked_tokens', set())
        assert store.get_subscription(uid)['plan'] == 'free'
        assert appmod.verify_token(token) == (False, None)
    independent.dispose()
    # A fresh interpreter has neither the old app module nor its in-memory cache.
    program = "import json,sys,app,db; p=json.loads(sys.stdin.read()); assert not app._revoked_tokens; assert app.verify_token(p['token']) == (False,None); assert db.get_subscription(p['uid'])['plan']=='free'; print('RESTART_REVOCATION_PASS')"
    result = subprocess.run([sys.executable, '-c', program], input=json.dumps({'token': token, 'uid': uid}),
        text=True, capture_output=True, timeout=45, env={**os.environ, 'DATABASE_URL': store.DATABASE_URL})
    assert result.returncode == 0, result.stderr
    assert 'RESTART_REVOCATION_PASS' in result.stdout


def test_concurrent_refund_claim_has_one_winner(client):
    uid = login(client)
    token = purchase(uid)
    barrier = threading.Barrier(2)
    def claim():
        barrier.wait(timeout=10)
        return store.claim_owned_refund(uid, 'cs_test_owned', [token], 'pi_test_owned')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(results) == [False, True]
    assert store.get_subscription(uid)['status'] == 'revoked'


def test_old_purchase_replay_cannot_replace_newer_paid_access(client, monkeypatch):
    uid = login(client)
    purchase(uid, 'cs_test_old')
    purchase(uid, 'cs_test_new', plan='pro')
    assert signed_event(client, monkeypatch, 'checkout.session.completed',
        checkout_payload(uid, 'cs_test_old')).status_code == 200
    assert store.get_subscription(uid)['plan'] == 'pro'
    store.claim_owned_refund(uid, 'cs_test_old', (), 'pi_old')
    assert store.get_subscription(uid)['plan'] == 'pro'


@pytest.mark.parametrize('legacy', [False, True])
def test_signed_external_full_refund_revokes_only_owned_purchase(client, monkeypatch, legacy):
    uid = login(client)
    token = purchase(uid)
    if legacy:
        monkeypatch.setattr(appmod.stripe.checkout.Session, 'list', lambda **kwargs:
            types.SimpleNamespace(data=[stripe_session('cs_test_owned')]))
    else:
        with store.engine.begin() as connection:
            connection.execute(update(store.payments).values(payment_intent_id='pi_test_owned'))
    charge = {'object': 'charge', 'id': 'ch_test', 'refunded': True, 'payment_intent': 'pi_test_owned'}
    assert signed_event(client, monkeypatch, 'charge.refunded', charge, valid=False).status_code == 400
    assert store.get_subscription(uid)['plan'] == 'core'
    assert signed_event(client, monkeypatch, 'charge.refunded', charge).status_code == 200
    assert store.get_subscription(uid)['status'] == 'revoked'
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is False
    assert signed_event(client, monkeypatch, 'checkout.session.completed',
        checkout_payload(uid, 'cs_test_owned')).status_code == 409


def test_partial_refund_does_not_invent_new_revocation_policy(client, monkeypatch):
    uid = login(client)
    purchase(uid)
    response = signed_event(client, monkeypatch, 'charge.refunded',
        {'object': 'charge', 'refunded': False, 'payment_intent': 'pi_test_owned'})
    assert response.status_code == 200 and store.get_subscription(uid)['plan'] == 'core'


def test_passwordless_identity_and_free_access_remain_available(client):
    uid = store.get_or_create_user('verified@example.test')
    magic = store.create_login_token(uid)
    assert client.get('/auth/verify?token=' + magic).status_code == 302
    state = client.get('/auth/me').get_json()
    assert state['authenticated'] is True and state['plan'] == 'free'


@pytest.mark.parametrize('plan', ['core', 'pro'])
def test_existing_account_owned_legacy_token_remains_valid(client, plan):
    uid = login(client)
    token = purchase(uid, plan=plan)
    result = client.post('/verify-token', json={'token': token}).get_json()
    assert result['valid'] is True and result['plan'] == plan


def test_v1_token_requires_and_preserves_verified_purchase_owner(client):
    uid = login(client)
    purchase(uid)
    record = store.get_owned_payment(uid)
    expiry = str(int(store._aware(record['period_end']).timestamp()))
    signature = hmac.new(appmod.SECRET.encode(), expiry.encode(), hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f'{expiry}.{signature}'.encode()).decode().rstrip('=')
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is True
    client.delete_cookie(appmod.SESSION_COOKIE)
    assert client.post('/verify-token', json={'token': token}).get_json()['valid'] is False


def test_poll_rejects_provider_session_mismatch(client, monkeypatch):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    monkeypatch.setattr(appmod.stripe.checkout.Session, 'retrieve', lambda *a, **k:
        types.SimpleNamespace(**checkout_payload(uid, 'cs_other')))
    assert client.get('/poll-token?session_id=cs_test_pending').status_code == 409
    assert store.get_subscription(uid)['plan'] == 'free'


def test_revocation_write_failure_never_calls_stripe_refund(client, monkeypatch):
    uid = login(client)
    purchase(uid)
    with store.engine.begin() as connection:
        connection.execute(update(store.payments).values(payment_intent_id='pi_test_owned'))
    def fail(*args):
        raise RuntimeError('synthetic revocation-store failure')
    monkeypatch.setattr(store, '_persist_token_revocations', fail)
    assert client.post('/withdraw', json={'session_id': 'cs_test_owned'}).status_code == 503
    assert store.get_owned_payment(uid)['state'] == 'paid'
    assert store.get_subscription(uid)['status'] == 'active'


def test_concurrent_paid_confirmation_grants_one_period(client):
    uid = login(client)
    store.bind_pending_checkout(uid, 'cs_test_pending', 'core', 999)
    barrier = threading.Barrier(2)
    def fulfill():
        barrier.wait(timeout=10)
        return store.fulfill_bound_checkout('cs_test_pending', 'core', 999, 'eur', 'pi_test')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: fulfill(), range(2)))
    assert uid in results and set(results) <= {uid, None}
    record = store.get_owned_payment(uid)
    assert store._aware(record['period_end']) - store._aware(record['paid_at']) == dt.timedelta(days=30)
    assert store.fulfill_bound_checkout('cs_test_pending', 'core', 999, 'eur', 'pi_test') == uid
    assert store.get_owned_payment(uid)['period_end'] == record['period_end']


def test_payment_responses_cannot_be_shared_cached(client):
    responses = [client.get('/poll-token?session_id=cs_test'),
        client.post('/verify-token', json={'token': 'invalid'}),
        client.post('/withdraw', json={'session_id': 'cs_test'}),
        client.post('/create-checkout-session', json={'plan': 'core'})]
    assert all(response.headers['Cache-Control'] == 'private, no-store' for response in responses)
