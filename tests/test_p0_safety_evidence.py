"""P0 vertical contracts: real serialization, stores, renderers, and Flask routes."""
from copy import deepcopy
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

import app as appmod
import db
import nutrition_plan as nutrition
from nutrition_constraints import canonical_constraints
from nutrition_validation import NutritionTargets
from constraint_store_state import ConstraintLoadState, load_constraints
from training_engine import build_training_plan, load_exercise_library
from training_engine.completion import completion_projection
from training_engine.followups import serialize_conversation_plan
from workout_execution import normalize_execution


PROFILE = {"goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh"}


@pytest.fixture
def account(monkeypatch):
    appmod.app.config["TESTING"] = True
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    monkeypatch.delenv("BRAIN_ENFORCE", raising=False)
    monkeypatch.setattr(appmod, "_update_learning_engine", lambda *args: None)
    uid = db.get_or_create_user("p0@example.com")
    db.save_profile(uid, PROFILE)
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, db.create_session(uid))
    return client, uid


def _food_payload(name):
    return {"meals": [{"meal_type": meal, "foods": [{"display_name": name, "grams": "100",
            "protein_g": "20", "carbs_g": "40", "fat_g": "20", "kcal": "420", "measurement_state": "as_served"}]}
            for meal in ("breakfast", "lunch", "dinner")]}


def _nutrition(name, restrictions=()):
    return nutrition.build_plan(_food_payload(name), NutritionTargets(kcal=Decimal("1260")),
                                restrictions=restrictions, provenance={}, language="en")


def test_peanut_allergy_blocks_before_plan_or_persistence(account):
    _, uid = account
    with pytest.raises(nutrition.NutritionRestrictionError, match="conflict"):
        db.save_nutrition_plan(uid, nutrition.to_record(_nutrition("Peanuts", ("peanut allergy",))))
    assert db.list_nutrition_plans(uid) == []


def test_safe_unrelated_food_survives_plan_db_and_delivery(account):
    _, uid = account
    plan = _nutrition("Rice", ("peanut allergy",))
    db.save_nutrition_plan(uid, nutrition.to_record(plan))
    loaded = nutrition.from_record(db.list_nutrition_plans(uid)[0]["plan"])
    assert loaded.totals == plan.totals
    assert "Rice" in nutrition.render_delivery(loaded, "en")


@pytest.mark.parametrize("food", ("Protein snack", "Mystery rice", "Peanut-free mix"))
def test_ambiguous_food_fails_closed(food):
    with pytest.raises(nutrition.NutritionRestrictionError, match="identity_unresolved"):
        _nutrition(food, ("peanut allergy",))


def test_no_preference_is_invented():
    assert canonical_constraints(()) == ()
    assert _nutrition("Peanuts").restrictions == ()
    # Conversation-like content never becomes an inferred allergen preference.
    constraints = canonical_constraints(("My friend has a peanut allergy",))
    assert all(item.kind.value == "unsupported" for item in constraints)


def test_new_profile_restriction_blocks_delivery_of_old_plan():
    plan = _nutrition("Peanuts")
    reply = nutrition.render_delivery(plan, "en", {"allergies": "peanut allergy"})
    assert reply == nutrition.restriction_blocked_message("en")
    assert "Peanuts" not in reply


def test_catalog_chicken_cannot_bypass_recorded_chicken_exclusion():
    with pytest.raises(nutrition.NutritionRestrictionError, match="conflict"):
        _nutrition("Roasted skinless chicken breast", ("no chicken",))


def test_conflicting_food_id_fails_closed():
    payload = _food_payload("Rice")
    payload["meals"][0]["foods"][0]["catalog_id"] = "peanuts"
    with pytest.raises(nutrition.NutritionRestrictionError, match="ambiguous"):
        nutrition.build_plan(payload, NutritionTargets(kcal=Decimal("1260")),
                             restrictions=("peanut allergy",), provenance={})


def test_peanuts_blocked_through_chat_delivery(account, monkeypatch):
    client, uid = account
    db.save_profile(uid, {**PROFILE, "age": "30", "gender": "male", "height": "180",
                          "weight": "80", "allergies": "peanut allergy"})
    monkeypatch.setattr(appmod, "_build_profile_block", lambda *args: "Calorie target: 1260 kcal")
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(_food_payload("Peanuts"))))]))
    response = client.post("/chat", json={"message": "Give me a nutrition plan", "lang": "en"})
    text = "".join(event.get("t", "") for event in _events(response))
    assert text == nutrition.restriction_blocked_message("en")
    assert db.list_nutrition_plans(uid) == []


