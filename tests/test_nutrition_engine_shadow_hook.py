"""Phase 6C: isolated read-only Nutrition Engine V2 shadow hook.

Unit tests for shadow_hook (flag, eligibility, bounded dispatcher, projection,
privacy, isolation) plus /chat integration equivalence (quota/LLM/persistence/
SSE/voice unchanged; dispatch fires once; flag-off is inert).
"""
from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from pathlib import Path

import pytest

import app as appmod
from nutrition_engine import shadow_hook as sh
from nutrition_engine.feasibility import FeasibilityCode
from nutrition_engine.optimizer import optimize
from nutrition_engine.shadow_hook import ShadowSkipReason


# ── module-state reset ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_shadow_state():
    sh._reset_runtime_for_testing()
    yield
    sh._reset_runtime_for_testing()


def _drain():
    sh.shutdown_runtime(wait=True)


def _proj():
    return sh.build_projection(language="bg", calorie_target=Decimal("1914"),
                               protein_target=Decimal("198"))


# ── flag ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (None, False), ("", False), ("false", False), ("nope", False), ("1", False),
    ("yes", False), ("true", True), ("TRUE", True), ("  true  ", True), ("True", True),
])
def test_flag_is_fail_closed(value, expected):
    getenv = (lambda k, d: d) if value is None else (lambda k, d: value)
    assert sh.shadow_flag_enabled(getenv) is expected


# ── eligibility ──────────────────────────────────────────────────────────────

def _elig(**over):
    base = dict(flag_enabled=True, is_nutrition=True, is_full_day=True,
                calorie_target=Decimal("1914"), protein_target=Decimal("198"),
                route_is_medical=False, session_start=False, already_attempted=False,
                allergy_prose="", preference_tokens="")
    base.update(over)
    return sh.classify_eligibility(**base)


def test_eligibility_happy_path():
    d = _elig()
    assert d.eligible is True and d.reason is None


@pytest.mark.parametrize("over,reason", [
    (dict(flag_enabled=False), ShadowSkipReason.SHADOW_DISABLED),
    (dict(session_start=True), ShadowSkipReason.SESSION_START),
    (dict(route_is_medical=True), ShadowSkipReason.MEDICAL_ROUTE),
    (dict(is_nutrition=False), ShadowSkipReason.NOT_NUTRITION),
    (dict(is_full_day=False), ShadowSkipReason.NOT_FULL_DAY),
    (dict(calorie_target=None), ShadowSkipReason.MISSING_AUTHORITATIVE_TARGETS),
    (dict(protein_target=None), ShadowSkipReason.MISSING_AUTHORITATIVE_TARGETS),
    (dict(allergy_prose="nuts"), ShadowSkipReason.ALLERGY_AUTHORITY_UNAVAILABLE),
    (dict(preference_tokens="vegan"), ShadowSkipReason.UNSUPPORTED_TYPED_CONSTRAINT),
    (dict(already_attempted=True), ShadowSkipReason.DUPLICATE_EXECUTION),
])
def test_eligibility_skips(over, reason):
    d = _elig(**over)
    assert d.eligible is False and d.reason is reason


def test_allergy_prose_never_becomes_omnivore():
    # any non-empty allergy prose or preference token must skip, never run omnivore
    assert _elig(allergy_prose=" ца ").eligible is False  # whitespace-only? no, has cyr
    assert _elig(allergy_prose="   ").eligible is True     # truly empty allowed
    assert _elig(preference_tokens="vegetarian").reason is ShadowSkipReason.UNSUPPORTED_TYPED_CONSTRAINT


# ── projection privacy ───────────────────────────────────────────────────────

def test_projection_and_request_carry_no_identity_or_prose():
    p = sh.build_projection(language="en", calorie_target=Decimal("1914"),
                            protein_target=Decimal("198"), carbs_target=Decimal("200"))
    blob = repr(p) + repr(sh.to_request(p))
    for token in ("allergies", "email", "user_id", "conversation", "@", "profile",
                  "device", "prompt", "message"):
        assert token not in blob.lower()
    assert p.diet_constraints.diet_type == "standard_omnivore"
    assert p.catalog_mode.value == "development"


