"""
APEX — persistence layer (the source of truth).

Runs identically on Postgres (production, via DATABASE_URL) and SQLite
(local dev) through SQLAlchemy Core. The browser is only a cache; every
account-owned object lives here.

Design guarantees requested for 1.0:
  • Email is the canonical user identity (passwordless magic-link).
  • Every object uses a UUID primary key + created/updated timestamps.
  • Auth is provider-agnostic (auth_identities) so Google/Apple Sign-In can be
    added later with zero schema redesign — magic-link is just provider='email'.
  • coach_id / source columns are present (nullable) so multiple AI coaches and
    wearable data sources can be added later without a migration redesign.
"""
import os, uuid, hashlib, secrets, datetime as _dt
from sqlalchemy import (
    create_engine, MetaData, Table, Column, String, Integer, Boolean,
    DateTime, JSON, ForeignKey, UniqueConstraint, Index, func, select, update, insert, delete
)
from sqlalchemy.types import Uuid
from sqlalchemy.exc import IntegrityError

# ── Engine ────────────────────────────────────────────────────────────────────
def _normalize_url(url: str) -> str:
    if not url:
        return ""
    # Railway/Heroku hand out postgres:// ; SQLAlchemy 2.x wants an explicit driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

_DEFAULT_SQLITE = "sqlite:///" + os.path.join(os.path.dirname(__file__), "data", "apex.db")
DATABASE_URL = _normalize_url(os.getenv("DATABASE_URL", "")) or _DEFAULT_SQLITE
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
    engine = create_engine(DATABASE_URL, future=True, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, pool_recycle=280)

metadata = MetaData()