def _execution(uid):
    plan = build_training_plan(recommendation_blueprint_id="p0-execution", facts=PROFILE)
    db.update_conversation_runtime_state(f"account:{uid}", "p0-execution-conversation",
                                         workout_blueprint=serialize_conversation_plan(plan))
    session = completion_projection(plan, load_exercise_library())["sessions"][0]
    payload = {"workout_id": "p0-workout", "plan_id": plan.plan_id, "plan_version": plan.version,
               "session_id": session["session_id"], "completion_timestamp": "2026-09-05T10:00:00Z",
               "exercises": [{"prescription_id": item["prescription_id"], "exercise_id": item["exercise_id"],
                   "exercise_version": item["exercise_version"], "completed_sets": item["prescribed_sets"],
                   "actual_repetitions": item["rep_min"], "completed_repetitions": item["rep_min"]}
                   for item in session["exercises"]]}
    return plan, payload


def _post_execution(account, payload, state="unknown"):
    client, uid = account
    response = client.post("/api/workout", json={"session": {"completion": 100, "execution_state": state},
                                                "workout_completion": payload})
    assert response.status_code == 200, response.get_json()
    rows = client.get("/api/history").get_json()["workouts"]
    return next(row for row in rows if row["id"] == response.get_json()["id"])


def test_skipped_exercise_cannot_yield_100_after_db_roundtrip(account):
    _, payload = _execution(account[1])
    payload["exercises"][-1].update(completed_sets=0, actual_repetitions=None, completed_repetitions=0,
                                    execution_state="skipped")
    row = _post_execution(account, payload)
    assert row["completion"] < 100
    assert row["execution_state"] == "partial"
    assert row["exercises"][-1]["execution_state"] == "skipped"


def test_partial_execution_stays_partial(account):
    _, payload = _execution(account[1])
    payload["exercises"][0]["completed_sets"] = 1
    row = _post_execution(account, payload, "partial")
    assert row["execution_state"] == "partial"
    assert 0 < row["completion"] < 100


def test_missing_actual_reps_remain_unknown_even_when_legacy_reps_are_prefilled(account):
    plan, payload = _execution(account[1])
    for item in payload["exercises"]:
        item.pop("actual_repetitions")
    row = _post_execution(account, payload)
    assert row["execution_state"] == "unknown"
    assert row["completion"] != 100
    assert all(item["completed_repetitions"] is None for item in row["exercises"])
    assert appmod._advance_active_training_plan(plan, {"completed_workout": payload, "recovery": {}}) == plan


def test_abandoned_execution_remains_abandoned(account):
    _, payload = _execution(account[1])
    for item in payload["exercises"]:
        item.update(completed_sets=0, actual_repetitions=None, completed_repetitions=0)
    row = _post_execution(account, payload, "abandoned")
    assert row["execution_state"] == "abandoned"
    assert row["completion"] == 0
    assert "finished within" not in db.build_memory_context(account[1])


def test_partial_report_without_prescription_remains_partial():
    normalized = normalize_execution({"execution_state": "partial", "exercises": []})
    assert normalized["execution_state"] == "partial"
    assert normalized["completion"] is None


def test_legacy_history_is_unknown_not_100_percent(account):
    import uuid
    from sqlalchemy import insert
    with db.engine.begin() as connection:
        connection.execute(insert(db.workout_history).values(
            id=uuid.uuid4(), user_id=uuid.UUID(account[1]), completion=100,
            exercises=[{"name": "Bench press", "sets": 3, "reps": 10}]))
    row = account[0].get("/api/history").get_json()["workouts"][0]
    assert row["completion"] is None
    assert row["execution_state"] == "unknown"
    assert row["exercises"][0]["completed_repetitions"] is None


def test_execution_migration_preserves_legacy_rows_and_is_idempotent(tmp_path):
    from sqlalchemy import create_engine, text
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-execution.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE workout_history (id TEXT, completion INTEGER)"))
        connection.execute(text("INSERT INTO workout_history VALUES ('legacy', 100)"))
        db._add_execution_evidence(connection)
        db._add_execution_evidence(connection)
        row = connection.execute(text("SELECT id, completion, execution_state, completion_evidence FROM workout_history")).one()
    assert row == ("legacy", 100, None, None)