# ── bounded, non-blocking dispatcher ─────────────────────────────────────────

def test_executor_created_once_per_process():
    e1 = sh._ensure_executor()
    e2 = sh._ensure_executor()
    assert e1 is e2


def test_executor_shutdown_is_idempotent_and_prevents_reinitialization():
    sh._ensure_executor()
    sh.shutdown_runtime(wait=True)
    sh.shutdown_runtime(wait=True)
    assert sh._executor is None
    with pytest.raises(RuntimeError, match="shut down"):
        sh._ensure_executor()


def test_runtime_self_validation_fails_closed_without_leaking_a_permit(monkeypatch):
    monkeypatch.setattr(sh, "_MAX_WORKERS", 2)
    assert sh.dispatch(_proj()) is False
    telemetry = sh.snapshot_telemetry()
    assert telemetry["initialization_failure"] == 1
    assert telemetry["dropped"] == 1
    for _ in range(sh._MAX_INFLIGHT):
        assert sh._semaphore.acquire(blocking=False) is True


def test_dispatch_submits_and_runs_in_background(tmp_path):
    records = []
    assert sh.dispatch(_proj(), sink=records.append) is True
    _drain()
    assert len(records) == 1 and records[0].outcome == "success"
    telemetry = sh.snapshot_telemetry()
    assert telemetry["dispatched"] == 1
    assert telemetry["completed"] == 1
    assert telemetry["current_inflight"] == 0
    assert telemetry["current_queue_depth"] == 0


def test_dispatch_is_non_blocking():
    gate = threading.Event()
    started = threading.Event()

    def slow_sink(_rec):
        started.set()
        gate.wait(2.0)

    t0 = time.perf_counter()
    ok = sh.dispatch(_proj(), sink=slow_sink)
    elapsed = time.perf_counter() - t0
    assert ok is True
    assert elapsed < 0.2  # caller returned immediately; did not wait for the task
    gate.set()
    _drain()


def test_saturated_queue_drops_without_blocking_or_inline_execution():
    gate = threading.Event()
    ran = []

    def blocking_sink(_rec):
        ran.append(1)
        gate.wait(2.0)

    # fill both permits (1 running + 1 queued)
    assert sh.dispatch(_proj(), sink=blocking_sink) is True
    assert sh.dispatch(_proj(), sink=blocking_sink) is True
    # third is dropped: returns immediately, does not run inline
    dropped_sink_called = []
    t0 = time.perf_counter()
    ok = sh.dispatch(_proj(), sink=lambda r: dropped_sink_called.append(1))
    assert time.perf_counter() - t0 < 0.2
    assert ok is False
    assert dropped_sink_called == []
    telemetry = sh.snapshot_telemetry()
    assert telemetry["dropped"] == 1
    assert telemetry["maximum_queue_depth"] <= 1
    gate.set()
    _drain()


