"""Billing is a read-only account projection, not a second entitlement policy."""
import datetime as dt
import json
import uuid

import pytest
from sqlalchemy import event, select, update

import app as appmod
import db as store


UTC = dt.timezone.utc


@pytest.fixture
def client(monkeypatch):
    appmod.app.config['TESTING'] = True
    monkeypatch.delenv('PAID_ACCESS_ENABLED', raising=False)
    for api, name in [(appmod.stripe.checkout.Session, 'retrieve'),
                      (appmod.stripe.checkout.Session, 'create'),
                      (appmod.stripe.Refund, 'create')]:
        monkeypatch.setattr(api, name, lambda *a, **k: pytest.fail('billing must not call Stripe'))
    return appmod.app.test_client()


def login(client, email='billing-a@example.test'):
    uid = store.get_or_create_user(email)
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    return uid


def purchase(uid, plan='core', state='paid', status='active', **changes):
    now = dt.datetime.now(UTC)
    expiry = now + dt.timedelta(days=20)
    sid = 'cs_test_billing_' + uuid.uuid4().hex
    store.upsert_subscription(uid, plan, expiry, stripe_session_id=sid, status=status)
    store.record_payment(uid, sid, 1234, 'eur', plan)
    with store.engine.begin() as c:
        c.execute(update(store.payments).where(store.payments.c.stripe_session_id == sid)
                  .values(state=state, paid_at=now - dt.timedelta(days=10),
                          period_end=expiry, **changes))
    return sid


def test_billing_requires_real_account_and_is_not_publicly_cacheable(client):
    response = client.get('/api/billing?session_id=cs_untrusted&user_id=untrusted')
    assert response.status_code == 401
    assert 'no-store' in response.headers['Cache-Control']


def test_free_has_no_manufactured_payment_facts_and_sales_stay_off(client):
    login(client)
    response = client.get('/api/billing')
    assert response.status_code == 200
    assert response.get_json() == {
        'entitlement': {'plan': 'free', 'status': 'free', 'access_until': None},
        'purchases': [], 'paid_sales_enabled': False,
    }
    assert 'no-store' in response.headers['Cache-Control']
    assert 'private' in response.headers['Cache-Control']
    assert client.post('/create-checkout-session', json={'plan': 'core'}).status_code == 503
    assert client.post('/api/billing', json={'plan': 'pro'}).status_code == 405


@pytest.mark.parametrize('plan', ['core', 'pro'])
def test_legacy_paid_entitlement_without_purchase_does_not_invent_history(client, plan):
    uid = login(client)
    expiry = dt.datetime.now(UTC) + dt.timedelta(days=7)
    store.upsert_subscription(uid, plan, expiry)
    result = client.get('/api/billing').get_json()
    assert result['entitlement'] == {'plan': plan, 'status': 'active', 'access_until': expiry.isoformat()}
    assert result['purchases'] == []
    assert client.get('/auth/me').get_json()['plan'] == plan


def test_billing_uses_only_owned_persisted_values_without_mutation(client):
    uid = login(client)
    sid = purchase(uid)
    other = store.get_or_create_user('billing-b@example.test')
    other_sid = purchase(other, plan='pro')
    with store.engine.begin() as c:
        c.execute(update(store.payments).where(store.payments.c.stripe_session_id == sid)
                  .values(paid_at=None, period_end=None, refund_id='re_private', payment_intent_id='pi_private'))
        before = [dict(row) for row in c.execute(select(store.payments)).mappings()]
    response = client.get('/api/billing?user_id=' + str(other) + '&session_id=' + other_sid)
    result = response.get_json()
    assert len(result['purchases']) == 1
    p = result['purchases'][0]
    assert p['reference'] == sid
    assert p['amount_cents'] == 1234  # Actual record, not the 999 list price.
    assert p['paid_at'] is None  # created_at is not a confirmed payment date.
    assert p['recorded_at'].endswith('+00:00')
    assert p['access_until'] == result['entitlement']['access_until']
    for private in [str(uid), str(other), 'billing-a@example.test', other_sid, 'pi_private', 're_private']:
        assert private not in json.dumps(result)
    assert set(p) == {'reference', 'plan', 'state', 'recorded_at', 'paid_at', 'amount_cents',
                      'currency', 'access_until', 'refund_status', 'can_request_refund'}
    with store.engine.begin() as c:
        assert before == [dict(row) for row in c.execute(select(store.payments)).mappings()]


