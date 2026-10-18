"""Private, non-refilling test authorization. Amounts are internal micro-USD
reservations, NOT an invoice guarantee. No browser/admin HTTP API exists here.
"""
from contextlib import contextmanager
import time
import uuid
import math

from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import db
from voice.session_store import Denied


SUBJECT = "voice-test:global-safety:v1"
TTS_PILOT_RESERVATION = 100_000
TTS_PILOT_LIMIT = 400_000


class SafetyStore:
    def __init__(self, engine=None, *, require_postgres=True, clock=time.time):
        self.engine = engine if engine is not None else db.engine
        self.require_postgres, self.clock = require_postgres, clock

    def _supported(self):
        if self.engine.dialect.name != "postgresql" and self.require_postgres:
            raise Denied("postgres_safety_required")

    @contextmanager
    def locked(self):
        self._supported()
        with self.engine.connect() as connection:
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                connection.begin()
                connection.exec_driver_sql("SET LOCAL lock_timeout = '1000ms'")
                connection.exec_driver_sql("SET LOCAL statement_timeout = '1000ms'")
            try:
                query = select(db.user_preferences.c.data).where(db.user_preferences.c.subject == SUBJECT)
                if connection.dialect.name == "postgresql": query = query.with_for_update()
                row = connection.execute(query).first()
                if not row or not isinstance(row[0], dict): raise Denied("test_control_unconfigured")
                data = dict(row[0])
                yield data
                connection.execute(update(db.user_preferences).where(
                    db.user_preferences.c.subject == SUBJECT).values(data=data))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def provision(self, account, *, global_micro_usd, account_micro_usd, max_operations,
                  expires_at, tts_max_operations=4):
        """Trusted operator only. Insert once, OFF. Never refill existing state."""
        self._supported()
        account = str(uuid.UUID(str(account)))
        if (type(global_micro_usd) is not int or type(account_micro_usd) is not int
                or not 1 <= account_micro_usd <= 5_000_000 or not 1 <= global_micro_usd <= 5_000_000
                or type(max_operations) is not int or not 1 <= max_operations <= 128
                or type(tts_max_operations) is not int or not 1 <= tts_max_operations <= 8
                or not isinstance(expires_at, (int, float))
                or not self.clock() < expires_at <= self.clock() + 86400):
            raise ValueError("invalid_test_authorization")
        with self.engine.begin() as connection:
            if connection.execute(select(db.users.c.id).where(
                    db.users.c.id == uuid.UUID(account))).first() is None:
                raise Denied("account_missing")
            insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
            result = connection.execute(insert(db.user_preferences).values(id=uuid.uuid4(), subject=SUBJECT,
                data={"enabled": False, "epoch": uuid.uuid4().hex, "tester": account,
                      "global_limit": global_micro_usd, "account_limit": account_micro_usd,
                      "global_used": 0, "account_used": 0, "operation_limit": max_operations,
                      "operation_count": 0, "expires_at": expires_at, "operations": {},
                      "tts_operation_limit": tts_max_operations}
                ).on_conflict_do_nothing(index_elements=["subject"]).returning(db.user_preferences.c.id))
            if result.first() is None: raise Denied("test_control_already_provisioned")

    def read(self):
        self._supported()
        with self.engine.connect() as connection:
            row = connection.execute(select(db.user_preferences.c.data).where(
                db.user_preferences.c.subject == SUBJECT)).first()
        if not row or not isinstance(row[0], dict): raise Denied("test_control_unconfigured")
        return dict(row[0])

    def set_enabled(self, enabled):
        if type(enabled) is not bool: raise ValueError("invalid_switch")
        with self.locked() as data:
            if enabled and data.get("bound_violation"):
                raise Denied("provider_usage_bound_violated")
            data.update(enabled=enabled, epoch=uuid.uuid4().hex)

    def approve_tts_pilot(self, account):
        """Trusted owner-approved exception for this ONE existing tester only.

        Idempotent approval never resets attempts, reservations, expiry or OFF.
        $0.40 is internal authorization, not a guaranteed provider invoice cap.
        """
        account = str(uuid.UUID(str(account)))
        with self.locked() as data:
            if data.get("tester") != account:
                raise Denied("tester_mismatch")
            if data.get("tts_pilot_approved") is True:
                return
            if data.get("enabled") is not False or any(
                    op.get("kind") == "tts" for op in data.get("operations", {}).values()):
                raise Denied("tts_pilot_requires_unused_off_control")
            data.update(tts_pilot_approved=True, tts_operation_limit=4,
                        tts_pilot_limit=TTS_PILOT_LIMIT)

    def _check(self, data, account, epoch=None):
        if (data.get("enabled") is not True or data.get("bound_violation")
                or data.get("tester") != str(account)
                or type(data.get("expires_at")) not in (int, float)
                or not math.isfinite(data["expires_at"])
                or self.clock() >= data["expires_at"]
                or epoch is not None and epoch != data.get("epoch")):
            raise Denied("test_disabled")
        for name in ("global_used", "account_used", "global_limit", "account_limit",
                     "operation_count", "operation_limit"):
            if type(data.get(name)) is not int or data[name] < 0: raise Denied("invalid_test_budget")
        operations = data.get("operations")
        if (not 1 <= data["operation_limit"] <= 128
                or not 1 <= data["global_limit"] <= 5_000_000
                or not 1 <= data["account_limit"] <= 5_000_000
                or not isinstance(operations, dict) or len(operations) != data["operation_count"]
                or not isinstance(data.get("epoch"), str) or len(data["epoch"]) != 32):
            raise Denied("invalid_test_budget")
        total = 0
        for operation in operations.values():
            if (not isinstance(operation, dict) or type(operation.get("reserved")) is not int
                    or operation["reserved"] <= 0 or type(operation.get("settled")) is not bool):
                raise Denied("invalid_test_budget")
            amount = operation.get("actual") if operation["settled"] else operation["reserved"]
            if type(amount) is not int or not 0 <= amount <= operation["reserved"]:
                raise Denied("invalid_test_budget")
            total += amount
        if total != data["global_used"] or total != data["account_used"]:
            raise Denied("invalid_test_budget")
        if (data["global_used"] >= data["global_limit"] or data["account_used"] >= data["account_limit"]
                or data["operation_count"] >= data["operation_limit"]):
            raise Denied("test_budget_exhausted")

    def require(self, account, epoch=None):
        data = self.read()
        self._check(data, account, epoch)
        return data

    def reserve(self, account, auth_session, kind, maximum, *, tts_pilot=False):
        if type(maximum) is not int or maximum <= 0 or kind not in {"transcription", "gpt6", "tts"}:
            raise Denied("cost_bound_unavailable")
        # Auth is re-read here, not trusted from a cookie value or a stale worker.
        with self.engine.connect() as connection:
            row = connection.execute(select(db.sessions.c.user_id).where(
                db.sessions.c.id == uuid.UUID(str(auth_session)), db.sessions.c.expires_at > func.now(),
                db.sessions.c.revoked_at.is_(None))).first()
        if not row or str(row[0]) != str(account): raise Denied("unauthenticated")
        with self.locked() as data:
            self._check(data, account)
            if kind == "tts":
                limit = data.get("tts_operation_limit")
                if type(limit) is not int or not 1 <= limit <= 8:
                    raise Denied("tts_limits_unconfigured")
                attempts = [op for op in data["operations"].values() if op.get("kind") == "tts"]
                if tts_pilot:
                    if (data.get("tts_pilot_approved") is not True or limit != 4
                            or data.get("tts_pilot_limit") != TTS_PILOT_LIMIT
                            or maximum != TTS_PILOT_RESERVATION):
                        raise Denied("tts_pilot_not_approved")
                    if sum(op["reserved"] for op in attempts) + maximum > TTS_PILOT_LIMIT:
                        raise Denied("tts_pilot_exhausted")
                elif data.get("tts_pilot_approved") is True:
                    raise Denied("tts_pilot_model_required")
                # A worker crash/unknown provider outcome leaves its slot held.
                # Neither a timer nor a new worker may assume synthesis stopped.
                if any(op.get("tts_open", True) for op in attempts):
                    raise Denied("tts_already_active")
                if len(attempts) >= limit:
                    raise Denied("tts_operation_limit")
            if (data["global_used"] + maximum > data["global_limit"]
                    or data["account_used"] + maximum > data["account_limit"]):
                # Exhaustion is durable and also stops existing media workers.
                data["enabled"] = False
                denied = True
            else:
                denied = False
                ident = uuid.uuid4().hex
                operations = dict(data["operations"])
                operations[ident] = {"kind": kind, "reserved": maximum, "settled": False}
                if kind == "tts":
                    operations[ident].update(tts_open=True, submitted=False, tts_pilot=tts_pilot)
                data.update(global_used=data["global_used"] + maximum,
                            account_used=data["account_used"] + maximum,
                            operation_count=data["operation_count"] + 1, operations=operations)
                grant = {"id": ident, "epoch": data["epoch"], "maximum": maximum}
        if denied: raise Denied("test_budget_exhausted")
        return grant

    def tts_submitted(self, grant):
        """Persist uncertainty BEFORE provider I/O; no automatic retry thereafter."""
        with self.locked() as data:
            operation = data["operations"].get(grant["id"])
            if (data.get("enabled") is not True or data.get("epoch") != grant["epoch"]
                    or self.clock() >= data["expires_at"] or not operation
                    or operation.get("kind") != "tts" or not operation.get("tts_open")
                    or operation.get("submitted") or operation.get("settled")):
                raise Denied("tts_submission_denied")
            operations = dict(data["operations"])
            operations[grant["id"]] = dict(operation, submitted=True)
            data["operations"] = operations

    def finish_tts(self, grant, *, unused=False):
        """Release a completed slot, not its unknown bill. Refund only before I/O.

        The attempt counter never decreases. This is an internal reservation
        release, never a provider refund or evidence of zero external billing.
        """
        with self.locked() as data:
            operations = dict(data["operations"])
            operation = operations.get(grant["id"])
            if not operation or operation.get("kind") != "tts":
                raise Denied("invalid_tts_reservation")
            if unused:
                if operation.get("submitted"):
                    raise Denied("tts_submission_uncertain")
                if operation["settled"]: return
                data["global_used"] -= operation["reserved"]
                data["account_used"] -= operation["reserved"]
                operation = dict(operation, settled=True, actual=0)
            elif not operation.get("submitted"):
                raise Denied("tts_not_submitted")
            operations[grant["id"]] = dict(operation, tts_open=False)
            data["operations"] = operations

    def reconcile(self, grant, actual):
        """Only validated provider usage may release a reservation. Unknown stays held."""
        if type(actual) is not int or actual < 0: return
        with self.locked() as data:
            operations = dict(data["operations"])
            operation = operations.get(grant["id"])
            if not operation or operation["settled"]: return
            if actual > operation["reserved"]:
                data.update(enabled=False, bound_violation=True)
                return
            difference = operation["reserved"] - actual
            operations[grant["id"]] = dict(operation, settled=True, actual=actual)
            data.update(global_used=data["global_used"] - difference,
                        account_used=data["account_used"] - difference, operations=operations)


control = SafetyStore()
