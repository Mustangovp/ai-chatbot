"""Regression coverage for one-time Stripe Checkout entitlement recovery."""
import base64
import datetime as dt
import os
import time
import types

import pytest

import app as appmod
import db as store


UTC = dt.timezone.utc


def _expiry(token):
    padded = token + "=" * (-len(token) % 4)
    return int(base64.urlsafe_b64decode(padded).decode().split(".")[0])


def _paid_session(session_id, email="poll@example.com", plan="core"):
    return types.SimpleNamespace(
        id=session_id,
        payment_status="paid",
        metadata={"plan": plan},
        customer_details=types.SimpleNamespace(email=email),
        customer=None,
        amount_total=999,
        currency="eur",
    )


@pytest.fixture
def client():
    db_path = store.DATABASE_URL.removeprefix("sqlite:///")
    assert os.path.basename(db_path) == "test.db"
    assert os.path.basename(os.path.dirname(db_path)).startswith("apex_test_")
    appmod.app.config["TESTING"] = True
    appmod._pending_tokens.clear()
    appmod._poll_rate.clear()
    return appmod.app.test_client()


def test_first_redemption_creates_one_entitlement_period(client, monkeypatch):
    session_id = "cs_test_first_redemption"
    monkeypatch.setattr(appmod.stripe.checkout.Session, "retrieve",
                        lambda supplied_id: _paid_session(supplied_id))

    before = int(time.time())
    response = client.get(f"/poll-token?session_id={session_id}")
    data = response.get_json()

    assert data["ready"] is True
    uid = store.get_checkout_session_user(session_id)
    sub = store.get_subscription(uid)
    assert sub["plan"] == "core" and sub["status"] == "active"
    recorded_end = dt.datetime.fromisoformat(sub["current_period_end"])
    if recorded_end.tzinfo is None:
        recorded_end = recorded_end.replace(tzinfo=UTC)
    assert _expiry(data["token"]) == int(recorded_end.timestamp())
    assert before + 30 * 24 * 3600 <= _expiry(data["token"]) <= int(time.time()) + 30 * 24 * 3600


def test_replay_uses_the_recorded_expiry(client, monkeypatch):
    session_id = "cs_test_replay"
    uid = store.get_or_create_user("replay@example.com")
    expiry = dt.datetime.now(UTC) + dt.timedelta(days=9)
    store.upsert_subscription(uid, "pro", expiry, stripe_session_id=session_id)
    store.record_payment(uid, session_id, 1499, "eur", "pro")

    monkeypatch.setattr(appmod.stripe.checkout.Session, "retrieve",
                        lambda *_: pytest.fail("redeemed session must not call Stripe fallback"))
    response = client.get(f"/poll-token?session_id={session_id}")
    data = response.get_json()

    assert data["ready"] is True
    assert _expiry(data["token"]) == int(expiry.timestamp())


def test_replay_after_expiry_returns_not_ready(client, monkeypatch):
    session_id = "cs_test_expired"
    uid = store.get_or_create_user("expired@example.com")
    expired = dt.datetime.now(UTC) - dt.timedelta(seconds=1)
    store.upsert_subscription(uid, "core", expired, stripe_session_id=session_id)
    store.record_payment(uid, session_id, 999, "eur", "core")

    monkeypatch.setattr(appmod.stripe.checkout.Session, "retrieve",
                        lambda *_: pytest.fail("expired replay must not call Stripe fallback"))
    response = client.get(f"/poll-token?session_id={session_id}")

    assert response.get_json() == {"ready": False}


def test_malformed_subscription_cannot_fall_through_to_new_entitlement(client, monkeypatch):
    session_id = "cs_test_malformed"
    uid = store.get_or_create_user("malformed@example.com")
    store.record_payment(uid, session_id, 999, "eur", "core")

    monkeypatch.setattr(appmod.store, "get_subscription", lambda _: {
        "plan": "core", "status": "active", "current_period_end": "not-a-date",
    })
    monkeypatch.setattr(appmod.stripe.checkout.Session, "retrieve",
                        lambda *_: pytest.fail("malformed replay must not call Stripe fallback"))
    response = client.get(f"/poll-token?session_id={session_id}")

    assert response.get_json() == {"ready": False}