def test_semaphore_released_after_success_and_after_exception(monkeypatch):
    # success releases
    r = []
    sh.dispatch(_proj(), sink=r.append); _drain()
    for _ in range(sh._MAX_INFLIGHT):
        assert sh._semaphore.acquire(blocking=False) is True
    for _ in range(sh._MAX_INFLIGHT):
        sh._semaphore.release()
    sh._reset_runtime_for_testing()
    # exception in the engine still releases and never escapes
    monkeypatch.setattr(sh, "build_nutrition_plan",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert sh.dispatch(_proj()) is True
    _drain()
    assert sh.snapshot_telemetry()["exception"] == 1
    for _ in range(sh._MAX_INFLIGHT):
        assert sh._semaphore.acquire(blocking=False) is True


def test_optimizer_cooperatively_returns_dedicated_timeout():
    from tests.test_nutrition_engine_phase5 import CATALOG, POLICY
    from nutrition_engine.candidate_builder import build_candidates
    from nutrition_engine.models import DietConstraints, NutritionTargets

    targets = NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198"))
    plan = build_candidates(CATALOG, targets, DietConstraints(), ("breakfast", "lunch", "dinner"), POLICY)
    assert plan is not None
    result = optimize(CATALOG, targets, DietConstraints(), plan.selections, POLICY,
                      deadline_monotonic=0.0, clock=lambda: 1.0)
    assert result.code is FeasibilityCode.SHADOW_TIMEOUT


def test_timeout_telemetry_and_permit_release(monkeypatch):
    from nutrition_engine.models import NutritionPlanCode, NutritionPlanOutcome
    from nutrition_engine.service import NutritionPlanResult

    timeout = NutritionPlanResult(
        NutritionPlanOutcome.TIMEOUT, NutritionPlanCode.SHADOW_TIMEOUT,
        "test", "test",
    )
    monkeypatch.setattr(sh, "build_nutrition_plan", lambda *a, **k: timeout)
    assert sh.dispatch(_proj()) is True
    _drain()
    telemetry = sh.snapshot_telemetry()
    assert telemetry["timeout"] == 1
    assert telemetry["completed"] == 1
    for _ in range(sh._MAX_INFLIGHT):
        assert sh._semaphore.acquire(blocking=False) is True


def test_shutdown_cancels_queued_work_and_releases_every_permit(monkeypatch):
    gate = threading.Event()
    started = threading.Event()

    def blocking_build(*args, **kwargs):
        started.set()
        gate.wait(1.0)
        from nutrition_engine.service import build_nutrition_plan as real_build
        return real_build(*args, **kwargs)

    monkeypatch.setattr(sh, "build_nutrition_plan", blocking_build)
    assert sh.dispatch(_proj()) is True
    assert started.wait(0.5)
    assert sh.dispatch(_proj()) is True
    shutdown = threading.Thread(target=sh.shutdown_runtime, kwargs={"wait": True})
    shutdown.start()
    gate.set()
    shutdown.join(1.0)
    assert not shutdown.is_alive()
    telemetry = sh.snapshot_telemetry()
    assert telemetry["shutdown_cancelled"] == 1
    assert telemetry["current_inflight"] == 0
    assert telemetry["current_queue_depth"] == 0
    for _ in range(sh._MAX_INFLIGHT):
        assert sh._semaphore.acquire(blocking=False) is True


# ── isolation (static) ───────────────────────────────────────────────────────

def test_shadow_hook_has_no_forbidden_imports():
    source = (Path(appmod.__file__).parent / "nutrition_engine" / "shadow_hook.py").read_text(encoding="utf-8")
    # import-shaped / attribute-access tokens only (prose in the docstring is fine)
    for token in ("import app", "from app", "import flask", "from flask", "flask.",
                  "import requests", "requests.get", "requests.post", "import urllib",
                  "import httpx", "import socket", "socket.", "sqlalchemy", "store.",
                  "import openai", "from openai", "OpenAI(", "nutrition_generation",
                  "NUTRITION_ENGINE_V2_ACTIVE"):
        assert token not in source, token


# ── /chat integration equivalence (dispatch spied → deterministic) ──────────

@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _nutrition_env(monkeypatch, dispatch_spy=None):
    # Force a full-day nutrition request with authoritative targets, deterministically.
    import nutrition_validation as nv
    monkeypatch.setattr(appmod.nutrition_validation, "is_full_day_request", lambda *a, **k: True)
    monkeypatch.setattr(appmod, "_daily_nutrition_targets",
                        lambda *a, **k: nv.NutritionTargets(Decimal("1914"), Decimal("198")))
    # fake LLM stream + counter
    calls = {"llm": 0}
    from tests.test_chat_enforcement import _Chunk

    def fake_create(**kwargs):
        calls["llm"] += 1
        def stream():
            yield _Chunk("| Meal | Food | Quantity | Protein (g) | Carbs (g) | Fat (g) | Kcal |")
        return stream()
    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)
    # spy quota + persistence
    calls["quota"] = 0
    calls["persist"] = 0
    monkeypatch.setattr(appmod.store, "free_usage_consume",
                        lambda *a, **k: calls.__setitem__("quota", calls["quota"] + 1) or {"allowed": True})
    monkeypatch.setattr(appmod.store, "add_conversation",
                        lambda *a, **k: calls.__setitem__("persist", calls["persist"] + 1))
    if dispatch_spy is not None:
        monkeypatch.setattr(sh, "dispatch", dispatch_spy)
    return calls


