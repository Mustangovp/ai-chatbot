"""v27 repairs pre-existing structured nutrition tables without inventing plans."""
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select, text

import db as store
import nutrition_plan
from nutrition_validation import NutritionTargets


def _plan_record():
    payload = {"meals": [{"meal_type": meal, "foods": [{
        "display_name": "Rice", "grams": "100", "protein_g": "20",
        "carbs_g": "40", "fat_g": "20", "kcal": "420",
        "measurement_state": "as_served",
    }]} for meal in ("breakfast", "lunch", "dinner")]}
    plan = nutrition_plan.build_plan(
        payload, NutritionTargets(kcal=Decimal("1260")), restrictions=(),
        provenance={}, language="en")
    return nutrition_plan.to_record(plan)


def _legacy_engine(monkeypatch, *, source_column="plan", document=None):
    engine = create_engine("sqlite://", future=True)
    row_id, user_id = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at DATETIME)"))
        connection.execute(text(
            "CREATE TABLE nutrition_plans (id VARCHAR(36) PRIMARY KEY, "
            "user_id VARCHAR(36) NOT NULL, created_at DATETIME, "
            f"{source_column} JSON)"))
        if document is not None:
            connection.execute(text(
                f"INSERT INTO nutrition_plans (id, user_id, created_at, {source_column}) "
                "VALUES (:id, :user_id, '2026-01-01', :document)"), {
                    "id": row_id, "user_id": user_id, "document": json.dumps(document),
                })
        for version in range(1, 27):
            connection.execute(text("INSERT INTO schema_version (version) VALUES (:version)"),
                               {"version": version})
    monkeypatch.setattr(store, "engine", engine)
    return engine, row_id, user_id


def _versions(engine):
    with engine.begin() as connection:
        return {row[0] for row in connection.execute(select(store.schema_version.c.version))}


def test_v27_fresh_database_has_canonical_nutrition_schema(monkeypatch):
    engine = create_engine("sqlite://", future=True)
    monkeypatch.setattr(store, "engine", engine)
    store.run_migrations()
    columns = {column["name"]: column for column in inspect(engine).get_columns("nutrition_plans")}
    assert {"id", "user_id", "created_at", "plan_id", "version", "plan"} <= columns.keys()
    assert all(not columns[name]["nullable"] for name in ("plan_id", "version", "plan"))
    with engine.begin() as connection:
        assert store._nutrition_plan_id_is_unique(connection)
    assert 27 in _versions(engine)


@pytest.mark.parametrize("source_column", ("plan", "content", "data"))
def test_v27_legacy_row_is_preserved_and_missing_columns_repaired(monkeypatch, source_column):
    document = _plan_record()
    engine, row_id, user_id = _legacy_engine(
        monkeypatch, source_column=source_column, document=document)
    store.run_migrations()
    store.run_migrations()
    columns = {column["name"] for column in inspect(engine).get_columns("nutrition_plans")}
    assert {"plan_id", "version", "plan"} <= columns
    with engine.begin() as connection:
        row = connection.execute(text(
            "SELECT id, user_id, plan_id, version, plan FROM nutrition_plans "
            "WHERE id = :id"), {"id": row_id}).mappings().one()
        assert store._nutrition_plan_id_is_unique(connection)
    assert row["id"] == row_id and row["user_id"] == user_id
    assert row["plan_id"] == document["id"]
    assert row["version"] == document["version"]
    assert json.loads(row["plan"]) == document
    assert store.list_nutrition_plans(user_id)[0]["plan"] == document
    if source_column != "plan":
        with engine.begin() as connection:
            assert connection.execute(text(
                f"SELECT {source_column} FROM nutrition_plans WHERE id = :id"),
                {"id": row_id}).scalar_one() == json.dumps(document)
    assert 27 in _versions(engine)


def test_v27_repairs_empty_legacy_table_without_dropping_it(monkeypatch):
    engine, _, _ = _legacy_engine(monkeypatch, document=None)
    store.run_migrations()
    columns = {column["name"] for column in inspect(engine).get_columns("nutrition_plans")}
    assert {"plan_id", "version", "plan"} <= columns
    assert 27 in _versions(engine)


def test_v27_unmappable_legacy_row_preserved_and_not_recorded(monkeypatch):
    engine, row_id, _ = _legacy_engine(monkeypatch, source_column="content",
                                       document={"id": "incomplete", "version": "nutrition-plan-v1"})
    with pytest.raises(RuntimeError, match="cannot be migrated deterministically"):
        store.run_migrations()
    with engine.begin() as connection:
        assert connection.execute(text(
            "SELECT content FROM nutrition_plans WHERE id = :id"),
            {"id": row_id}).scalar_one() == json.dumps(
                {"id": "incomplete", "version": "nutrition-plan-v1"})
    assert 27 not in _versions(engine)
