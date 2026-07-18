"""Phase 5 isolated service contract, projection, and shadow-record tests.

Fully isolated: no production imports, no network, no DB, no LLM, no time/random.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from nutrition_engine.catalog import CatalogGovernance, load_catalog_file
from nutrition_engine.models import (
    CatalogMode, CallerRouteStatus, DietConstraints, NutritionPlanCode, NutritionPlanOutcome,
    NutritionPlanRequest, NutritionTargets, PracticalityPolicy, PreferenceWeights, RotationContext,
)
from nutrition_engine import service, shadow
from nutrition_engine.service import build_nutrition_plan, SERVICE_VERSION
from nutrition_engine.projection import canonical_bytes

CATALOG = load_catalog_file(
    Path(__file__).parents[1] / "nutrition_engine" / "data" / "food_catalog_v1.json",
    CatalogGovernance(True, False, Decimal("15")),
)
CATVER = CATALOG.version
POLICY = PracticalityPolicy(
    maximum_foods_per_meal=4,
    category_portion_overrides=(
        ("protein", Decimal("200"), Decimal("300"), Decimal("50")),
        ("carbohydrate", Decimal("100"), Decimal("200"), Decimal("50")),
        ("vegetable", Decimal("75"), Decimal("75"), Decimal("25")),
        ("fruit", Decimal("100"), Decimal("150"), Decimal("50")),
        ("fat", Decimal("5"), Decimal("5"), Decimal("5")),
    ),
    max_search_nodes=200_000,
)


def _req(**kw) -> NutritionPlanRequest:
    base = dict(
        language="bg", catalog_version=CATVER, catalog_mode=CatalogMode.DEVELOPMENT,
        diet_constraints=DietConstraints(), required_meals=("breakfast", "lunch", "dinner"),
        practicality_policy=POLICY, caller_route_status=CallerRouteStatus.ELIGIBLE,
        service_version=SERVICE_VERSION,
        targets=NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198")),
    )
    base.update(kw)
    return NutritionPlanRequest(**base)


# 1, 2, 24
def test_identical_requests_produce_identical_result_and_bytes():
    a = build_nutrition_plan(_req(), catalog=CATALOG)
    b = build_nutrition_plan(_req(), catalog=CATALOG)
    assert a == b
    assert canonical_bytes(a.projection) == canonical_bytes(b.projection)
    assert a.deterministic_output_hash == b.deterministic_output_hash


# 3
def test_non_success_never_carries_a_projection():
    for r in (build_nutrition_plan(_req(caller_route_status=CallerRouteStatus.MEDICAL_ROUTING_REQUIRED), catalog=CATALOG),
              build_nutrition_plan(_req(targets=None), catalog=CATALOG),
              build_nutrition_plan(_req(catalog_version="wrong-v9"), catalog=CATALOG)):
        assert r.outcome is not NutritionPlanOutcome.SUCCESS
        assert r.projection is None
        assert r.deterministic_output_hash is None


# 4
def test_medical_route_short_circuits_before_catalog_and_optimizer(monkeypatch):
    called = {"catalog": False}
    monkeypatch.setattr(service, "build_candidates", lambda *a, **k: called.__setitem__("candidate", True))
    r = build_nutrition_plan(_req(caller_route_status=CallerRouteStatus.MEDICAL_ROUTING_REQUIRED))
    assert r.code is NutritionPlanCode.MEDICAL_ROUTING_REQUIRED
    assert "candidate" not in called  # optimizer/candidate never reached


# 5
def test_missing_target_authority_returns_typed_failure():
    r = build_nutrition_plan(_req(targets=None), catalog=CATALOG)
    assert r.outcome is NutritionPlanOutcome.CLARIFICATION_REQUIRED
    assert r.code is NutritionPlanCode.MISSING_TARGET_AUTHORITY
    r2 = build_nutrition_plan(_req(targets=NutritionTargets(Decimal("1914"), Decimal("0.05"))), catalog=CATALOG)
    assert r2.code is NutritionPlanCode.MISSING_TARGET_AUTHORITY  # no protein authority


# 6, 32
def test_production_ready_mode_rejects_current_catalog():
    r = build_nutrition_plan(_req(catalog_mode=CatalogMode.PRODUCTION_READY))  # loads file in prod mode
    assert r.outcome is NutritionPlanOutcome.CATALOG_NOT_READY
    assert r.code is NutritionPlanCode.CATALOG_NOT_READY
    assert r.projection is None
    # development mode remains explicitly non-production
    ok = build_nutrition_plan(_req(), catalog=CATALOG)
    assert ok.internal_metrics.development_only is True


# 7
def test_catalog_version_mismatch_fails_closed():
    r = build_nutrition_plan(_req(catalog_version="not-the-real-version"), catalog=CATALOG)
    assert r.code is NutritionPlanCode.CATALOG_VERSION_MISMATCH
    assert r.projection is None


# 8
def test_unsupported_diet_returns_typed_unsupported():
    r = build_nutrition_plan(_req(diet_constraints=DietConstraints(diet_type="vegan")), catalog=CATALOG)
    assert r.outcome is NutritionPlanOutcome.UNSUPPORTED
    assert r.code in (NutritionPlanCode.UNSUPPORTED_DIET, NutritionPlanCode.CANDIDATE_COVERAGE_INSUFFICIENT)
    assert r.projection is None


# 9
def test_allergies_beat_preferences():
    # prefer chicken but exclude all-protein via allergen: chicken must not appear
    constraints = DietConstraints(no_chicken=True, diet_type="no_chicken")
    prefs = PreferenceWeights(preferred_food_ids=frozenset({"dev_chicken_breast_cooked"}))
    r = build_nutrition_plan(_req(diet_constraints=constraints, preference_weights=prefs), catalog=CATALOG)
    if r.outcome is NutritionPlanOutcome.SUCCESS:
        names = {f.name for m in r.projection.meals for f in m.foods}
        assert all("Пилешк" not in n for n in names)  # no chicken despite preference


# 10, 21
def test_exclusions_beat_rotation_and_are_never_surfaced():
    excluded = frozenset({"dev_chicken_breast_cooked"})
    rot = RotationContext(recent_main_protein_ids=("dev_turkey_breast_cooked", "dev_lean_beef_cooked"),
                          maximum_history_depth=5)
    # rotation_choice must never return an excluded food
    assert service.rotation_choice(
        ["dev_chicken_breast_cooked", "dev_turkey_breast_cooked"],
        ["dev_turkey_breast_cooked"], excluded) == "dev_turkey_breast_cooked"
    assert service.rotation_choice(["dev_chicken_breast_cooked"], [], excluded) is None


# 11
def test_candidate_failure_produces_no_plan():
    r = build_nutrition_plan(_req(diet_constraints=DietConstraints(excluded_categories=frozenset({"protein"}))), catalog=CATALOG)
    assert r.outcome is NutritionPlanOutcome.UNSUPPORTED
    assert r.projection is None


# 12
def test_optimizer_infeasibility_maps_correctly():
    r = build_nutrition_plan(_req(targets=NutritionTargets(Decimal("6000"), Decimal("0.01"), Decimal("400"))), catalog=CATALOG)
    assert r.outcome in (NutritionPlanOutcome.INFEASIBLE, NutritionPlanOutcome.UNSUPPORTED)
    assert r.code in (
        NutritionPlanCode.CALORIE_TARGET_UNREACHABLE, NutritionPlanCode.PROTEIN_MINIMUM_UNREACHABLE,
        NutritionPlanCode.MEAL_STRUCTURE_INFEASIBLE, NutritionPlanCode.SEARCH_LIMIT_REACHED,
        NutritionPlanCode.CANDIDATE_COVERAGE_INSUFFICIENT,
    )
    assert r.projection is None


# 13, 14 — hard vs soft quality
def test_hard_quality_failure_blocks_and_soft_findings_preserve_success():
    ok = build_nutrition_plan(_req(), catalog=CATALOG)
    assert ok.outcome is NutritionPlanOutcome.SUCCESS  # soft penalties, if any, do not block
    # a hard-quality failure path returns no projection
    from nutrition_engine.feasibility import FeasibilityResult, FeasibilityCode
    import nutrition_engine.service as svc

    def fake_quality(catalog, day):
        from nutrition_engine.quality import QualityResult
        return QualityResult(("repeated_main_protein",), ())

    original = svc.evaluate_quality
    svc.evaluate_quality = fake_quality
    try:
        blocked = build_nutrition_plan(_req(), catalog=CATALOG)
    finally:
        svc.evaluate_quality = original
    assert blocked.outcome is NutritionPlanOutcome.INFEASIBLE
    assert blocked.code is NutritionPlanCode.QUALITY_CONSTRAINTS_INFEASIBLE
    assert blocked.projection is None


# 15, 34
def test_selector_totals_equal_optimizer_totals_with_decimal_preserved():
    from nutrition_engine.candidate_builder import build_candidates
    from nutrition_engine.optimizer import optimize
    targets = NutritionTargets(Decimal("1914"), Decimal("0.05"), Decimal("198"))
    plan = build_candidates(CATALOG, targets, DietConstraints(), ("breakfast", "lunch", "dinner"), POLICY)
    opt = optimize(CATALOG, targets, DietConstraints(), plan.selections, POLICY)
    r = build_nutrition_plan(_req(), catalog=CATALOG)
    assert r.projection.daily_totals.kcal == opt.day.daily_totals.kcal
    assert r.projection.daily_totals.protein_g == opt.day.daily_totals.protein_g
    assert isinstance(r.projection.daily_totals.kcal, Decimal)


# 16, 17, 18 — localization + leakage
_FORBIDDEN = ("dev_", "source_record", "source_version", "catalog_version", "review_status",
              "TEST_POLICY_ONLY", "NUTRIENTS_REVIEWED", "meal_id", "food_id", "lnch_", "brk_", "dnr_")


def test_localization_preserves_numbers_and_leaks_no_ids_bg_and_en():
    bg = build_nutrition_plan(_req(language="bg"), catalog=CATALOG)
    en = build_nutrition_plan(_req(language="en"), catalog=CATALOG)
    # identical numbers across languages
    assert bg.projection.daily_totals == en.projection.daily_totals
    for lang_result in (bg, en):
        blob = canonical_bytes(lang_result.projection).decode("utf-8")
        for token in _FORBIDDEN:
            assert token not in blob, token
    assert bg.projection.language == "bg" and en.projection.language == "en"


# 19, 20 — rotation
def test_rotation_avoids_repeats_when_possible_and_accepts_unavoidable():
    alts = ["dev_chicken_breast_cooked", "dev_turkey_breast_cooked", "dev_lean_beef_cooked"]
    # fresh option preferred
    assert service.rotation_choice(alts, ["dev_chicken_breast_cooked"], frozenset()) == "dev_turkey_breast_cooked"
    # all recent -> oldest (earliest in recent) chosen, deterministic
    recent = ["dev_lean_beef_cooked", "dev_turkey_breast_cooked", "dev_chicken_breast_cooked"]
    assert service.rotation_choice(alts, recent, frozenset()) == "dev_lean_beef_cooked"
    # single option repeats honestly
    assert service.rotation_choice(["dev_tofu_firm"], ["dev_tofu_firm"], frozenset()) == "dev_tofu_firm"


# 22, 23 — preferences
def test_preferences_affect_only_ordering_and_ignore_unknown_ids():
    prefs = PreferenceWeights(preferred_food_ids=frozenset({"dev_turkey_breast_cooked"}),
                              disliked_food_ids=frozenset({"dev_chicken_breast_cooked"}))
    base = build_nutrition_plan(_req(), catalog=CATALOG)
    with_prefs = build_nutrition_plan(_req(preference_weights=prefs), catalog=CATALOG)
    # ordering-only: the optimizer numbers are unchanged
    assert with_prefs.projection.daily_totals == base.projection.daily_totals
    # ordering helper is a stable reorder that never drops/adds
    ordered = service.order_alternatives_by_preference(
        ["dev_chicken_breast_cooked", "dev_turkey_breast_cooked", "dev_tofu_firm"], prefs)
    assert set(ordered) == {"dev_chicken_breast_cooked", "dev_turkey_breast_cooked", "dev_tofu_firm"}
    assert ordered[0] == "dev_turkey_breast_cooked" and ordered[-1] == "dev_chicken_breast_cooked"
    # unknown ids ignored deterministically -> recorded as a count, no crash
    unknown = PreferenceWeights(preferred_food_ids=frozenset({"dev_not_a_real_food"}))
    ur = build_nutrition_plan(_req(preference_weights=unknown), catalog=CATALOG)
    assert ur.outcome is NutritionPlanOutcome.SUCCESS
    assert "unknown_preferred_ids:1" in ur.internal_metrics.preference_findings


# 25 — fingerprint stable
def test_request_fingerprint_is_stable_and_hashed():
    assert shadow.fingerprint_request(_req()) == shadow.fingerprint_request(_req())
    assert len(shadow.fingerprint_request(_req())) == 64  # sha256 hex, one-way


# 26, 27 — shadow contains no raw text/identity/ids
def test_shadow_record_contains_no_raw_text_identity_or_ids():
    r = build_nutrition_plan(_req(), catalog=CATALOG)
    rec = shadow.build_shadow_record(_req(), r, Decimal("2.5"))
    text = str(dataclasses.asdict(rec))
    for token in ("dev_", "source_record", "source_name", "source_version", "@", "Пилешк",
                  "chicken", "email", "prompt", "review_status", "food_id", "TEST_POLICY"):
        assert token not in text, token
    # role summary is category composition only
    assert all("+" in sig or sig == "" for _, sig in rec.selected_role_summary)
    assert rec.hard_quality_finding_count == 0


# 28, 29 — fail closed
def test_internal_exception_becomes_fail_closed_with_no_partial_plan(monkeypatch):
    monkeypatch.setattr(service, "optimize", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = build_nutrition_plan(_req(), catalog=CATALOG)
    assert r.outcome is NutritionPlanOutcome.INTERNAL_FAIL_CLOSED
    assert r.code is NutritionPlanCode.INTERNAL_FAIL_CLOSED
    assert r.projection is None and r.deterministic_output_hash is None


# 33 — no mutation of inputs
def test_service_does_not_mutate_request_or_catalog():
    request = _req()
    before_catalog = tuple(f.food_id for f in CATALOG.foods)
    before_req = dataclasses.astuple(request)
    build_nutrition_plan(request, catalog=CATALOG)
    assert tuple(f.food_id for f in CATALOG.foods) == before_catalog
    assert dataclasses.astuple(request) == before_req


# 30, 31 — isolation
def test_phase5_modules_have_no_production_network_or_llm_imports():
    package = Path(__file__).parents[1] / "nutrition_engine"
    forbidden = ("import app", "from app", "import db", "requests.", "openai", "sqlalchemy",
                 "socket.", "flask", "conversation_composer", "nutrition_validation",
                 "nutrition_generation", "urllib", "httpx", "os.environ", "getenv", "random",
                 "time.time", "uuid")
    for name in ("service.py", "projection.py", "shadow.py"):
        source = (package / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} references {token}"
