"""
Pytest bootstrap for M0.

Runs every test against an isolated temporary SQLite database and with stub
secrets, established BEFORE `db` (or `app`) is imported anywhere. Also puts the
repo root on sys.path so top-level modules (`db`, `athlete_store`, `app`) import.
"""
import os
import sys
import tempfile

# Repo root on the path so `import db` / `import athlete_store` / `import app` resolve.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Isolated temp DB + stub secrets, set before any db/app import (module-level in db.py
# reads DATABASE_URL at import; app.py refuses to import without APEX_SECRET / an
# OpenAI key). Force non-empty values.
_TMPDB = os.path.join(tempfile.mkdtemp(prefix="apex_test_"), "test.db").replace("\\", "/")
os.environ["DATABASE_URL"] = "sqlite:///" + _TMPDB
os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "sk-test-stub"
os.environ["APEX_SECRET"] = os.environ.get("APEX_SECRET") or "test-signing-secret"

import pytest                       # noqa: E402
import db as store                  # noqa: E402
from sqlalchemy import delete       # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_schema():
    """Build the schema once for the whole test session."""
    store.init_db()
    yield


# Tables cleared between tests for determinism (FK-safe order: children → parents).
_CLEAN_ORDER = (
    "human_state_reviews", "human_state_events", "human_state",
    "recommendation_history", "user_preferences",
    "brain_events", "brain_decisions", "athlete_models", "conversations", "workout_history",
    "nutrition_history", "coach_memory", "subscriptions", "auth_identities",
    "login_tokens", "sessions", "payments", "free_usage", "users",
)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Wipe app-owned rows before each test (never touches schema_version)."""
    with store.engine.begin() as c:
        for name in _CLEAN_ORDER:
            t = store.metadata.tables.get(name)
            if t is not None:
                try:
                    c.execute(delete(t))
                except Exception:
                    pass
    yield
