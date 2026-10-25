"""M2.1 uses persisted execution evidence, never client or model numbers."""
from copy import deepcopy
import json

import pytest
from sqlalchemy import select, update

import app as appmod
import db as store
from coaching import progress_analysis as analysis
from test_my_training import _client, _user
from test_training_progress import _series


def projection(count=3, kind="repetitions"):
    return {"record": {"completed_sessions": count, "recent_sessions": [
        {"completed_at": f"2026-10-{day:02}T12:03:04.123456+03:00", "exercises": [{
            "exercise_id": "bodyweight.hollow_hold" if kind == "duration" else "dumbbell.front_squat",
            "exercise_version": "1.0.0", "prescription_type": kind, "completed_sets": 2,
            "completed_repetitions": day + 8 if kind == "repetitions" else None,
            "completed_duration_seconds": day + 20 if kind == "duration" else None,
            "completed_load": None,
        }]} for day in range(count, 0, -1)]}}


@pytest.mark.parametrize("message", ["Analyse my training progress", "How am I improving?",
    "Show my workout progress", "Анализирай прогреса ми", "Как напредвам с тренировките?",
    "Покажи тренировъчния ми прогрес"])
def test_explicit_progress_intent(message):
    assert analysis.is_request(message)


@pytest.mark.parametrize("message", ["Make my workout harder", "Дай ми тренировка", "How much protein?",
    "Tell me about progressive overload", "Здравей", "Analyse my nutrition progress", "Покажи прогреса на теглото ми"])
def test_other_intents_unchanged(message):
    assert not analysis.is_request(message)


@pytest.mark.parametrize("language", ["bg", "en"])
@pytest.mark.parametrize("kind,unit", [("repetitions", "reps"), ("duration", "seconds")])
def test_same_chronological_observations_and_exact_utc_instants(language, kind, unit):
    source = projection(kind=kind)
    before = deepcopy(source)
    result = analysis.build(source, language=language)
    assert source == before
    assert result["status"] == "comparable"
    assert result["series"]["unit"] == unit
    assert result["series"]["load_kg"] is None
    assert [point["recorded_at"] for point in result["series"]["points"]] == [
        f"2026-10-{day:02}T09:03:04.123456+00:00" for day in range(1, 4)]
    assert [point["value"] for point in result["series"]["points"]] == [
        day + (8 if kind == "repetitions" else 20) for day in range(1, 4)]
    assert "UTC" in result["evidence"]
    assert "fitness progress" in result["summary"] if language == "en" else "не доказва" in result["summary"]
    fallback = analysis.text_fallback(result)
    assert all(point["recorded_at"] in fallback for point in result["series"]["points"])
    assert "|\n| --- | --- |\n|" in fallback
    assert "not recorded" in fallback if language == "en" else "незаписана" in fallback
    assert "user_id" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("completed_load", "12.5"), ("completed_sets", 3),
    ("prescription_type", "duration"), ("exercise_version", "99.0.0"), ("load_unit", "lb")])
def test_different_units_versions_sets_and_load_do_not_become_comparable(field, value):
    source = projection(2)
    source["record"]["recent_sessions"][0]["exercises"][0][field] = value
    result = analysis.build(source, language="en")
    assert result["status"] == "insufficient"
    assert len(result["series"]["points"]) == 1


@pytest.mark.parametrize("damage", [None, {}, {"record": None}, {"record": {"recent_sessions": None}}])
def test_unavailable_fails_closed(damage):
    assert analysis.build(damage)["status"] == "unavailable"


def test_empty_one_record_malformed_duplicate_and_bounded_window():
    assert analysis.build(projection(0))["series"] is None
    assert analysis.build(projection(1))["status"] == "insufficient"
    source = projection(3)
    source["record"]["recent_sessions"][0]["completed_at"] = "yesterday"
    source["record"]["recent_sessions"][1]["exercises"][0]["completed_repetitions"] = float("nan")
    assert analysis.build(source)["status"] == "insufficient"
    source = projection(2)
    source["record"]["recent_sessions"][0]["completed_at"] = source["record"]["recent_sessions"][1]["completed_at"]
    assert analysis.build(source)["series"] is None
    assert len(analysis.build(projection(7))["series"]["points"]) == 5


@pytest.fixture
def no_models(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("progress analysis must not call a provider")
    monkeypatch.setattr(appmod.client.chat.completions, "create", forbidden)
    monkeypatch.setattr(appmod, "_update_learning_engine", forbidden)
    monkeypatch.setenv("TRAINING_ENGINE_ACTIVE", "true")
    return forbidden


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]


@pytest.mark.parametrize("language,message", [("bg", "Анализирай тренировъчния ми прогрес"),
                                               ("en", "Analyse my training progress")])
