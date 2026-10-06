"""Saved nutrition is a read-only projection of real persisted typed plans."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import uuid

import pytest
from sqlalchemy import event, select, update

import app as appmod
import db as store
import nutrition_plan
from nutrition_validation import NutritionTargets


def _record(*, macro_targets=True, restrictions=(), language="en", snack=False):
    kinds = ("breakfast", "snack", "lunch", "dinner") if snack else ("breakfast", "lunch", "dinner")
    payload = {"meals": [{"meal_type": kind, "time": time, "foods": [{
        "display_name": "Rice" if language == "en" else "Ориз", "grams": "100.25",
        "protein_g": "20", "carbs_g": "40", "fat_g": "20", "kcal": "420",
        "measurement_state": "as_served",
    }]} for kind, time in zip(kinds, ("08:00", "10:00", "13:00", "19:00") if snack else ("08:00", "13:00", "19:00"))]}
    count = len(kinds)
    targets = NutritionTargets(kcal=Decimal(420 * count),
        protein=Decimal(20 * count) if macro_targets else None,
        carbs=Decimal(40 * count) if macro_targets else None,
        fat=Decimal(20 * count) if macro_targets else None)
    plan = nutrition_plan.build_plan(payload, targets, restrictions=restrictions,
        provenance={"generator": "private-test-provenance"}, language=language)
    return nutrition_plan.to_record(plan)


def _account():
    uid = store.get_or_create_user(f"saved-nutrition-{uuid.uuid4().hex}@example.com")
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, store.create_session(uid))
    return client, uid


def _save(uid, record, day=1):
    store.save_nutrition_plan(uid, record)
    with store.engine.begin() as connection:
        connection.execute(update(store.nutrition_plans).where(
            store.nutrition_plans.c.plan_id == record["id"]).values(
                created_at=datetime(2026, 10, day, tzinfo=timezone.utc)))


def test_anonymous_read_is_unauthenticated_and_post_is_not_supported():
    client = appmod.app.test_client()
    assert client.get("/api/nutrition").status_code == 401
    assert client.post("/api/nutrition", json={}).status_code == 405


def test_authenticated_empty_state_is_private_and_not_stored():
    client, _ = _account()
    response = client.get("/api/nutrition")
    assert response.status_code == 200
    assert response.json == {"latest_plan": None}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_only_newest_owned_plan_is_read_and_query_identity_is_ignored():
    client, uid = _account()
    _, other_uid = _account()
    old, newest, foreign = _record(), _record(language="bg"), _record()
    _save(uid, old, 1)
    _save(uid, newest, 2)
    _save(other_uid, foreign, 3)
    response = client.get(f"/api/nutrition?user_id={other_uid}&plan_id={foreign['id']}")
    assert response.status_code == 200
    assert response.json["latest_plan"]["created_at"] == newest["created_at_utc"]
    assert response.json["latest_plan"]["meals"][0]["foods"][0]["display_name"] == "Ориз"


def test_real_persisted_record_uses_existing_from_record_authority(monkeypatch):
    client, uid = _account()
    record = _record()
    _save(uid, record)
    original, calls = nutrition_plan.from_record, []
    def observed(value):
        calls.append(deepcopy(value))
        return original(value)
    monkeypatch.setattr(nutrition_plan, "from_record", observed)
    assert client.get("/api/nutrition").json["latest_plan"] is not None
    assert calls == [record]


def test_legacy_text_alone_does_not_populate_or_get_parsed(monkeypatch):
    client, uid = _account()
    store.save_nutrition(uid, "| Breakfast | Rice | 100g | 420 kcal |")
    monkeypatch.setattr(nutrition_plan, "from_record", lambda *a: pytest.fail("legacy parsed"))
    assert client.get("/api/nutrition").json == {"latest_plan": None}


@pytest.mark.parametrize("corruption", ["targets", "meals", "measurement", "grams", "identity",
    "version", "timestamp", "naive_timestamp", "totals", "meal_macros", "order", "restrictions"])
def test_malformed_newest_fails_closed_without_older_fallback(corruption):
    client, uid = _account()
    old, newest = _record(), _record()
    _save(uid, old, 1)
    _save(uid, newest, 2)
    raw = deepcopy(newest)
    if corruption == "targets": raw["targets"]["kcal"] = "not-a-number"
    elif corruption == "meals": raw["meals"] = []
    elif corruption == "measurement": raw["meals"][0]["foods"][0]["measurement_state"] = "guessed"
    elif corruption == "grams": raw["meals"][0]["foods"][0]["grams"] = "-1"
    elif corruption == "identity": raw["id"] = "foreign-plan"
    elif corruption == "version": raw["version"] = "foreign-version"
    elif corruption == "timestamp": raw["created_at_utc"] = "not-a-date"
    elif corruption == "naive_timestamp": raw["created_at_utc"] = "2026-10-01T10:00:00"
    elif corruption == "totals": raw["totals"]["kcal"] = "1261"
    elif corruption == "meal_macros": raw["meals"][0]["macros"]["protein_g"] = "21"
    elif corruption == "order": raw["meals"].reverse()
    elif corruption == "restrictions": raw["restrictions"] = ["no rice"]
    with store.engine.begin() as connection:
        connection.execute(update(store.nutrition_plans).where(
            store.nutrition_plans.c.plan_id == newest["id"]).values(plan=raw))
    response = client.get("/api/nutrition")
    assert response.status_code == 200
    assert response.json == {"latest_plan": None}


def test_targets_totals_meals_and_grams_are_exact_not_recalculated():
    client, uid = _account()
    record = _record(snack=True)
    record["targets"]["kcal"] = "1700.0000000000000001"  # Existing tolerance, not a new target.
    _save(uid, record)
    plan = client.get("/api/nutrition").json["latest_plan"]
    assert plan["targets"]["kcal"] == record["targets"]["kcal"]
    assert plan["totals"] == record["totals"]
    assert [meal["meal_type"] for meal in plan["meals"]] == ["breakfast", "snack", "lunch", "dinner"]
    for public, saved in zip(plan["meals"], record["meals"]):
        assert public["time"] == saved["time"]
        assert public["macros"] == saved["macros"]
        assert public["foods"][0]["grams"] == "100.25"
        assert public["foods"][0]["display_name"] == saved["foods"][0]["display_name"]


def test_missing_macro_targets_remain_null_not_zero():
    client, uid = _account()
    record = _record(macro_targets=False)
    _save(uid, record)
    targets = client.get("/api/nutrition").json["latest_plan"]["targets"]
    assert targets == {"kcal": "1260", "protein_g": None, "carbs_g": None, "fat_g": None}


@pytest.mark.parametrize("state", ["raw", "cooked", "drained", "ready_to_eat", "as_served", "package_weight", None])
def test_all_persisted_measurement_states_and_absence_are_preserved(state):
    client, uid = _account()
    record = _record()
    record["meals"][0]["foods"][0]["measurement_state"] = state
    record["meals"][0].pop("time")
    _save(uid, record)
    meal = client.get("/api/nutrition").json["latest_plan"]["meals"][0]
    assert meal["foods"][0]["measurement_state"] == state
    assert meal["time"] is None


def test_current_profile_cannot_change_saved_targets_or_restrictions():
    client, uid = _account()
    record = _record(restrictions=("peanut allergy",))
    _save(uid, record)
    before = client.get("/api/nutrition").json
    store.save_profile(uid, {"weight": "110", "goal": "fat_loss", "allergies": "no rice"})
    assert client.get("/api/nutrition").json == before
    assert before["latest_plan"]["restrictions"] == ["peanut allergy"]


def test_public_projection_has_only_allowlisted_fields():
    client, uid = _account()
    record = _record()
    _save(uid, record)
    result = client.get("/api/nutrition").json
    assert set(result) == {"latest_plan"}
    plan = result["latest_plan"]
    assert set(plan) == {"created_at", "targets", "totals", "meals", "restrictions"}
    for meal in plan["meals"]:
        assert set(meal) == {"meal_type", "time", "foods", "macros"}
        for food in meal["foods"]:
            assert set(food) == {"display_name", "grams", "measurement_state"}
    serialized = json.dumps(result)
    for private in [uid, record["id"], record["version"], "private-test-provenance",
                    record["meals"][0]["id"], record["meals"][0]["foods"][0]["id"]]:
        assert str(private) not in serialized


def test_read_is_select_only_and_never_generates_or_calls_model(monkeypatch):
    client, uid = _account()
    record = _record()
    _save(uid, record)
    with store.engine.connect() as connection:
        before = dict(connection.execute(select(store.nutrition_plans).where(
            store.nutrition_plans.c.plan_id == record["id"])).mappings().one())
    def forbidden(*args, **kwargs):
        pytest.fail("read invoked a write, profile recalculation, generation or model")
    for name in ("save_nutrition", "save_nutrition_plan", "save_profile", "get_profile"):
        monkeypatch.setattr(store, name, forbidden)
    for name in ("_daily_nutrition_targets", "_nutrition_engine_v2_active",
                 "_nutrition_engine_v2_shadow_active", "_update_learning_engine"):
        monkeypatch.setattr(appmod, name, forbidden)
    monkeypatch.setattr(nutrition_plan, "build_plan", forbidden)
    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/nutrition")
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and response.json["latest_plan"] is not None
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert all("nutrition_history" not in sql for sql in statements)
    with store.engine.connect() as connection:
        after = dict(connection.execute(select(store.nutrition_plans).where(
            store.nutrition_plans.c.plan_id == record["id"])).mappings().one())
    assert after == before


def test_database_failure_is_unavailable_not_empty_and_logs_class_only(monkeypatch, capsys):
    client, _ = _account()
    def broken(*args):
        raise RuntimeError("PRIVATE_ACCOUNT_NUTRITION_CONTENT")
    monkeypatch.setattr(store, "get_saved_nutrition", broken)
    response = client.get("/api/nutrition")
    assert response.status_code == 503
    assert response.json == {"error": "nutrition_data_unavailable"}
    captured = capsys.readouterr().out
    assert "[nutrition-surface] read unavailable: RuntimeError" in captured
    assert "PRIVATE_ACCOUNT_NUTRITION_CONTENT" not in captured