@pytest.mark.parametrize('state', ['pending', 'unknown'])
def test_checkout_quote_is_not_a_confirmed_charge(client, state):
    uid = login(client)
    purchase(uid, state=state)
    p = client.get('/api/billing').get_json()['purchases'][0]
    assert p['amount_cents'] is None and p['currency'] is None
    assert p['can_request_refund'] is False


@pytest.mark.parametrize('state', ['refunded', 'refund_pending', 'revoked'])
def test_revoked_purchase_overrides_stale_grace_and_cannot_request_again(client, state):
    uid = login(client)
    purchase(uid, state=state, status='cancelled')
    result = client.get('/api/billing').get_json()
    assert result['entitlement']['plan'] == 'free'
    assert result['entitlement']['status'] == 'revoked'
    assert result['purchases'][0]['state'] == state
    assert result['purchases'][0]['can_request_refund'] is False


@pytest.mark.parametrize('refund_status', ['pending', 'succeeded', 'failed', 'unconfirmed', 'requires_action', 'canceled'])
def test_refund_outcome_is_projected_without_promoting_it_to_success(client, refund_status):
    uid = login(client)
    purchase(uid, state='refund_pending', refund_status=refund_status)
    p = client.get('/api/billing').get_json()['purchases'][0]
    assert p['state'] == 'refund_pending'
    assert p['refund_status'] == refund_status


def test_paid_through_and_expired_access_use_existing_entitlement_policy(client):
    uid = login(client)
    purchase(uid, status='cancelled')
    assert client.get('/api/billing').get_json()['entitlement']['status'] == 'grace'
    with store.engine.begin() as c:
        c.execute(update(store.subscriptions).where(store.subscriptions.c.user_id == store._as_uuid(uid))
                  .values(status='active', current_period_end=dt.datetime.now(UTC) - dt.timedelta(days=1)))
    result = client.get('/api/billing').get_json()
    assert result['entitlement']['plan'] == 'free' and result['entitlement']['status'] == 'expired'


def test_billing_failure_reports_unavailable_not_a_fake_free_account(client, monkeypatch, capsys):
    login(client)
    def failed(_):
        raise RuntimeError('PRIVATE_PAYMENT_VALUE')
    monkeypatch.setattr(store, 'get_billing_summary', failed)
    response = client.get('/api/billing')
    assert response.status_code == 503
    assert response.get_json() == {'error': 'billing_unavailable'}
    assert 'PRIVATE_PAYMENT_VALUE' not in capsys.readouterr().out


def test_refund_eligibility_cannot_borrow_an_unrelated_entitlement_period(client):
    uid = login(client)
    sid = purchase(uid)
    with store.engine.begin() as c:
        c.execute(update(store.payments).where(store.payments.c.stripe_session_id == sid)
                  .values(plan='pro', period_end=None))
    p = client.get('/api/billing').get_json()['purchases'][0]
    assert p['access_until'] is None and p['can_request_refund'] is False


def test_access_and_payment_display_share_one_read_snapshot(client):
    uid = login(client)
    purchase(uid)
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(store.engine, 'before_cursor_execute', capture)
    try:
        result = store.get_billing_summary(uid)
    finally:
        event.remove(store.engine, 'before_cursor_execute', capture)
    assert result['entitlement']['plan'] == 'core'
    assert len(result['purchases']) == 1
    assert len(statements) == 1 and statements[0].lstrip().upper().startswith('SELECT')


@pytest.mark.parametrize('language', ['bg', 'en'])
@pytest.mark.parametrize('sender', [appmod._send_seq_24h, appmod._send_seq_72h])
def test_billing_email_copy_does_not_sell_unavailable_or_unsupported_benefits(monkeypatch, language, sender):
    messages = []
    monkeypatch.setattr(appmod, 'send_email', lambda *args: messages.append(args) or True)
    sender({'email': 'synthetic@example.test', 'lang': language})
    assert len(messages) == 1
    body = messages[0][2]
    assert '€9.99' in body and '€14.99' in body
    assert ('coming soon' if language == 'en' else 'предстоят') in body
    assert ('no automatic renewal' if language == 'en' else 'без автоматично подновяване') in body.lower()
    assert not any(claim in body.lower() for claim in ['apex50', '50%', 'no limits', 'без никакви лимити', 'pdf'])