def _uuid_col():
    return Column("id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

def _ts(**kw):
    return Column(DateTime(timezone=True), server_default=func.now(), **kw)

# ── Schema ────────────────────────────────────────────────────────────────────
users = Table("users", metadata,
    _uuid_col(),
    Column("email", String(320), nullable=False, unique=True),   # stored lowercase
    Column("stripe_customer_id", String(80)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

auth_identities = Table("auth_identities", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("provider", String(32), nullable=False),      # 'email' | 'google' | 'apple' | …
    Column("provider_uid", String(320), nullable=False), # email address or OAuth subject
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("provider", "provider_uid", name="uq_provider_uid"),
)

login_tokens = Table("login_tokens", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

sessions = Table("sessions", metadata,
    _uuid_col(),  # the id IS the opaque session cookie value
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

subscriptions = Table("subscriptions", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("plan", String(16), nullable=False, default="free"),        # free | core | pro
    Column("status", String(16), nullable=False, default="free"),      # free | active | expired | cancelled | grace
    Column("current_period_end", DateTime(timezone=True)),
    Column("stripe_customer_id", String(80)),
    Column("stripe_session_id", String(120)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

payments = Table("payments", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("stripe_session_id", String(120), unique=True),
    Column("amount_cents", Integer),
    Column("currency", String(8), default="eur"),
    Column("plan", String(16)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# Free usage belongs to the account when logged in; before login it is keyed by a
# server-issued device id (httpOnly cookie) + IP — never by client-writable storage.
free_usage = Table("free_usage", metadata,
    _uuid_col(),
    Column("subject_type", String(8), nullable=False),   # 'user' | 'device'
    Column("subject_id", String(80), nullable=False),
    Column("count", Integer, nullable=False, default=0),
    Column("window_start", DateTime(timezone=True), server_default=func.now()),
    Column("bonus", Boolean, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("subject_type", "subject_id", name="uq_free_subject"),
)

profiles = Table("profiles", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("data", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

workout_history = Table("workout_history", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("coach_id", Uuid(as_uuid=True)),     # future: multiple AI coaches
    Column("source", String(32)),               # future: 'app' | 'wearable:garmin' | …
    Column("occurred_at", DateTime(timezone=True), server_default=func.now()),
    Column("type", String(64)),
    Column("exercises", JSON),                  # [{name,sets,reps,weight}]
    Column("difficulty", String(24)),
    Column("completion", Integer),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_workout_user_occurred", "user_id", "occurred_at"),
)

nutrition_history = Table("nutrition_history", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("coach_id", Uuid(as_uuid=True)),
    Column("content", JSON),                    # rendered meals / raw text
    Column("macros", JSON),                     # {protein,carbs,fat,kcal}
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_nutrition_user_created", "user_id", "created_at"),
)

# Durable long-term coaching memory — the timeline. One row per meaningful event.
coach_memory = Table("coach_memory", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("coach_id", Uuid(as_uuid=True)),
    Column("source", String(32)),
    Column("kind", String(32), nullable=False), # workout | nutrition | consultation | recommendation | note | recovery
    Column("payload", JSON),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_memory_user_created", "user_id", "created_at"),
)

# Full chat transcript, account-owned. Loads on any device so the coach continues.
conversations = Table("conversations", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("coach_id", Uuid(as_uuid=True)),
    Column("role", String(16), nullable=False), # 'user' | 'assistant'
    Column("content", JSON),                    # message text
    Column("lang", String(4)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_conv_user_created", "user_id", "created_at"),
)

# ── Brain substrate (M0) ──────────────────────────────────────────────────────
# The Athlete Model state, one row per account. The browser is only a cache;
# this row is the source of truth the Brain reads. Additive — nothing else moves.
athlete_models = Table("athlete_models", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
           nullable=False, unique=True),
    Column("schema", String(32), nullable=False),
    Column("state", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

# Append-only decision ledger (Event Ledger). Created inert in M0; first written
# in M1. user_id nullable so anonymous decisions can be recorded later.
brain_decisions = Table("brain_decisions", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")),
    Column("verdict", String(16)),               # GO|MODIFY|NOT_YET|NO_TRAIN
    Column("intervention", String(32)),
    Column("urgency", String(16)),               # EMERGENCY_now|URGENT_soon|ROUTINE_mention|null
    Column("enforced", Boolean, default=False),  # shadow vs authoritative
    Column("out_of_mandate", Boolean, default=False),
    Column("trace", JSON),                        # per-station reasoning (never user-facing)
    Column("message_hash", String(64)),           # sha256 of the message; no raw text
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_brain_user_created", "user_id", "created_at"),
)

# M5 Brain Observatory — one analytics row per enforced Brain decision. Additive,
# no PII (anon_id is a one-way hash), never read by the Brain. Observability only.
brain_events = Table("brain_events", metadata,
    _uuid_col(),
    Column("anon_id", String(32)),                        # sha256(subject)[:32] — not reversible
    Column("verdict", String(16)),                        # GO|MODIFY|NOT_YET|NO_TRAIN
    Column("urgency", String(16)),                        # EMERGENCY_now|URGENT_soon|ROUTINE_mention|null
    Column("intervention", String(32)),
    Column("route", String(32)),                          # route_target or null
    Column("cold_start", Boolean, default=False),
    Column("enforcement_generate", Boolean, default=False),
    Column("latency_ms", Integer),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_brain_events_created", "created_at"),
)

schema_version = Table("schema_version", metadata,
    Column("version", Integer, primary_key=True),
    Column("applied_at", DateTime(timezone=True), server_default=func.now()),
)

# Ordered, idempotent migrations. create_all() builds the base schema; each numbered
# step below runs once (recorded in schema_version) so future ALTERs deploy cleanly
# without dropping data. Add new steps by appending — never edit an applied one.
_MIGRATIONS = [
    # (version, callable(connection) -> None)
    (1, lambda c: None),  # baseline: tables created by metadata.create_all()
    (2, lambda c: None),  # M0: athlete_models table (created by create_all)
    (3, lambda c: None),  # M0: brain_decisions ledger (created by create_all)
    (4, lambda c: None),  # M5: brain_events observatory table (created by create_all)
]

def run_migrations():
    """Create the base schema, then apply any pending versioned migrations.

    Resilient creation: a single pre-existing object (e.g. an index orphaned by a
    past partial deploy) must NOT abort the whole run and leave newer tables
    uncreated. We try the fast bulk path first, then fall back to per-table
    checkfirst creation so every missing table is still created."""
    try:
        metadata.create_all(engine, checkfirst=True)
    except Exception as e:
        print(f"[db] create_all bulk path failed ({e}); creating tables individually")
        for table in metadata.sorted_tables:
            try:
                table.create(engine, checkfirst=True)
            except Exception as te:
                print(f"[db] table {table.name} create skipped: {te}")
    with engine.begin() as c:
        applied = {r[0] for r in c.execute(select(schema_version.c.version)).all()}
        for version, fn in _MIGRATIONS:
            if version in applied:
                continue
            fn(c)
            c.execute(insert(schema_version).values(version=version))
    print(f"[db] migrations up to v{_MIGRATIONS[-1][0]} applied")

# Backwards-compatible alias.
def init_db():
    run_migrations()

# ── Helpers ───────────────────────────────────────────────────────────────────
def _now():
    return _dt.datetime.now(_dt.timezone.utc)

def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

# ── Users / identity ──────────────────────────────────────────────────────────
def get_or_create_user(email: str, stripe_customer_id: str = None):
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return None
    with engine.begin() as c:
        row = c.execute(select(users).where(users.c.email == email)).mappings().first()
        if row:
            uid = row["id"]
            if stripe_customer_id and not row["stripe_customer_id"]:
                c.execute(update(users).where(users.c.id == uid).values(stripe_customer_id=stripe_customer_id))
        else:
            uid = uuid.uuid4()
            c.execute(insert(users).values(id=uid, email=email, stripe_customer_id=stripe_customer_id))
            c.execute(insert(auth_identities).values(id=uuid.uuid4(), user_id=uid, provider="email", provider_uid=email))
            c.execute(insert(subscriptions).values(id=uuid.uuid4(), user_id=uid, plan="free", status="free"))
        return str(uid)

def get_user(user_id):
    with engine.begin() as c:
        row = c.execute(select(users).where(users.c.id == _as_uuid(user_id))).mappings().first()
        return dict(row) if row else None

def _as_uuid(v):
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))

# ── Magic-link auth ───────────────────────────────────────────────────────────
def create_login_token(user_id, ttl_minutes=20) -> str:
    raw = secrets.token_urlsafe(32)
    with engine.begin() as c:
        c.execute(insert(login_tokens).values(
            id=uuid.uuid4(), user_id=_as_uuid(user_id), token_hash=_hash(raw),
            expires_at=_now() + _dt.timedelta(minutes=ttl_minutes)))
    return raw

def consume_login_token(raw: str):
    if not raw:
        return None
    h = _hash(raw)
    with engine.begin() as c:
        row = c.execute(select(login_tokens).where(login_tokens.c.token_hash == h)).mappings().first()
        if not row or row["used_at"] is not None:
            return None
        exp = row["expires_at"]
        if exp and _aware(exp) < _now():
            return None
        c.execute(update(login_tokens).where(login_tokens.c.id == row["id"]).values(used_at=_now()))
        return str(row["user_id"])

def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=_dt.timezone.utc)

# ── Sessions ──────────────────────────────────────────────────────────────────
def create_session(user_id, ttl_days=90) -> str:
    sid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(insert(sessions).values(
            id=sid, user_id=_as_uuid(user_id), expires_at=_now() + _dt.timedelta(days=ttl_days)))
    return str(sid)

def get_session_user(session_id):
    if not session_id:
        return None
    try:
        sid = _as_uuid(session_id)
    except Exception:
        return None
    with engine.begin() as c:
        row = c.execute(select(sessions).where(sessions.c.id == sid)).mappings().first()
        if not row or row["revoked_at"] is not None:
            return None
        if _aware(row["expires_at"]) < _now():
            return None
        u = c.execute(select(users).where(users.c.id == row["user_id"])).mappings().first()
        return dict(u) if u else None

def revoke_session(session_id):
    try:
        sid = _as_uuid(session_id)
    except Exception:
        return
    with engine.begin() as c:
        c.execute(update(sessions).where(sessions.c.id == sid).values(revoked_at=_now()))

# ── Subscriptions (server truth) ──────────────────────────────────────────────
_FREE_SUB = {"plan": "free", "status": "free", "current_period_end": None}

def get_subscription(user_id):
    # RV-3: never raise. If the database is momentarily unavailable, degrade to FREE
    # so the app keeps working (no 500, no broken UI) until the DB recovers.
    try:
        with engine.begin() as c:
            row = c.execute(select(subscriptions).where(subscriptions.c.user_id == _as_uuid(user_id))).mappings().first()
    except Exception as e:
        print(f"[db] get_subscription degraded to FREE (DB unavailable): {e}")
        return dict(_FREE_SUB)
    if not row:
        return {"plan": "free", "status": "free", "current_period_end": None}
    plan, status, cpe = row["plan"], row["status"], row["current_period_end"]
    # Derive live status from the period end — never trust a stale row.
    if plan != "free" and cpe is not None:
        end = _aware(cpe)
        if status == "cancelled":
            status = "cancelled" if end < _now() else "grace"   # cancelled but still paid through period
        elif end < _now():
            status, plan = "expired", "free"
    return {"plan": plan if status in ("active", "grace") else ("free" if status in ("expired", "free") else plan),
            "status": status, "current_period_end": cpe.isoformat() if cpe else None}

def upsert_subscription(user_id, plan, period_end, stripe_customer_id=None, stripe_session_id=None, status="active"):
    with engine.begin() as c:
        exists = c.execute(select(subscriptions.c.id).where(subscriptions.c.user_id == _as_uuid(user_id))).first()
        vals = dict(plan=plan, status=status, current_period_end=period_end,
                    stripe_customer_id=stripe_customer_id, stripe_session_id=stripe_session_id)
        if exists:
            c.execute(update(subscriptions).where(subscriptions.c.user_id == _as_uuid(user_id)).values(**vals))
        else:
            c.execute(insert(subscriptions).values(id=uuid.uuid4(), user_id=_as_uuid(user_id), **vals))

def cancel_subscription(user_id):
    with engine.begin() as c:
        c.execute(update(subscriptions).where(subscriptions.c.user_id == _as_uuid(user_id)).values(status="cancelled"))

def record_payment(user_id, stripe_session_id, amount_cents, currency, plan):
    with engine.begin() as c:
        exists = c.execute(select(payments.c.id).where(payments.c.stripe_session_id == stripe_session_id)).first()
        if not exists:
            c.execute(insert(payments).values(id=uuid.uuid4(), user_id=_as_uuid(user_id),
                stripe_session_id=stripe_session_id, amount_cents=amount_cents, currency=currency, plan=plan))

def list_payments(user_id):
    with engine.begin() as c:
        rows = c.execute(select(payments).where(payments.c.user_id == _as_uuid(user_id))
                         .order_by(payments.c.created_at.desc())).mappings().all()
    return [dict(r) for r in rows]

# ── Free usage (server-authoritative, never client-trusted) ──────────────────
def free_usage_state(subject_type, subject_id, limit, window_seconds, bonus_extra=0):
    """Return current quota state without mutating (for read-only checks)."""
    with engine.begin() as c:
        row = c.execute(select(free_usage).where(
            (free_usage.c.subject_type == subject_type) & (free_usage.c.subject_id == subject_id))).mappings().first()
    return _quota_from_row(row, limit, window_seconds, bonus_extra)

def free_usage_consume(subject_type, subject_id, limit, window_seconds, bonus_extra=0):
    """Atomically roll the window if expired, enforce the limit, and consume one
    message if allowed. Returns {allowed, count, remaining, reset_in, limit}.

    Concurrency-safe: an existing row is locked (SELECT ... FOR UPDATE on Postgres)
    so parallel updates serialize; a concurrent FIRST insert that loses the unique
    race raises IntegrityError, which we swallow and retry on the now-existing row
    (read/update path). A user must never see a 500 from double-clicks or retries.
    """
    for _attempt in range(4):
        try:
            with engine.begin() as c:
                sel = select(free_usage).where(
                    (free_usage.c.subject_type == subject_type) & (free_usage.c.subject_id == subject_id))
                if not IS_SQLITE:
                    sel = sel.with_for_update()
                row = c.execute(sel).mappings().first()
                now = _now()
                if row is None:
                    c.execute(insert(free_usage).values(id=uuid.uuid4(), subject_type=subject_type,
                        subject_id=subject_id, count=1, window_start=now, bonus=False))
                    return _quota(1, limit, window_seconds, now)
                start = _aware(row["window_start"]) if row["window_start"] else now
                eff_limit = limit + (bonus_extra if row["bonus"] else 0)
                # Window expired → reset.
                if (now - start).total_seconds() >= window_seconds:
                    c.execute(update(free_usage).where(free_usage.c.id == row["id"]).values(count=1, window_start=now))
                    return _quota(1, eff_limit, window_seconds, now)
                count = row["count"] or 0
                if count >= eff_limit:
                    return _quota(count, eff_limit, window_seconds, start, allowed=False)
                c.execute(update(free_usage).where(free_usage.c.id == row["id"]).values(count=count + 1))
                return _quota(count + 1, eff_limit, window_seconds, start)
        except IntegrityError:
            # A concurrent first-insert won the race; loop re-reads the existing row.
            continue
    # Should never reach here; fail OPEN (allow) rather than error the user.
    return _quota(1, limit, window_seconds, _now())

def free_usage_grant_bonus(subject_type, subject_id):
    with engine.begin() as c:
        c.execute(update(free_usage).where(
            (free_usage.c.subject_type == subject_type) & (free_usage.c.subject_id == subject_id)).values(bonus=True))

def free_usage_refund(subject_type, subject_id):
    with engine.begin() as c:
        row = c.execute(select(free_usage).where(
            (free_usage.c.subject_type == subject_type) & (free_usage.c.subject_id == subject_id)).mappings().first()
        )
        if row and (row["count"] or 0) > 0:
            c.execute(update(free_usage).where(free_usage.c.id == row["id"]).values(count=row["count"] - 1))

def _quota(count, limit, window_seconds, start, allowed=True):
    reset_in = max(0, int(window_seconds - (_now() - _aware(start)).total_seconds()))
    return {"allowed": allowed, "count": count, "limit": limit,
            "remaining": max(0, limit - count), "reset_in": reset_in,
            "hours_left": max(1, reset_in // 3600 + 1)}

def _quota_from_row(row, limit, window_seconds, bonus_extra):
    now = _now()
    if not row:
        return {"allowed": True, "count": 0, "limit": limit, "remaining": limit,
                "reset_in": window_seconds, "hours_left": max(1, window_seconds // 3600)}
    start = _aware(row["window_start"]) if row["window_start"] else now
    eff = limit + (bonus_extra if row["bonus"] else 0)
    if (now - start).total_seconds() >= window_seconds:
        return {"allowed": True, "count": 0, "limit": eff, "remaining": eff,
                "reset_in": window_seconds, "hours_left": max(1, window_seconds // 3600)}
    count = row["count"] or 0
    return _quota(count, eff, window_seconds, start, allowed=count < eff)

# ── Profile ───────────────────────────────────────────────────────────────────
def get_profile(user_id):
    with engine.begin() as c:
        row = c.execute(select(profiles).where(profiles.c.user_id == _as_uuid(user_id))).mappings().first()
    return dict(row["data"]) if row and row["data"] else {}

def save_profile(user_id, data: dict):
    data = data or {}
    with engine.begin() as c:
        exists = c.execute(select(profiles.c.id).where(profiles.c.user_id == _as_uuid(user_id))).first()
        if exists:
            c.execute(update(profiles).where(profiles.c.user_id == _as_uuid(user_id)).values(data=data))
        else:
            c.execute(insert(profiles).values(id=uuid.uuid4(), user_id=_as_uuid(user_id), data=data))

# ── Workout / nutrition / conversation / memory (the account timeline) ────────
def log_workout(user_id, session: dict):
    wid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(insert(workout_history).values(
            id=wid, user_id=_as_uuid(user_id), type=session.get("type"),
            exercises=session.get("exercises"), difficulty=session.get("diff"),
            completion=session.get("completion"), source="app"))
        c.execute(insert(coach_memory).values(id=uuid.uuid4(), user_id=_as_uuid(user_id),
            kind="workout", source="app", payload=session))
    return str(wid)

def add_memory_event(user_id, kind, payload, source="app"):
    with engine.begin() as c:
        c.execute(insert(coach_memory).values(id=uuid.uuid4(), user_id=_as_uuid(user_id),
            kind=kind, payload=payload, source=source))

def save_nutrition(user_id, content, macros=None):
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(insert(nutrition_history).values(id=nid, user_id=_as_uuid(user_id),
            content=content, macros=macros))
        c.execute(insert(coach_memory).values(id=uuid.uuid4(), user_id=_as_uuid(user_id),
            kind="nutrition", source="app", payload={"macros": macros}))
    return str(nid)

def list_nutrition(user_id, limit=30):
    with engine.begin() as c:
        rows = c.execute(select(nutrition_history).where(nutrition_history.c.user_id == _as_uuid(user_id))
                         .order_by(nutrition_history.c.created_at.desc()).limit(limit)).mappings().all()
    return [_serial(r) for r in rows]

def add_conversation(user_id, role, content, lang=None):
    with engine.begin() as c:
        c.execute(insert(conversations).values(id=uuid.uuid4(), user_id=_as_uuid(user_id),
            role=role, content=content, lang=lang))

def list_conversation(user_id, limit=40):
    """Most recent messages, returned oldest→newest for prompt/context replay."""
    with engine.begin() as c:
        rows = c.execute(select(conversations).where(conversations.c.user_id == _as_uuid(user_id))
                         .order_by(conversations.c.created_at.desc()).limit(limit)).mappings().all()
    out = [{"role": r["role"], "content": r["content"]} for r in rows]
    out.reverse()
    return out

def list_workouts(user_id, limit=60):
    with engine.begin() as c:
        rows = c.execute(select(workout_history).where(workout_history.c.user_id == _as_uuid(user_id))
                         .order_by(workout_history.c.occurred_at.desc()).limit(limit)).mappings().all()
    return [_serial(r) for r in rows]

def list_timeline(user_id, limit=100):
    with engine.begin() as c:
        rows = c.execute(select(coach_memory).where(coach_memory.c.user_id == _as_uuid(user_id))
                         .order_by(coach_memory.c.created_at.desc()).limit(limit)).mappings().all()
    return [_serial(r) for r in rows]

def _serial(row):
    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, _dt.datetime):
            d[k] = _aware(v).isoformat()
    return d

def build_memory_context(user_id, en=True):
    """Pre-formatted [WORKOUT MEMORY] block from the DB, injected into the prompt
    so the AI remembers the person — not the browser."""
    wks = list_workouts(user_id, limit=30)
    if not wks:
        return ""
    now = _now()
    last = wks[0]
    L = []
    L.append("[WORKOUT MEMORY]" if en else "[ТРЕНИРОВЪЧНА ПАМЕТ]")
    L.append(("  Completed sessions: " if en else "  Завършени сесии: ") + str(len(wks)))
    def _within(days):
        cnt = 0
        for w in wks:
            try:
                if (now - _aware(_dt.datetime.fromisoformat(w["occurred_at"]))).days < days:
                    cnt += 1
            except Exception:
                pass
        return cnt
    L.append(("  Frequency (7d): " if en else "  Честота (7д): ") + str(_within(7)) + ("/week" if en else "/седмица"))
    exs = last.get("exercises") or []
    exs_str = ", ".join(f"{e.get('name')} {e.get('sets')}×{e.get('reps')}" +
                        (f" @{e.get('weight')}kg" if e.get('weight') else "") for e in exs)
    try:
        occ = _aware(_dt.datetime.fromisoformat(last["occurred_at"]))
        just = (now - occ).total_seconds() < 2 * 3600
        date_str = occ.strftime("%Y-%m-%d")
    except Exception:
        just, date_str = False, ""
    L.append(("  Last session: " if en else "  Последна сесия: ") + date_str + " — " +
             str(last.get("type") or "training") + ((" (" + exs_str + ")") if exs_str else ""))
    if just:
        L.append("  ⚡ POST-WORKOUT — finished within the last 2 hours. Acknowledge it; do NOT prescribe a new workout."
                 if en else
                 "  ⚡ СЛЕД ТРЕНИРОВКА — завършена в последните 2 часа. Признай я; НЕ предлагай нова тренировка.")
    return "\n".join(L)

# ── Brain substrate persistence (M0) ─────────────────────────────────────────
def get_athlete_state(user_id):
    """Return the stored Athlete Model state dict, or None if none exists yet."""
    with engine.begin() as c:
        row = c.execute(select(athlete_models).where(
            athlete_models.c.user_id == _as_uuid(user_id))).mappings().first()
    return dict(row["state"]) if row and row["state"] else None

def save_athlete_state(user_id, state: dict):
    """Upsert the Athlete Model state for a user. Concurrency-safe on Postgres via
    SELECT … FOR UPDATE (the same pattern as free_usage); a no-op lock on SQLite."""
    state = state or {}
    schema = str(state.get("schema", "athlete-model-v1"))[:32]
    with engine.begin() as c:
        sel = select(athlete_models.c.id).where(athlete_models.c.user_id == _as_uuid(user_id))
        if not IS_SQLITE:
            sel = sel.with_for_update()
        exists = c.execute(sel).first()
        if exists:
            c.execute(update(athlete_models).where(
                athlete_models.c.user_id == _as_uuid(user_id)).values(state=state, schema=schema))
        else:
            c.execute(insert(athlete_models).values(
                id=uuid.uuid4(), user_id=_as_uuid(user_id), schema=schema, state=state))

def log_decision(user_id, verdict=None, intervention=None, urgency=None,
                 enforced=False, out_of_mandate=False, trace=None, message_hash=None,
                 decision_id=None):
    """Append one decision record to the ledger. `decision_id` sets a stable id
    (so the trace's decision_id == the row id); generated if not supplied."""
    with engine.begin() as c:
        c.execute(insert(brain_decisions).values(
            id=(_as_uuid(decision_id) if decision_id else uuid.uuid4()),
            user_id=(_as_uuid(user_id) if user_id else None),
            verdict=verdict, intervention=intervention, urgency=urgency,
            enforced=bool(enforced), out_of_mandate=bool(out_of_mandate),
            trace=trace, message_hash=message_hash))

def get_brain_decision(decision_id):
    """Fetch one decision record (serialized) by id, for the debug inspector."""
    try:
        did = _as_uuid(decision_id)
    except Exception:
        return None
    with engine.begin() as c:
        row = c.execute(select(brain_decisions).where(brain_decisions.c.id == did)).mappings().first()
    return _serial(dict(row)) if row else None


# ── M5 Brain Observatory — analytics writes + aggregates (no PII, obs-only) ──
def log_brain_event(anon_id, verdict=None, urgency=None, intervention=None, route=None,
                    cold_start=False, enforcement_generate=False, latency_ms=None):
    """Append one analytics row for an enforced Brain decision. Never read by the Brain."""
    with engine.begin() as c:
        c.execute(insert(brain_events).values(
            id=uuid.uuid4(), anon_id=anon_id, verdict=verdict, urgency=urgency,
            intervention=intervention, route=route, cold_start=bool(cold_start),
            enforcement_generate=bool(enforcement_generate), latency_ms=latency_ms))


def _since(hours=0, days=0):
    return _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours, days=days)


def brain_events_stats(hours=24):
    """Aggregate stats over a rolling window (DB-agnostic; cutoff computed in Python)."""
    cutoff = _since(hours=hours)
    t = brain_events
    with engine.begin() as c:
        total = c.execute(select(func.count()).select_from(t).where(t.c.created_at >= cutoff)).scalar() or 0
        verdicts = dict(c.execute(select(t.c.verdict, func.count())
                                  .where(t.c.created_at >= cutoff).group_by(t.c.verdict)).all())
        interventions = dict(c.execute(select(t.c.intervention, func.count())
                                       .where(t.c.created_at >= cutoff).group_by(t.c.intervention)).all())
        cold = c.execute(select(func.count()).select_from(t)
                         .where(t.c.created_at >= cutoff).where(t.c.cold_start == True)).scalar() or 0  # noqa: E712
        avg_lat = c.execute(select(func.avg(t.c.latency_ms)).where(t.c.created_at >= cutoff)).scalar()
    return {
        "total": int(total),
        "verdicts": {k: int(v) for k, v in verdicts.items() if k},
        "interventions": {k: int(v) for k, v in interventions.items() if k},
        "cold_start": int(cold),
        "cold_start_rate": (cold / total) if total else 0.0,
        "avg_latency_ms": int(avg_lat) if avg_lat is not None else 0,
    }


def brain_events_daily(days=7):
    """Per-day decision counts for the last `days` (bucketed in Python, DB-agnostic)."""
    cutoff = _since(days=days)
    t = brain_events
    with engine.begin() as c:
        rows = c.execute(select(t.c.created_at).where(t.c.created_at >= cutoff)).all()
    from collections import Counter
    buckets = Counter()
    for (ts,) in rows:
        if ts is not None:
            buckets[ts.date().isoformat()] += 1
    return sorted(buckets.items())
