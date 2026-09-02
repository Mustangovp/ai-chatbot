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
import os, uuid, hashlib, secrets, datetime as _dt, time as _time, math
from contextlib import contextmanager
from sqlalchemy import (
    create_engine, MetaData, Table, Column, String, Integer, Boolean, Float,
    DateTime, JSON, ForeignKey, UniqueConstraint, Index, func, select, update, insert, delete, inspect, text
)
from sqlalchemy.types import Uuid
from sqlalchemy.exc import IntegrityError, OperationalError

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

# Canonical records for new structured nutrition generation. Legacy
# nutrition_history.content remains a display archive and is never upgraded.
nutrition_plans = Table("nutrition_plans", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("plan_id", String(64), nullable=False, unique=True),
    Column("version", String(32), nullable=False),
    Column("plan", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_nutrition_plans_user_created", "user_id", "created_at"),
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

# Request workers must share safety-critical conversation state. Browser state
# remains a cache; this record carries only bounded workout safety markers.
conversation_runtime_state = Table("conversation_runtime_state", metadata,
    _uuid_col(),
    Column("subject", String(96), nullable=False),
    Column("conversation_id", String(128), nullable=False),
    Column("medical_hold", JSON),
    Column("health_restrictions", JSON),
    Column("workout_blueprint", JSON),
    Column("workout_decision", String(40)),
    Column("nutrition_followup", String(40)),
    Column("workout_delivered", Boolean, nullable=False, default=False),
    Column("workout_stale", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("subject", "conversation_id", name="uq_conversation_runtime_scope"),
)

# Account-owned, closed-vocabulary training exclusions.  The stored pattern is
# always a deterministic training taxonomy key; free-form chat text never enters
# this table.
account_training_constraints = Table("account_training_constraints", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("pattern", String(48), nullable=False),
    Column("source", String(32), nullable=False, default="explicit_user"),
    Column("state", String(16), nullable=False, default="active"),
    Column("retired_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("user_id", "pattern", name="uq_account_training_constraint_pattern"),
    Index("ix_account_training_constraints_user", "user_id"),
)

# Immutable, account-owned training lineage.  These records are deliberately
# separate from conversation_runtime_state: the latter remains a bounded
# conversation/safety cache, while this ledger proves cross-session identity.
delivered_training_plans = Table("delivered_training_plans", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("plan_id", String(512), nullable=False),
    Column("plan_version", String(48), nullable=False),
    Column("lineage", JSON, nullable=False),
    _ts(name="delivered_at"),
    UniqueConstraint("user_id", "plan_id", "plan_version", name="uq_delivered_training_plan_identity"),
    Index("ix_delivered_training_plans_user_delivered", "user_id", "delivered_at"),
)

delivered_training_sessions = Table("delivered_training_sessions", metadata,
    _uuid_col(),
    Column("delivered_plan_id", Uuid(as_uuid=True), ForeignKey("delivered_training_plans.id", ondelete="CASCADE"), nullable=False),
    Column("session_id", String(512), nullable=False),
    Column("session_index", Integer, nullable=False),
    Column("selection_blueprint_id", String(512), nullable=False),
    Column("estimated_duration_minutes", Integer, nullable=False),
    UniqueConstraint("delivered_plan_id", "session_id", name="uq_delivered_training_session_identity"),
)

delivered_training_prescriptions = Table("delivered_training_prescriptions", metadata,
    _uuid_col(),
    Column("delivered_session_id", Uuid(as_uuid=True), ForeignKey("delivered_training_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("prescription_id", String(96), nullable=False),
    Column("exercise_id", String(128), nullable=False),
    Column("exercise_version", String(48), nullable=False),
    Column("prescription", JSON, nullable=False),
    UniqueConstraint("delivered_session_id", "prescription_id", name="uq_delivered_training_prescription_identity"),
)

training_completions = Table("training_completions", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("delivered_plan_id", Uuid(as_uuid=True), ForeignKey("delivered_training_plans.id", ondelete="CASCADE"), nullable=False),
    Column("delivered_session_id", Uuid(as_uuid=True), ForeignKey("delivered_training_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("workout_id", String(256), nullable=False),
    Column("completion_percent", Integer, nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    _ts(name="recorded_at"),
    UniqueConstraint("user_id", "workout_id", name="uq_training_completion_workout"),
    UniqueConstraint("delivered_plan_id", "delivered_session_id", name="uq_training_completion_session"),
    Index("ix_training_completions_user_completed", "user_id", "completed_at"),
)

training_completion_prescriptions = Table("training_completion_prescriptions", metadata,
    _uuid_col(),
    Column("completion_id", Uuid(as_uuid=True), ForeignKey("training_completions.id", ondelete="CASCADE"), nullable=False),
    Column("prescription_index", Integer, nullable=False),
    Column("prescription_id", String(96), nullable=False),
    Column("exercise_id", String(128), nullable=False),
    Column("exercise_version", String(48), nullable=False),
    Column("completed_sets", Integer, nullable=False),
    Column("completed_repetitions", Integer, nullable=False),
    Column("completed_load", Float),
    Column("completed_rpe", Float),
    Column("completed_rir", Integer),
    Column("completed_effort", String(24)),
    UniqueConstraint("completion_id", "prescription_id", name="uq_training_completion_prescription"),
)

_ACCOUNT_TRAINING_CONSTRAINT_PATTERNS = frozenset({
    "vertical_push", "horizontal_push", "vertical_pull", "squat", "lunge", "hinge",
})

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

# M6 Recommendation Architecture — persistent per-subject preferences + diversity
# history. Additive; never read by the Brain (kept out of the athlete model).
user_preferences = Table("user_preferences", metadata,
    _uuid_col(),
    Column("subject", String(64), nullable=False, unique=True),   # 'user:<id>' | 'device:<id>'
    Column("data", JSON, nullable=False, default=dict),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)
recommendation_history = Table("recommendation_history", metadata,
    _uuid_col(),
    Column("subject", String(64), nullable=False),
    Column("kind", String(24), nullable=False),        # nutrition | workout | recovery
    Column("anchor", String(48), nullable=False),      # rotated anchor for diversity
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_rec_hist_subject_kind", "subject", "kind", "created_at"),
)

# BUILD-001 Human Conversation Ingestion — current fused state per (subject, key).
# Additive; NEVER read or written by the Brain (independent of athlete_models).
human_state = Table("human_state", metadata,
    _uuid_col(),
    Column("subject", String(64), nullable=False),      # 'user:<id>' | 'device:<id>'
    Column("key", String(32), nullable=False),          # fatigue|pain|sleep|motivation|...
    Column("value", JSON),                              # scalar or small token
    Column("confidence", Float),                        # 0..1 at time observed
    Column("source", String(24)),                      # message|checkin|coach_obs
    Column("observed_at", DateTime(timezone=True)),
    Column("ttl_seconds", Integer),
    # Compatibility column only. HSE stores bounded values, never source-language notes.
    Column("note", String(120)),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("subject", "key", name="uq_human_state_subject_key"),
    Index("ix_human_state_subject", "subject"),
)

# BUILD-002 Human State Observatory — extraction audit log + reviewer marks.
# Internal engineering validation only; admin-gated. Additive.
human_state_events = Table("human_state_events", metadata,
    _uuid_col(),
    Column("subject", String(64), nullable=False),
    # Compatibility column only. Raw conversation content is never persisted here.
    Column("message", String(4000)),
    Column("transitions", JSON),                        # [{key, extracted_value, confidence, ttl, prev_*, action, final_value}]
    Column("latency_ms", Float),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_hse_events_created", "created_at"),
    Index("ix_hse_events_subject", "subject"),
)
human_state_reviews = Table("human_state_reviews", metadata,
    _uuid_col(),
    Column("event_id", Uuid(as_uuid=True)),             # references human_state_events.id
    Column("key", String(48)),                          # entity reviewed, or a missed-entity key
    Column("verdict", String(24)),                      # correct|incorrect|partial|missed|false_extraction
    Column("note", String(240)),
    Column("reviewer", String(48)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_hse_reviews_event", "event_id"),
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
    (5, lambda c: None),  # M6: user_preferences table (created by create_all)
    (6, lambda c: None),  # M6: recommendation_history table (created by create_all)
    (7, lambda c: None),  # BUILD-001: human_state table (created by create_all)
    (8, lambda c: None),  # BUILD-002: human_state_events table (created by create_all)
    (9, lambda c: None),  # BUILD-002: human_state_reviews table (created by create_all)
    (10, lambda c: None), # NutritionPlan v1 table (created by create_all)
    (11, lambda c: None), # shared safety-critical conversation runtime state
    (12, lambda c: _add_runtime_workout_blueprint(c)),
    (13, lambda c: _remove_legacy_hse_free_text(c)),
    (14, lambda c: None), # account-owned canonical training constraints
    (15, lambda c: _add_account_training_constraint_lifecycle(c)),
    (16, lambda c: _add_runtime_workout_decision(c)),
    (17, lambda c: _add_runtime_nutrition_followup(c)),
    (18, lambda c: None), # account-owned immutable training lineage tables
]


def _add_runtime_workout_blueprint(connection):
    """Persist the immutable plan so follow-ups survive a worker boundary."""
    columns = {column["name"] for column in inspect(connection).get_columns(
        "conversation_runtime_state")}
    if "workout_blueprint" not in columns:
        connection.execute(text(
            "ALTER TABLE conversation_runtime_state ADD COLUMN workout_blueprint JSON"))


def _remove_legacy_hse_free_text(connection):
    """Erase legacy raw HSE text. New writes never populate these compatibility fields."""
    connection.execute(text("UPDATE human_state_events SET message = NULL"))
    connection.execute(text("UPDATE human_state SET note = NULL"))
    connection.execute(text("UPDATE human_state_reviews SET note = NULL"))


def _add_account_training_constraint_lifecycle(connection):
    """Keep account exclusions auditable after a user explicitly retires one."""
    columns = {column["name"] for column in inspect(connection).get_columns(
        "account_training_constraints")}
    if "state" not in columns:
        connection.execute(text(
            "ALTER TABLE account_training_constraints ADD COLUMN state VARCHAR(16) DEFAULT 'active'"))
        connection.execute(text(
            "UPDATE account_training_constraints SET state = 'active' WHERE state IS NULL"))
    if "retired_at" not in columns:
        retired_type = "TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME"
        connection.execute(text(
            f"ALTER TABLE account_training_constraints ADD COLUMN retired_at {retired_type}"))


def _add_runtime_workout_decision(connection):
    """Persist the bounded authority outcome for referential workout turns."""
    inspector = inspect(connection)
    if not inspector.has_table("conversation_runtime_state"):
        return
    columns = {column["name"] for column in inspector.get_columns(
        "conversation_runtime_state")}
    if "workout_decision" not in columns:
        connection.execute(text(
            "ALTER TABLE conversation_runtime_state ADD COLUMN workout_decision VARCHAR(40)"))


def _add_runtime_nutrition_followup(connection):
    """Persist only the closed recipe meal-clarification continuation marker."""
    inspector = inspect(connection)
    if not inspector.has_table("conversation_runtime_state"):
        return
    columns = {column["name"] for column in inspector.get_columns(
        "conversation_runtime_state")}
    if "nutrition_followup" not in columns:
        connection.execute(text(
            "ALTER TABLE conversation_runtime_state ADD COLUMN nutrition_followup VARCHAR(40)"))

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

def get_checkout_session_user(stripe_session_id):
    """Return the account that has already redeemed a Checkout session, if any."""
    session_id = str(stripe_session_id or "")[:120]
    if not session_id:
        return None
    with engine.begin() as c:
        row = c.execute(select(payments.c.user_id).where(
            payments.c.stripe_session_id == session_id)).first()
        if not row:
            row = c.execute(select(subscriptions.c.user_id).where(
                subscriptions.c.stripe_session_id == session_id)).first()
    return str(row[0]) if row else None

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


def list_account_training_constraint_records(user_id, *, active_only=True):
    """Return bounded account-owned constraint records without free-form chat text."""
    with engine.begin() as c:
        statement = select(
            account_training_constraints.c.id,
            account_training_constraints.c.pattern,
            account_training_constraints.c.source,
            account_training_constraints.c.state,
        ).where(account_training_constraints.c.user_id == _as_uuid(user_id))
        if active_only:
            statement = statement.where(account_training_constraints.c.state == "active")
        rows = c.execute(statement.order_by(account_training_constraints.c.created_at.asc())).mappings().all()
    return tuple({
        "id": str(row["id"]),
        "pattern": str(row["pattern"]),
        "source": str(row["source"]),
        "state": str(row["state"]),
        "removable": row["source"] == "explicit_user" and row["state"] == "active",
    } for row in rows if row["pattern"] in _ACCOUNT_TRAINING_CONSTRAINT_PATTERNS)


def list_account_training_constraints(user_id):
    """Return only active canonical account-owned movement exclusions."""
    return tuple(record["pattern"] for record in list_account_training_constraint_records(user_id))


def add_account_training_constraints(user_id, patterns, source="explicit_user"):
    """Insert closed-vocabulary patterns idempotently; no chat text is stored."""
    normalized = tuple(dict.fromkeys(
        str(pattern).strip() for pattern in (patterns or ())
        if isinstance(pattern, str) and str(pattern).strip() in _ACCOUNT_TRAINING_CONSTRAINT_PATTERNS
    ))
    if not normalized:
        return ()
    user_uuid = _as_uuid(user_id)
    for pattern in normalized:
        try:
            with engine.begin() as c:
                c.execute(insert(account_training_constraints).values(
                    id=uuid.uuid4(), user_id=user_uuid, pattern=pattern, source=source,
                    state="active", retired_at=None))
        except IntegrityError:
            # A repeated declaration is benign. A prior user-owned retirement is
            # explicitly reactivated by a fresh, explicit declaration.
            with engine.begin() as c:
                existing = c.execute(select(
                    account_training_constraints.c.source,
                    account_training_constraints.c.state,
                ).where(
                    account_training_constraints.c.user_id == user_uuid,
                    account_training_constraints.c.pattern == pattern,
                )).mappings().first()
                if (existing and existing["source"] == "explicit_user"
                        and existing["state"] == "retired" and source == "explicit_user"):
                    c.execute(update(account_training_constraints).where(
                        account_training_constraints.c.user_id == user_uuid,
                        account_training_constraints.c.pattern == pattern,
                    ).values(state="active", retired_at=None))
    return list_account_training_constraints(user_id)


def retire_account_training_constraint(user_id, constraint_id):
    """Retire one active user-owned constraint; unknown/cross-account rows stay hidden."""
    try:
        constraint_uuid = _as_uuid(constraint_id)
    except (TypeError, ValueError, AttributeError):
        return None
    with engine.begin() as c:
        row = c.execute(select(
            account_training_constraints.c.id,
            account_training_constraints.c.pattern,
            account_training_constraints.c.source,
            account_training_constraints.c.state,
        ).where(
            account_training_constraints.c.id == constraint_uuid,
            account_training_constraints.c.user_id == _as_uuid(user_id),
        )).mappings().first()
        if (not row or row["pattern"] not in _ACCOUNT_TRAINING_CONSTRAINT_PATTERNS
                or row["source"] != "explicit_user"):
            return None
        retired = row["state"] == "active"
        if retired:
            c.execute(update(account_training_constraints).where(
                account_training_constraints.c.id == constraint_uuid,
                account_training_constraints.c.user_id == _as_uuid(user_id),
            ).values(state="retired", retired_at=_now()))
    return {"id": str(constraint_uuid), "pattern": str(row["pattern"]), "retired": retired}

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

def save_nutrition_plan(user_id, plan: dict):
    """Persist a new canonical NutritionPlan without touching legacy text rows."""
    if not isinstance(plan, dict) or not plan.get("id") or not plan.get("version"):
        raise ValueError("structured nutrition plan is required")
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(insert(nutrition_plans).values(
            id=nid, user_id=_as_uuid(user_id), plan_id=str(plan["id"]),
            version=str(plan["version"]), plan=plan))
        c.execute(insert(coach_memory).values(id=uuid.uuid4(), user_id=_as_uuid(user_id),
            kind="nutrition", source="app", payload={"plan_id": plan["id"], "version": plan["version"]}))
    return str(nid)

def list_nutrition(user_id, limit=30):
    with engine.begin() as c:
        rows = c.execute(select(nutrition_history).where(nutrition_history.c.user_id == _as_uuid(user_id))
                         .order_by(nutrition_history.c.created_at.desc()).limit(limit)).mappings().all()
    return [_serial(r) for r in rows]

def list_nutrition_plans(user_id, limit=30):
    with engine.begin() as c:
        rows = c.execute(select(nutrition_plans).where(nutrition_plans.c.user_id == _as_uuid(user_id))
                         .order_by(nutrition_plans.c.created_at.desc()).limit(limit)).mappings().all()
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

def get_conversation_runtime_state(subject, conversation_id):
    """Return bounded cross-worker workout safety state for one conversation."""
    with engine.begin() as c:
        row = c.execute(select(conversation_runtime_state).where(
            conversation_runtime_state.c.subject == str(subject),
            conversation_runtime_state.c.conversation_id == str(conversation_id),
        )).mappings().first()
    return dict(row) if row else {}

def update_conversation_runtime_state(subject, conversation_id, **values):
    """Update only supplied safety fields, preserving concurrent field ownership."""
    allowed = {"medical_hold", "health_restrictions", "workout_blueprint", "workout_decision",
               "nutrition_followup", "workout_delivered", "workout_stale"}
    changes = {key: value for key, value in values.items() if key in allowed}
    if not changes:
        return
    subject = str(subject)
    conversation_id = str(conversation_id)
    with engine.begin() as c:
        result = c.execute(update(conversation_runtime_state).where(
            conversation_runtime_state.c.subject == subject,
            conversation_runtime_state.c.conversation_id == conversation_id,
        ).values(**changes))
        if result.rowcount:
            return
    try:
        with engine.begin() as c:
            c.execute(insert(conversation_runtime_state).values(
                id=uuid.uuid4(), subject=subject, conversation_id=conversation_id, **changes))
    except IntegrityError:
        with engine.begin() as c:
            c.execute(update(conversation_runtime_state).where(
                conversation_runtime_state.c.subject == subject,
                conversation_runtime_state.c.conversation_id == conversation_id,
            ).values(**changes))

def list_workouts(user_id, limit=60):
    with engine.begin() as c:
        rows = c.execute(select(workout_history).where(workout_history.c.user_id == _as_uuid(user_id))
                         .order_by(workout_history.c.occurred_at.desc()).limit(limit)).mappings().all()
    return [_serial(r) for r in rows]


# ── Individual Model v1 · immutable training lineage ────────────────────────
def persist_delivered_training_plan(user_id, lineage):
    """Persist one validated immutable plan lineage, or return its exact prior row.

    The caller supplies only a projection of ``TrainingPlanBlueprintV2``.  This
    store never accepts renderer text, profile snapshots, or request history.
    """
    normalized = _validated_training_lineage(lineage)
    user_uuid = _as_uuid(user_id)
    with engine.begin() as c:
        existing = c.execute(select(delivered_training_plans).where(
            delivered_training_plans.c.user_id == user_uuid,
            delivered_training_plans.c.plan_id == normalized["plan_id"],
            delivered_training_plans.c.plan_version == normalized["plan_version"],
        )).mappings().first()
        if existing:
            if existing["lineage"] != normalized:
                raise ValueError("delivered training plan identity is immutable")
            return str(existing["id"])
        plan_uuid = uuid.uuid4()
        c.execute(insert(delivered_training_plans).values(
            id=plan_uuid, user_id=user_uuid, plan_id=normalized["plan_id"],
            plan_version=normalized["plan_version"], lineage=normalized,
        ))
        for session in normalized["sessions"]:
            session_uuid = uuid.uuid4()
            c.execute(insert(delivered_training_sessions).values(
                id=session_uuid, delivered_plan_id=plan_uuid,
                session_id=session["session_id"], session_index=session["session_index"],
                selection_blueprint_id=session["selection_blueprint_id"],
                estimated_duration_minutes=session["estimated_duration_minutes"],
            ))
            for prescription in session["prescriptions"]:
                c.execute(insert(delivered_training_prescriptions).values(
                    id=uuid.uuid4(), delivered_session_id=session_uuid,
                    prescription_id=prescription["prescription_id"],
                    exercise_id=prescription["exercise_id"],
                    exercise_version=prescription["exercise_version"],
                    prescription=prescription,
                ))
    return str(plan_uuid)


def list_training_completion_records(user_id, limit=60):
    """Return normalized completions in the legacy reader shape for safe replay.

    This is an account-owned source; legacy ``workout_history`` remains a
    compatibility fallback for accounts that predate immutable lineage.
    """
    user_uuid = _as_uuid(user_id)
    with engine.begin() as c:
        rows = c.execute(select(training_completions).where(
            training_completions.c.user_id == user_uuid,
        ).order_by(training_completions.c.completed_at.desc()).limit(limit)).mappings().all()
        records = []
        for row in rows:
            facts = c.execute(select(training_completion_prescriptions).where(
                training_completion_prescriptions.c.completion_id == row["id"],
            ).order_by(training_completion_prescriptions.c.prescription_index.asc())).mappings().all()
            plan = c.execute(select(delivered_training_plans).where(
                delivered_training_plans.c.id == row["delivered_plan_id"],
                delivered_training_plans.c.user_id == user_uuid,
            )).mappings().first()
            session = c.execute(select(delivered_training_sessions).where(
                delivered_training_sessions.c.id == row["delivered_session_id"],
                delivered_training_sessions.c.delivered_plan_id == row["delivered_plan_id"],
            )).mappings().first()
            if not plan or not session or not facts:
                continue
            payload = {
                "workout_id": row["workout_id"], "plan_id": plan["plan_id"],
                "plan_version": plan["plan_version"], "session_id": session["session_id"],
                "completion_timestamp": _aware(row["completed_at"]).isoformat(),
                "exercises": [{
                    "prescription_id": item["prescription_id"],
                    "exercise_id": item["exercise_id"], "exercise_version": item["exercise_version"],
                    "completed_sets": item["completed_sets"],
                    "completed_repetitions": item["completed_repetitions"],
                    "completed_load": item["completed_load"], "completed_rpe": item["completed_rpe"],
                    "completed_rir": item["completed_rir"], "completed_effort": item["completed_effort"],
                } for item in facts],
            }
            records.append({
                "id": str(row["id"]), "occurred_at": _aware(row["completed_at"]).isoformat(),
                "completion": row["completion_percent"],
                "exercises": {"workout_completion": payload},
            })
    return records


def record_training_completion(user_id, session, completion):
    """Atomically store normalized completion facts and legacy history output.

    Every identity is looked up through the authenticated account before a fact
    is written.  A rejected lineage writes neither table.
    """
    if not isinstance(session, dict) or not isinstance(completion, dict):
        raise ValueError("training completion requires structured session evidence")
    user_uuid = _as_uuid(user_id)
    plan_id = _lineage_text(completion.get("plan_id"), "plan_id", maximum=512)
    plan_version = _lineage_text(completion.get("plan_version"), "plan_version", maximum=48)
    session_id = _lineage_text(completion.get("session_id"), "session_id", maximum=512)
    workout_id = _lineage_text(completion.get("workout_id"), "workout_id", maximum=256)
    completed_at = _lineage_timestamp(completion.get("completion_timestamp"))
    percentage = _lineage_percentage(session.get("completion"))
    exercises = completion.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        raise ValueError("training completion exercises are required")
    with engine.begin() as c:
        plan = c.execute(select(delivered_training_plans).where(
            delivered_training_plans.c.user_id == user_uuid,
            delivered_training_plans.c.plan_id == plan_id,
            delivered_training_plans.c.plan_version == plan_version,
        )).mappings().first()
        if not plan:
            raise ValueError("unknown delivered training plan")
        delivered_session = c.execute(select(delivered_training_sessions).where(
            delivered_training_sessions.c.delivered_plan_id == plan["id"],
            delivered_training_sessions.c.session_id == session_id,
        )).mappings().first()
        if not delivered_session:
            raise ValueError("unknown delivered training session")
        expected_rows = c.execute(select(delivered_training_prescriptions).where(
            delivered_training_prescriptions.c.delivered_session_id == delivered_session["id"],
        )).mappings().all()
        expected = {row["prescription_id"]: row for row in expected_rows}
        facts = []
        seen = set()
        for raw in exercises:
            fact = _validated_completion_fact(raw)
            prescription = expected.get(fact["prescription_id"])
            if prescription is None or fact["prescription_id"] in seen:
                raise ValueError("unknown or duplicate delivered prescription")
            if (fact["exercise_id"], fact["exercise_version"]) != (
                    prescription["exercise_id"], prescription["exercise_version"]):
                raise ValueError("completion exercise does not match delivered prescription")
            prescribed_sets = prescription["prescription"].get("sets")
            if not isinstance(prescribed_sets, int) or fact["completed_sets"] > prescribed_sets:
                raise ValueError("completed sets exceed the delivered prescription")
            if (fact["completed_sets"] == 0) != (fact["completed_repetitions"] == 0):
                raise ValueError("completed work must include both sets and repetitions")
            seen.add(fact["prescription_id"])
            facts.append(fact)
        if set(expected) != seen:
            raise ValueError("completion must cover the exact delivered session")
        duplicate = c.execute(select(training_completions.c.id).where(
            (training_completions.c.user_id == user_uuid) & (
                (training_completions.c.workout_id == workout_id) |
                ((training_completions.c.delivered_plan_id == plan["id"]) &
                 (training_completions.c.delivered_session_id == delivered_session["id"]))),
        )).first()
        if duplicate:
            raise ValueError("duplicate training completion")
        completion_uuid = uuid.uuid4()
        c.execute(insert(training_completions).values(
            id=completion_uuid, user_id=user_uuid, delivered_plan_id=plan["id"],
            delivered_session_id=delivered_session["id"], workout_id=workout_id,
            completion_percent=percentage, completed_at=completed_at,
        ))
        for fact_index, fact in enumerate(facts, 1):
            c.execute(insert(training_completion_prescriptions).values(
                id=uuid.uuid4(), completion_id=completion_uuid,
                prescription_index=fact_index, **fact,
            ))
        legacy_id = uuid.uuid4()
        c.execute(insert(workout_history).values(
            id=legacy_id, user_id=user_uuid, type=session.get("type"),
            exercises=session.get("exercises"), difficulty=session.get("diff"),
            completion=percentage, source="app"))
        c.execute(insert(coach_memory).values(
            id=uuid.uuid4(), user_id=user_uuid, kind="workout", source="app", payload=session))
    return str(legacy_id)


def _validated_training_lineage(value):
    if not isinstance(value, dict):
        raise ValueError("delivered training lineage must be an object")
    plan_id = _lineage_text(value.get("plan_id"), "plan_id", maximum=512)
    plan_version = _lineage_text(value.get("plan_version"), "plan_version", maximum=48)
    sessions = value.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("delivered training lineage requires sessions")
    normalized_sessions = []
    seen_sessions = set()
    for expected_index, raw in enumerate(sessions, 1):
        if not isinstance(raw, dict):
            raise ValueError("delivered training session is invalid")
        session_id = _lineage_text(raw.get("session_id"), "session_id", maximum=512)
        if session_id in seen_sessions or raw.get("session_index") != expected_index:
            raise ValueError("delivered training sessions must be unique and ordered")
        seen_sessions.add(session_id)
        if not isinstance(raw.get("estimated_duration_minutes"), int) or raw["estimated_duration_minutes"] < 1:
            raise ValueError("delivered training session duration is invalid")
        prescriptions = raw.get("prescriptions")
        if not isinstance(prescriptions, list) or not prescriptions:
            raise ValueError("delivered training session prescriptions are required")
        normalized_prescriptions = []
        seen_prescriptions = set()
        for prescription in prescriptions:
            if not isinstance(prescription, dict):
                raise ValueError("delivered prescription is invalid")
            pid = _lineage_text(prescription.get("prescription_id"), "prescription_id")
            if pid in seen_prescriptions:
                raise ValueError("delivered prescriptions must be unique")
            seen_prescriptions.add(pid)
            required = ("exercise_id", "exercise_version", "sets", "rep_min", "rep_max",
                        "target_rpe", "target_rir", "rest_seconds", "tempo",
                        "selection_policy_version", "prescription_policy_version",
                        "construction_policy_version")
            if any(field not in prescription for field in required):
                raise ValueError("delivered prescription provenance is incomplete")
            normalized_prescriptions.append(dict(prescription))
        normalized_sessions.append({
            "session_id": session_id, "session_index": raw["session_index"],
            "selection_blueprint_id": _lineage_text(
                raw.get("selection_blueprint_id"), "selection_blueprint_id", maximum=512),
            "estimated_duration_minutes": raw["estimated_duration_minutes"],
            "prescriptions": normalized_prescriptions,
        })
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("delivered training lineage metadata is required")
    return {"plan_id": plan_id, "plan_version": plan_version,
            "metadata": dict(metadata), "sessions": normalized_sessions}


def _lineage_text(value, field, maximum=128):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{field} is invalid")
    return value.strip()


def _lineage_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("completion timestamp is invalid")
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("completion timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("completion timestamp must be timezone-aware")
    return parsed.astimezone(_dt.timezone.utc)


def _lineage_percentage(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError("completion percentage is invalid")
    return value


def _validated_completion_fact(value):
    if not isinstance(value, dict):
        raise ValueError("completion prescription is invalid")
    required = ("prescription_id", "exercise_id", "exercise_version", "completed_sets", "completed_repetitions")
    if any(field not in value for field in required):
        raise ValueError("completion prescription is incomplete")
    if (isinstance(value["completed_sets"], bool) or isinstance(value["completed_repetitions"], bool)
            or not isinstance(value["completed_sets"], int) or not isinstance(value["completed_repetitions"], int)
            or value["completed_sets"] < 0 or value["completed_repetitions"] < 0):
        raise ValueError("completion performance values are invalid")
    def optional_number(field, minimum=None, maximum=None):
        raw = value.get(field)
        if raw is None:
            return None
        if isinstance(raw, bool):
            raise ValueError(f"{field} is invalid")
        try:
            normalized = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field} is invalid") from error
        if not math.isfinite(normalized) or (minimum is not None and normalized < minimum) or (
                maximum is not None and normalized > maximum):
            raise ValueError(f"{field} is invalid")
        return normalized
    completed_rir = value.get("completed_rir")
    if completed_rir is not None and (isinstance(completed_rir, bool) or not isinstance(completed_rir, int)
                                      or not 0 <= completed_rir <= 10):
        raise ValueError("completed_rir is invalid")
    effort = value.get("completed_effort")
    if effort not in (None, "easy", "productive", "hard", "incomplete"):
        raise ValueError("completed_effort is invalid")
    return {
        "prescription_id": _lineage_text(value["prescription_id"], "prescription_id"),
        "exercise_id": _lineage_text(value["exercise_id"], "exercise_id"),
        "exercise_version": _lineage_text(value["exercise_version"], "exercise_version"),
        "completed_sets": value["completed_sets"],
        "completed_repetitions": value["completed_repetitions"],
        "completed_load": optional_number("completed_load", minimum=0),
        "completed_rpe": optional_number("completed_rpe", minimum=1, maximum=10),
        "completed_rir": completed_rir,
        "completed_effort": effort,
    }

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


# ── M6 Recommendation Architecture — preferences + diversity history ─────────
def get_preferences(subject):
    with engine.begin() as c:
        row = c.execute(select(user_preferences.c.data)
                        .where(user_preferences.c.subject == subject)).first()
    return dict(row[0]) if row and row[0] else None


def save_preferences(subject, data):
    with engine.begin() as c:
        exists = c.execute(select(user_preferences.c.id)
                           .where(user_preferences.c.subject == subject)).first()
        if exists:
            c.execute(update(user_preferences)
                      .where(user_preferences.c.subject == subject).values(data=data))
        else:
            c.execute(insert(user_preferences).values(id=uuid.uuid4(), subject=subject, data=data))


def log_recommendation(subject, kind, anchor):
    with engine.begin() as c:
        c.execute(insert(recommendation_history).values(
            id=uuid.uuid4(), subject=subject, kind=kind, anchor=anchor))


def recent_recommendations(subject, kind, n=4):
    t = recommendation_history
    with engine.begin() as c:
        rows = c.execute(select(t.c.anchor).where(t.c.subject == subject).where(t.c.kind == kind)
                         .order_by(t.c.created_at.desc()).limit(n)).all()
    return [r[0] for r in rows]


# ── BUILD-001 Human Conversation Ingestion — human_state store (Brain-independent) ──
def hs_get(subject, key):
    t = human_state
    with engine.begin() as c:
        row = c.execute(select(t).where(t.c.subject == subject).where(t.c.key == key)).mappings().first()
    return dict(row) if row else None


def hs_get_all(subject):
    t = human_state
    with engine.begin() as c:
        rows = c.execute(select(t).where(t.c.subject == subject)).mappings().all()
    return [dict(r) for r in rows]


def _hs_insert(connection, values):
    """Small seam for deterministic insert-race regression testing."""
    connection.execute(insert(human_state).values(**values))


@contextmanager
def _hs_write_transaction():
    """Lock before HSE read/resolve/write on SQLite; lock the row on Postgres.

    SQLite has no row-level ``FOR UPDATE``.  A deferred transaction can let two
    writers read the same live row and make stale replace decisions before either
    acquires its write lock.  ``BEGIN IMMEDIATE`` serializes only this short HSE
    write critical section before its read.  PostgreSQL retains row-level locking.
    """
    if not IS_SQLITE:
        with engine.begin() as connection:
            yield connection
        return
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()


def hs_upsert(subject, key, value, confidence, source, observed_at, ttl_seconds, note=None,
              resolve=None, max_attempts=4):
    """Atomically apply one HSE state write.

    ``resolve(stored)`` is run while the existing row is locked on PostgreSQL and
    again after any insert conflict. It must return either ``action`` or
    ``(action, metadata)`` where action is ``insert``, ``replace``, or ``keep``.
    This prevents a losing first insert from replaying a stale lower-confidence
    decision over the concurrent winner. SQLite uses the same retry/re-read
    semantics without PostgreSQL-only lock syntax.
    """
    t = human_state
    vals = dict(value=value, confidence=float(confidence), source=source,
                observed_at=observed_at, ttl_seconds=int(ttl_seconds), note=None)
    last_error = None
    for attempt in range(max_attempts):
        try:
            with _hs_write_transaction() as c:
                query = select(t).where(t.c.subject == subject).where(t.c.key == key)
                if not IS_SQLITE:
                    query = query.with_for_update()
                row = c.execute(query).mappings().first()
                stored = dict(row) if row else None
                decision = resolve(stored) if resolve else ("replace" if stored else "insert")
                action, metadata = decision if isinstance(decision, tuple) else (decision, None)
                if action == "insert":
                    _hs_insert(c, dict(id=uuid.uuid4(), subject=subject, key=key, **vals))
                elif action == "replace":
                    # The locked/current row is the only row this update may affect.
                    if stored is None:
                        _hs_insert(c, dict(id=uuid.uuid4(), subject=subject, key=key, **vals))
                        action = "insert"
                    else:
                        c.execute(update(t).where(t.c.id == stored["id"]).values(**vals))
                elif action != "keep":
                    raise ValueError("invalid_hse_write_action")
                return {"action": action, "stored": stored, "metadata": metadata}
        except (IntegrityError, OperationalError) as error:
            # A unique conflict (or SQLite's transient writer lock) is not a
            # permission to replay the old decision. Retry causes a fresh read and
            # resolver evaluation against the winner's live state.
            last_error = error
            if attempt + 1 < max_attempts:
                _time.sleep(0.005 * (attempt + 1))
                continue
            raise
    raise last_error  # pragma: no cover - loop always returns or raises


# ── BUILD-002 Human State Observatory — audit log + reviews ──────────────────
_HSE_TRANSITION_FIELDS = (
    "key", "extracted_value", "confidence", "ttl_seconds", "source",
    "prev_value", "prev_confidence", "prev_effective", "action", "final_value",
)


def _bounded_hse_value(value):
    """Keep event history structured and bounded; never retain transcript fragments."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if -1000000 <= value <= 1000000 else None
    if isinstance(value, float):
        return round(value, 4) if -1000000 <= value <= 1000000 else None
    if isinstance(value, str):
        return value[:64] if len(value) <= 64 else None
    if isinstance(value, dict):
        # Existing preference values are the sole multi-value contract. Keep them
        # bounded without admitting arbitrary nested conversation content.
        bounded = {}
        for key in ("avoid", "prefer"):
            item = value.get(key)
            if isinstance(item, str) and item and len(item) <= 32:
                bounded[key] = item
        return bounded or None
    return None


def _bounded_hse_transitions(transitions):
    out = []
    for transition in transitions or []:
        if not isinstance(transition, dict):
            continue
        key = transition.get("key")
        if not isinstance(key, str) or not key or len(key) > 48:
            continue
        item = {"key": key}
        for field in _HSE_TRANSITION_FIELDS:
            if field == "key" or field not in transition:
                continue
            value = transition[field]
            if field in {"extracted_value", "prev_value", "final_value"}:
                value = _bounded_hse_value(value)
            elif field == "confidence" or field == "prev_confidence" or field == "prev_effective":
                try:
                    value = round(float(value), 4) if value is not None else None
                except (TypeError, ValueError):
                    value = None
            elif field == "ttl_seconds":
                try:
                    value = max(1, min(int(value), 180 * 24 * 60 * 60))
                except (TypeError, ValueError):
                    value = None
            elif field in {"source", "action"}:
                value = str(value)[:24] if value is not None else None
            item[field] = value
        out.append(item)
    return out


def hse_log_event(subject, transitions, latency_ms):
    """Persist only bounded derived transitions, never the source message."""
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(insert(human_state_events).values(
            id=eid, subject=subject, message=None,
            transitions=_bounded_hse_transitions(transitions),
            latency_ms=float(latency_ms) if latency_ms is not None else None))
    return str(eid)


def hse_recent_events(limit=50, subject=None):
    """Return a single subject's event history only. Unscoped individual-event
    retrieval is intentionally unavailable; use aggregate observability instead."""
    if not subject:
        return []
    t = human_state_events
    q = select(t).where(t.c.subject == subject).order_by(t.c.created_at.asc()).limit(limit)
    with engine.begin() as c:
        return [_serial(dict(r)) for r in c.execute(q).mappings().all()]


def hse_add_review(event_id, key, verdict, note=None, reviewer=None):
    with engine.begin() as c:
        c.execute(insert(human_state_reviews).values(
            id=uuid.uuid4(), event_id=_as_uuid(event_id) if event_id else None,
            key=key, verdict=verdict, note=None, reviewer=(reviewer or "admin")[:48]))


def hse_reviews_for_events(event_ids, limit=5000):
    """Return reviews only for explicitly scoped event ids."""
    event_ids = [_as_uuid(event_id) for event_id in event_ids or [] if event_id]
    if not event_ids:
        return []
    t = human_state_reviews
    with engine.begin() as c:
        return [_serial(dict(r)) for r in
                c.execute(select(t).where(t.c.event_id.in_(event_ids)).order_by(t.c.created_at.desc()).limit(limit)).mappings().all()]


def _hse_events_for_aggregate(limit=5000):
    """Private helper for aggregate-only observability; never returned directly."""
    t = human_state_events
    with engine.begin() as c:
        return [_serial(dict(r)) for r in c.execute(
            select(t).order_by(t.c.created_at.desc()).limit(limit)).mappings().all()]


def _hse_reviews_for_aggregate(limit=5000):
    """Private helper for aggregate-only observability; never returned directly."""
    t = human_state_reviews
    with engine.begin() as c:
        return [_serial(dict(r)) for r in c.execute(
            select(t).order_by(t.c.created_at.desc()).limit(limit)).mappings().all()]


def hse_event_count():
    with engine.begin() as c:
        return c.execute(select(func.count()).select_from(human_state_events)).scalar() or 0


HSE_EVENT_RETENTION_DAYS = 30


def _aware_hse_time(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


def hse_cleanup_expired(now=None, subject=None):
    """Physically remove expired HSE rows.

    Current state follows its per-key TTL. Derived event history is retained for
    the trajectory engine's 30-day analysis window, then purged with its reviews.
    ``subject`` scopes cleanup for an anonymous device or one account; no subject
    performs the same bounded lifecycle cleanup across HSE records.
    """
    at = _aware_hse_time(now) if now is not None else _dt.datetime.now(_dt.timezone.utc)
    state_q = select(human_state.c.id, human_state.c.observed_at, human_state.c.ttl_seconds)
    event_q = select(human_state_events.c.id, human_state_events.c.created_at)
    if subject:
        state_q = state_q.where(human_state.c.subject == subject)
        event_q = event_q.where(human_state_events.c.subject == subject)
    with engine.begin() as c:
        stale_state_ids = [row.id for row in c.execute(state_q).all()
                           if row.observed_at is None or
                           _aware_hse_time(row.observed_at) + _dt.timedelta(seconds=max(1, row.ttl_seconds or 0)) <= at]
        cutoff = at - _dt.timedelta(days=HSE_EVENT_RETENTION_DAYS)
        stale_event_ids = [row.id for row in c.execute(event_q).all()
                           if row.created_at is not None and _aware_hse_time(row.created_at) <= cutoff]
        if stale_state_ids:
            c.execute(delete(human_state).where(human_state.c.id.in_(stale_state_ids)))
        if stale_event_ids:
            c.execute(delete(human_state_reviews).where(human_state_reviews.c.event_id.in_(stale_event_ids)))
            c.execute(delete(human_state_events).where(human_state_events.c.id.in_(stale_event_ids)))
    return {"states_deleted": len(stale_state_ids), "events_deleted": len(stale_event_ids)}


def hse_purge_subject(subject):
    """Authoritatively erase all HSE-owned state, audit events, and reviews for one subject."""
    with engine.begin() as c:
        event_ids = [row.id for row in c.execute(
            select(human_state_events.c.id).where(human_state_events.c.subject == subject)).all()]
        reviews_deleted = 0
        if event_ids:
            reviews_deleted = c.execute(delete(human_state_reviews).where(
                human_state_reviews.c.event_id.in_(event_ids))).rowcount or 0
            events_deleted = c.execute(delete(human_state_events).where(
                human_state_events.c.id.in_(event_ids))).rowcount or 0
        else:
            events_deleted = 0
        states_deleted = c.execute(delete(human_state).where(human_state.c.subject == subject)).rowcount or 0
    return {"states_deleted": states_deleted, "events_deleted": events_deleted,
            "reviews_deleted": reviews_deleted}


def hse_purge_user(user_id):
    """Account-deletion primitive. No account-deletion runtime currently exists to wire."""
    return hse_purge_subject(f"user:{user_id}")