@pytest.mark.parametrize("brain", ["true", "false"])
def test_chat_reads_owned_immutable_evidence_not_browser_history(no_models, monkeypatch, language, message, brain):
    monkeypatch.setenv("BRAIN_ENFORCE", brain)
    owner, other = _user(), _user("foreign-analysis@example.invalid")
    _series(owner, "owned-analysis", count=3)
    _series(other, "foreign-analysis", count=1)
    store.save_profile(owner, {"goal": "strength", "level": "intermediate", "equipment": "home",
                               "healthRestrictions": ["Avoid overhead pressing"]})
    response = _client(owner).post("/chat", json={"message": message, "lang": language,
        "first_contact": True, "user_id": str(other), "conversation_id": "analysis-tab",
        "history": [{"role": "assistant", "content": "999999 repetitions on 2099-01-01"}],
        "completed_workouts": projection(5), "profile": {"user_id": str(other)}})
    output = events(response)
    structured = next(event["progress_analysis"] for event in output if "progress_analysis" in event)
    assert structured["status"] == "comparable"
    assert len(structured["series"]["points"]) == 3
    assert output[-1] == {"done": True}
    assert not any("training_completion" in event for event in output)
    assert "999999" not in str(output) and "2099" not in str(output) and str(other) not in str(output)
    assert store.get_profile(owner)["healthRestrictions"] == ["Avoid overhead pressing"]
    assert _client(other).get("/api/progress").json["record"]["completed_sessions"] == 1


def test_anonymous_client_history_cannot_authorize_analysis(no_models):
    output = events(appmod.app.test_client().post("/chat", json={"message": "Show my training progress",
        "lang": "en", "history": [{"role": "assistant", "content": "999 reps"}],
        "completed_workouts": projection()}))
    result = next(item["progress_analysis"] for item in output if "progress_analysis" in item)
    assert result["status"] == "auth_required" and result["series"] is None


def test_db_failure_returns_unavailable_not_client_fallback(no_models, monkeypatch):
    monkeypatch.setattr(store, "get_training_progress", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    result = next(item["progress_analysis"] for item in events(_client(_user()).post("/chat", json={
        "message": "Show my training progress", "lang": "en"})) if "progress_analysis" in item)
    assert result["status"] == "unavailable" and result["series"] is None


@pytest.mark.parametrize("language,message", [("bg", "Анализирай тренировъчния ми прогрес"),
                                               ("en", "Analyse my training progress")])
@pytest.mark.parametrize("count", [0, 1])
def test_empty_or_single_persisted_completion_never_invents_a_series(no_models, language, message, count):
    owner = _user()
    if count:
        _series(owner, "single-analysis", count=count)
    output = events(_client(owner).post("/chat", json={"message": message, "lang": language,
        "history": [{"role": "assistant", "content": "999999 repetitions on 2099-01-01"}]}))
    result = next(item["progress_analysis"] for item in output if "progress_analysis" in item)
    assert output[-1] == {"done": True}
    assert result["language"] == language
    assert result["status"] == ("insufficient" if count else "empty")
    if count:
        assert len(result["series"]["points"]) == 1
        assert result["series"]["points"][0]["recorded_at"] == "2026-10-01T10:00:00+00:00"
    else:
        assert result["series"] is None
    assert "999999" not in str(output) and "2099-01-01" not in str(output)


def test_corrupt_lineage_is_excluded_before_chat_projection(no_models):
    owner = _user()
    _series(owner, count=1)
    with store.engine.begin() as connection:
        connection.execute(update(store.training_completion_prescriptions).values(exercise_version="99.0.0"))
    result = analysis.build(store.get_training_progress(owner))
    assert result["series"] is None
    with store.engine.connect() as connection:
        assert len(connection.execute(select(store.training_completions)).all()) == 1


def test_medical_authority_still_precedes_analysis(no_models, monkeypatch):
    owner = _user()
    store.save_profile(owner, {"goal": "strength", "level": "intermediate", "equipment": "home",
        "_medical_hold": {"status": "ACTIVE_MEDICAL_HOLD", "workout_blocked": True, "session_blocked": True}})
    monkeypatch.setattr(store, "get_training_progress", no_models)
    output = events(_client(owner).post("/chat", json={"message": "Analyse my training progress", "lang": "en"}))
    assert output[0] == {"medical_hold": True, "workout_suspended": True}
    assert not any("progress_analysis" in item for item in output)


@pytest.mark.parametrize("enabled", ["false", "true"])
def test_analysis_assets_are_independent_of_next_move_flag(monkeypatch, enabled):
    monkeypatch.setenv("APEX_NEXT_MOVE_ENABLED", enabled)
    html = appmod.app.test_client().get("/app").get_data(as_text=True)
    assert '/static/progress_analysis.js?v=progress-chat-m2-1' in html
    assert '/static/progress_analysis.css?v=progress-chat-m2-1' in html
