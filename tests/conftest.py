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
    "training_trajectory_states", "training_progression_events", "exercise_progression_states",
    "training_completion_prescriptions",
    "training_completions", "delivered_training_prescriptions",
    "delivered_training_sessions", "delivered_training_plans",
    "brain_events", "brain_decisions", "athlete_models", "conversations", "workout_history",
    "nutrition_history", "coach_memory", "account_training_constraints", "subscriptions", "auth_identities",
    "login_tokens", "sessions", "payment_token_revocations", "stripe_event_receipts", "stripe_payment_intents", "payments", "free_activation_candidates",
    "free_activation_device_links", "free_activations", "free_usage", "users",
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


@pytest.fixture(autouse=True)
def _mock_nutrition_scope_transport(monkeypatch):
    """Keep legacy integration fixtures offline at the new external boundary.

    Existing suites supply generation responses, not scope responses. Their
    established request labels are reused ONLY in this provider stub. Semantic
    intent regressions supply independent annotations and exercise the actual
    parser and /chat delivery. Production has no lexical fallback.
    """
    import json
    from types import SimpleNamespace
    import decision_engine
    import nutrition_conversation
    import nutrition_intent

    def respond(_client, messages):
        data = json.loads(messages[-1]["content"])
        if "candidate" in data:
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content=json.dumps({
                    "daily_prescription": nutrition_conversation.unstructured_daily_plan(data["candidate"])})))])
        message, history = data["message"], data["conversation"]
        if nutrition_conversation.is_plan_request(message, history):
            scope = nutrition_intent.Scope.DAILY_PLAN
        elif nutrition_conversation.parse_plan_revision(message) is not None:
            scope = nutrition_intent.Scope.REVISION
        elif decision_engine.classify_intent(message) == "nutrition":
            scope = nutrition_intent.Scope.QUESTION
        else:
            scope = nutrition_intent.Scope.OTHER
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=json.dumps({"scope": scope.value, "requested_goal": None})))])

    monkeypatch.setattr(nutrition_intent, "_request", respond)
