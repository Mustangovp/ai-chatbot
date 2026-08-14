"""§7.2 — athlete_models get/save round-trip, upsert (not duplicate), uniqueness."""
import db as store
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, func, inspect, select


def _uid(email="athlete_model@example.com"):
    return store.get_or_create_user(email)


def test_get_absent_returns_none():
    uid = _uid("absent@example.com")
    assert store.get_athlete_state(uid) is None


def test_save_then_get_roundtrip():
    uid = _uid()
    state = {"schema": "athlete-model-v1",
             "vars": {"physical_fatigue": {"value": 0.5, "confidence": 0.3}},
             "updated_at": "2026-01-01T00:00:00+00:00"}
    store.save_athlete_state(uid, state)
    got = store.get_athlete_state(uid)
    assert got is not None
    assert got["vars"]["physical_fatigue"]["value"] == 0.5


def test_upsert_updates_not_duplicates():
    uid = _uid()
    store.save_athlete_state(uid, {"schema": "athlete-model-v1", "n": 1})
    store.save_athlete_state(uid, {"schema": "athlete-model-v1", "n": 2})
    got = store.get_athlete_state(uid)
    assert got["n"] == 2
    with store.engine.begin() as c:
        rows = c.execute(select(func.count()).select_from(store.athlete_models)
                         .where(store.athlete_models.c.user_id == store._as_uuid(uid))).scalar()
    assert rows == 1


def test_v14_constraint_lifecycle_migration_preserves_rows_and_is_idempotent(tmp_path):
    """A legacy v14 constraint becomes an active, auditable v15 row."""
    engine = create_engine(f"sqlite:///{tmp_path / 'v14.db'}")
    legacy = MetaData()
    constraints = Table(
        "account_training_constraints", legacy,
        Column("id", String(36), primary_key=True),
        Column("user_id", String(36), nullable=False),
        Column("pattern", String(48), nullable=False),
        Column("source", String(32), nullable=False),
    )
    versions = Table("schema_version", legacy, Column("version", Integer, primary_key=True))
    legacy.create_all(engine)
    with engine.begin() as connection:
        connection.execute(constraints.insert().values(
            id="constraint-v14", user_id="user-v14", pattern="vertical_push", source="explicit_user"))
        connection.execute(versions.insert(), [{"version": version} for version in range(1, 15)])

    def apply_pending_migrations():
        with engine.begin() as connection:
            applied = {row[0] for row in connection.execute(select(versions.c.version)).all()}
            for version, migration in store._MIGRATIONS:
                if version not in applied:
                    migration(connection)
                    connection.execute(versions.insert().values(version=version))

    apply_pending_migrations()
    apply_pending_migrations()

    columns = {column["name"] for column in inspect(engine).get_columns("account_training_constraints")}
    assert {"state", "retired_at"}.issubset(columns)
    migrated = Table("account_training_constraints", MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        row = connection.execute(select(
            migrated.c.pattern, migrated.c.state, migrated.c.retired_at,
        ).where(migrated.c.id == "constraint-v14")).one()
        applied = connection.execute(select(func.count()).select_from(versions)
                                     .where(versions.c.version == 15)).scalar_one()
    assert row == ("vertical_push", "active", None)
    assert applied == 1