def _events(resp):
    return [json.loads(l[6:]) for l in resp.get_data(as_text=True).splitlines() if l.startswith("data: ")]


def _post(client):
    return client.post("/chat", json={"message": "give me a full day menu", "lang": "en", "profile": {}})


def test_flag_off_does_not_dispatch_and_is_inert(client, monkeypatch):
    monkeypatch.delenv("NUTRITION_ENGINE_V2_SHADOW", raising=False)
    spied = []
    _nutrition_env(monkeypatch, dispatch_spy=lambda *a, **k: spied.append(1) or True)
    ev_off = _events(_post(client))
    assert spied == []  # zero V2 dispatch when disabled
    assert any(e.get("done") for e in ev_off)  # canonical stream still completes


def test_flag_on_dispatches_once_and_leaves_canonical_identical(client, monkeypatch):
    # baseline (flag off)
    monkeypatch.delenv("NUTRITION_ENGINE_V2_SHADOW", raising=False)
    base_calls = _nutrition_env(monkeypatch)
    base_ev = _events(_post(client))
    base = (base_calls["llm"], base_calls["quota"], base_calls["persist"], base_ev)

    # flag on, dispatch spied (no real threads)
    monkeypatch.setenv("NUTRITION_ENGINE_V2_SHADOW", "true")
    spied = []
    on_calls = _nutrition_env(monkeypatch, dispatch_spy=lambda *a, **k: spied.append(1) or True)
    on_ev = _events(_post(client))

    assert len(spied) == 1                              # dispatched exactly once
    assert on_calls["llm"] == base[0]                   # no second LLM call
    assert on_calls["quota"] == base[1]                 # no second quota charge
    assert on_calls["persist"] == base[2]               # no extra persistence
    assert on_ev == base[3]                             # SSE payloads + order identical
    assert sum(1 for e in on_ev if e.get("done")) == 1  # exactly one done
    blob = json.dumps(on_ev, ensure_ascii=False)
    for tok in ("shadow", "projection", "dev_", "source_", "skip_"):
        assert tok not in blob                          # no shadow leakage in SSE


def test_shadow_dispatch_exception_leaves_production_unchanged(client, monkeypatch):
    monkeypatch.delenv("NUTRITION_ENGINE_V2_SHADOW", raising=False)
    base_calls = _nutrition_env(monkeypatch)
    base_ev = _events(_post(client))

    monkeypatch.setenv("NUTRITION_ENGINE_V2_SHADOW", "true")
    on_calls = _nutrition_env(monkeypatch,
                              dispatch_spy=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    on_ev = _events(_post(client))
    assert on_ev == base_ev                             # canonical SSE unchanged
    assert on_calls["quota"] == base_calls["quota"]
    assert on_calls["persist"] == base_calls["persist"]


def test_voice_speech_text_unchanged_with_flag_on(client, monkeypatch):
    monkeypatch.delenv("NUTRITION_ENGINE_V2_SHADOW", raising=False)
    _nutrition_env(monkeypatch)
    base = [e for e in _events(client.post("/chat", json={"message": "give me a full day menu", "lang": "en", "voice": True, "profile": {}}))]
    monkeypatch.setenv("NUTRITION_ENGINE_V2_SHADOW", "true")
    _nutrition_env(monkeypatch, dispatch_spy=lambda *a, **k: True)
    on = [e for e in _events(client.post("/chat", json={"message": "give me a full day menu", "lang": "en", "voice": True, "profile": {}}))]
    assert [e for e in on if "speech_text" in e] == [e for e in base if "speech_text" in e]
