"""Private Live Voice test leases in the existing shared JSON store.

The reserved ``voice-test:`` subject namespace is never read as user preferences,
profile, coaching memory or entitlements. No schema change is needed. Full time
reservations are charged up front (not refunded); this deliberately bounds tests,
not paid minutes. A lease is released only after provider hangup acknowledgement.
"""
from __future__ import annotations

from contextlib import contextmanager
import time
import uuid
import math

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import db


PREFIX = "voice-test:"


class Denied(Exception):
    pass


class SessionStore:
    def __init__(self, engine=None, clock=time.time):
        self.engine = engine if engine is not None else db.engine
        self.clock = clock
        if self.engine.dialect.name not in {"sqlite", "postgresql"}:
            raise Denied("unsupported_shared_store")

    @staticmethod
    def subject(account_id):
        return PREFIX + str(uuid.UUID(str(account_id)))

    @contextmanager
    def locked(self, account_id):
        subject = self.subject(account_id)
        with self.engine.connect() as connection:
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                connection.begin()
            try:
                query = select(db.user_preferences.c.data).where(db.user_preferences.c.subject == subject)
                if connection.dialect.name == "postgresql":
                    query = query.with_for_update()
                row = connection.execute(query).first()
                if not row or not isinstance(row[0], dict):
                    raise Denied("tester_not_authorized")
                value = dict(row[0])
                yield value
                connection.execute(update(db.user_preferences).where(
                    db.user_preferences.c.subject == subject).values(data=value))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def configure(self, account_id, *, authorized, session_seconds=120, aggregate_seconds=600):
        """Server/operator-only configuration. No browser endpoint calls this."""
        if (type(authorized) is not bool or type(session_seconds) is not int or type(aggregate_seconds) is not int
                or not (15 <= session_seconds <= 300 and session_seconds <= aggregate_seconds <= 1800)):
            raise ValueError("invalid_test_limits")
        subject = self.subject(account_id)
        with self.engine.begin() as connection:
            query = select(db.users.c.id).where(db.users.c.id == uuid.UUID(str(account_id)))
            if connection.execute(query).first() is None:
                raise Denied("account_missing")
            # Initialize denied, without overwriting an existing quota or lease.
            insert = sqlite_insert if connection.dialect.name == "sqlite" else pg_insert
            connection.execute(insert(db.user_preferences).values(id=uuid.uuid4(), subject=subject,
                data={"authorized": False, "window_start": self.clock(), "used_seconds": 0,
                      "lease": None}).on_conflict_do_nothing(index_elements=["subject"]))
        with self.locked(account_id) as data:
            data.update(authorized=bool(authorized), session_seconds=session_seconds,
                        aggregate_seconds=aggregate_seconds)

    def read(self, account_id):
        with self.engine.connect() as connection:
            row = connection.execute(select(db.user_preferences.c.data).where(
                db.user_preferences.c.subject == self.subject(account_id))).first()
        if not row or not isinstance(row[0], dict):
            raise Denied("tester_not_authorized")
        return dict(row[0])

    def authorized(self, account_id):
        return self.read(account_id).get("authorized") is True

    def reserve(self, account_id, auth_session):
        if not auth_session:
            raise Denied("unauthenticated")
        now = self.clock()
        with self.locked(account_id) as data:
            if data.get("authorized") is not True:
                raise Denied("tester_not_authorized")
            if data.get("lease"):
                raise Denied("session_already_reserved")
            duration = data.get("session_seconds")
            budget = data.get("aggregate_seconds")
            if type(duration) is not int or type(budget) is not int or not (15 <= duration <= 300):
                raise Denied("invalid_test_policy")
            if not duration <= budget <= 1800:
                raise Denied("invalid_test_policy")
            start, used = data.get("window_start"), data.get("used_seconds")
            if (not isinstance(start, (int, float)) or not math.isfinite(start)
                    or type(used) is not int or used < 0 or now < start):
                raise Denied("invalid_usage_state")
            if now - start >= 86400:
                start, used = now, 0
            if used + duration > budget:
                raise Denied("usage_exhausted")
            lease = {"id": uuid.uuid4().hex, "auth_session": str(auth_session),
                     "deadline": now + duration, "seconds": duration, "call_id": None,
                     "state": "connecting"}
            data.update(window_start=start, used_seconds=used + duration, lease=lease)
        return dict(lease)

    def attach(self, account_id, lease_id, call_id):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if not lease or lease.get("id") != lease_id or lease.get("call_id"):
                raise Denied("lease_changed")
            lease = dict(lease, call_id=call_id, state="active")
            data["lease"] = lease
        return lease

    def require_lease(self, account_id, lease_id):
        data = self.read(account_id)
        lease = data.get("lease")
        if not isinstance(lease, dict) or lease.get("id") != lease_id:
            raise Denied("lease_missing")
        return data, dict(lease)

    def bind_media(self, account_id, lease_id, owner):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if not lease or lease.get("id") != lease_id or lease.get("state") != "connecting":
                raise Denied("lease_changed")
            data["lease"] = dict(lease, transport="relay", media_owner=owner, state="active")
        return dict(data["lease"])

    def request_stop(self, account_id, lease_id):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if lease and lease.get("id") == lease_id:
                data["lease"] = dict(lease, state="stop_requested")

    def media_finished(self, account_id, lease_id, *, confirmed, facts):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if not lease or lease.get("id") != lease_id:
                return
            data["last_media"] = {"lease": lease_id, **facts, "provider_close_ack": bool(confirmed)}
            data["lease"] = None if confirmed else dict(lease, state="termination_unconfirmed")

    def media_checkpoint(self, account_id, lease_id, *, accepted_samples, usage):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if not lease or lease.get("id") != lease_id or lease.get("state") != "active":
                raise Denied("lease_changed")
            data["lease"] = dict(lease, accepted_samples=accepted_samples, usage=usage)

    def claim_stop(self, account_id, lease_id):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if not lease or lease.get("id") != lease_id:
                return None
            if lease.get("stop_claim_until", 0) > self.clock() or lease.get("stop_attempts", 0) >= 2:
                return None
            lease = dict(lease, state="terminating", stop_claim_until=self.clock() + 10,
                         stop_attempts=lease.get("stop_attempts", 0) + 1)
            data["lease"] = lease
        return lease

    def finish(self, account_id, lease_id, *, provider_confirmed):
        with self.locked(account_id) as data:
            lease = data.get("lease")
            if not lease or lease.get("id") != lease_id:
                return
            if provider_confirmed:
                data["lease"] = None
            else:
                data["lease"] = dict(lease, state="termination_unconfirmed")

    def active(self):
        with self.engine.connect() as connection:
            rows = connection.execute(select(db.user_preferences.c.subject, db.user_preferences.c.data).where(
                db.user_preferences.c.subject.like(PREFIX + "%"))).all()
        return [(subject[len(PREFIX):], dict(data["lease"])) for subject, data in rows
                if isinstance(data, dict) and isinstance(data.get("lease"), dict)]