def test_observed_complete_execution_and_prescription_are_preserved(account):
    plan, payload = _execution(account[1])
    original = deepcopy(payload)
    row = _post_execution(account, payload)
    assert row["completion"] == 100 and row["execution_state"] == "completed"
    assert payload == original
    assert row["completion_evidence"]["plan_id"] == plan.plan_id


def test_empty_and_unavailable_constraints_are_distinct():
    empty = load_constraints(lambda: [], {"vertical_push"})
    def failed():
        raise RuntimeError("offline")
    unavailable = load_constraints(failed, {"vertical_push"})
    assert empty.state is ConstraintLoadState.AVAILABLE_EMPTY
    assert unavailable.state is ConstraintLoadState.UNAVAILABLE
    with pytest.raises(RuntimeError):
        unavailable.require_available()


def test_unrecognized_stored_constraint_does_not_collapse_to_empty(account):
    import uuid
    from sqlalchemy import insert
    with db.engine.begin() as connection:
        connection.execute(insert(db.account_training_constraints).values(
            id=uuid.uuid4(), user_id=uuid.UUID(account[1]), pattern="unknown_movement",
            source="explicit_user", state="active"))
    assert appmod._load_account_training_constraints(account[1]).state is ConstraintLoadState.UNAVAILABLE


def _events(response):
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")]


def test_constraint_read_failure_withholds_workout_and_keeps_exclusion(account, monkeypatch):
    client, uid = account
    db.add_account_training_constraints(uid, ("vertical_push",))
    def failed(*args):
        raise RuntimeError("offline")
    monkeypatch.setattr(db, "list_account_training_constraints", failed)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **kw: pytest.fail("model must not prescribe"))
    response = client.post("/chat", json={"message": "Give me a harder upper-body workout", "lang": "en"})
    events = _events(response)
    assert any(event.get("done") for event in events)
    assert not any("training_completion" in event for event in events)
    assert db.list_account_training_constraint_records(uid)[0]["pattern"] == "vertical_push"
    assert client.get("/api/profile").get_json()["training_constraint_load_state"] == "unavailable"


def test_constraint_write_failure_is_not_a_durable_acknowledgement(account, monkeypatch):
    client, uid = account
    def failed(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(db, "add_account_training_constraints", failed)
    response = client.post("/chat", json={"message": "Avoid overhead pressing", "lang": "en"})
    text = "".join(event.get("t", "") for event in _events(response))
    assert "couldn't save" in text
    assert not db.list_account_training_constraints(uid)


def test_constraint_write_empty_result_is_not_success(account, monkeypatch):
    client, _ = account
    monkeypatch.setattr(db, "add_account_training_constraints", lambda *args: [])
    response = client.post("/chat", json={"message": "Avoid overhead pressing", "lang": "en"})
    assert "couldn't save" in "".join(event.get("t", "") for event in _events(response))


@pytest.mark.parametrize("active", ("true", "false"))
def test_unavailable_constraints_block_ambiguous_request_and_legacy_fallback(account, monkeypatch, active):
    client, _ = account
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", active)
    monkeypatch.setattr(db, "list_account_training_constraints", lambda *args: None)
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **kw: pytest.fail("unsafe model egress"))
    response = client.post("/chat", json={"message": "What should I do today?", "lang": "en"})
    assert "".join(event.get("t", "") for event in _events(response)) == appmod._safety_constraints_unavailable_reply("en")


def test_harder_workout_still_respects_recorded_overhead_restriction(account, monkeypatch):
    client, uid = account
    monkeypatch.setattr(appmod.client.chat.completions, "create", lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"explanations":["Controlled workout."]}'))]))
    conversation = "p0-hard-workout-conversation"
    first = client.post("/chat", json={"message": "Avoid overhead pressing", "lang": "en", "conversation_id": conversation})
    assert any(event.get("done") for event in _events(first))
    assert "vertical_push" in db.list_account_training_constraints(uid)
    result = client.post("/chat", json={"message": "Give me a harder upper-body workout", "lang": "en", "conversation_id": conversation})
    events = _events(result)
    delivered = [event["training_completion"] for event in events if "training_completion" in event]
    assert delivered
    ids = {item["exercise_id"] for session in delivered[0]["sessions"] for item in session["exercises"]}
    library = load_exercise_library()
    assert all(library.get(item).movement_pattern.value != "vertical_push" for item in ids)
