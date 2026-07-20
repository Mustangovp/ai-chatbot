"""
M6 Recommendation Architecture — the layer downstream of the frozen Brain.
Covers: preference parsing + persistence, the Architect's deterministic blueprint
design, explainability, diversity rotation, and the render-only LLM prompt.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import recommend
from context_builder import Subject, build_context
from recommend import architect, preferences, diversity, renderer
from recommend.blueprint import to_dict
from knowledge import KnowledgeDomain, KnowledgeResolver, load_default_registry, load_registry_file
from brain import cascade
from brain.types import (Decision, Verdict, Intervention, S2State, ConstraintSet,
                         Constraint, ConstraintTier, CapacityEnvelope)
from recommend.engine import (
    ImmutableUserProfile, ProfileCompleteness, RecommendationEngine, RecommendationIntent,
    RecommendationOutcome, clarification_history, clarification_message,
)


def _decision(verdict=Verdict.MODIFY, intervention="training", constraints=(),
              intensity=0.5, supported=False, halt=False):
    cs = ConstraintSet()
    for m in constraints:
        cs.add(Constraint(m, ConstraintTier.RELATIVE, "hypertension_valsalva"))
    return Decision(
        verdict=verdict, intervention=Intervention(intervention, "k"), generate_training=True,
        halt=halt, verdict_confidence=0.5, constraints=cs,
        envelope=CapacityEnvelope(intensity, intensity, intensity, supported, 0.6),
        s2=S2State(readiness=0.6, readiness_conf=0.6, red_flags=[], halt=halt),
        need_vector=[], decision_id="d", model=None)


# ── Preference Engine ────────────────────────────────────────────────────────
def test_parse_preferences_from_language():
    assert "oats" in preferences.parse_updates("honestly I hate oats")["avoid"]
    assert "eggs" in preferences.parse_updates("I love eggs")["prefer"]
    assert preferences.parse_updates("I only have 10 minutes")["breakfast_time"] == 10
    assert preferences.parse_updates("I don't cook")["cooking"] == "minimal"
    assert preferences.parse_updates("what's the weather") == {}


def test_preferences_persist_and_conflict_resolve():
    subj = "device:pref1"
    preferences.update_from_message(subj, "I love eggs")
    p = preferences.update_from_message(subj, "actually I hate eggs now")
    assert "eggs" in p["avoid"] and "eggs" not in p["prefer"]      # dislike overrides like
    assert preferences.load(subj)["avoid"] == ["eggs"]            # persisted


# ── Architect: deterministic values + explainability ─────────────────────────
def test_workout_blueprint_from_constrained_decision():
    d = _decision(verdict=Verdict.MODIFY, intervention="training",
                  constraints=["valsalva", "high_impact"], intensity=0.35, supported=True)
    bp = architect.design(decision=d, profile={"goal": "strength", "equipment": ["dumbbells"]},
                          preferences={}, subject="device:w1")
    assert bp.kind == "workout" and bp.difficulty == "beginner"
    assert "valsalva" in bp.contraindications and "high_impact" in bp.contraindications
    assert bp.balance_demand == "supported" and bp.joint_impact == "low"
    whys = {c: b for c, b in bp.explanations}
    assert "Balance-supported" in whys and any("Avoid" in c for c in whys)


def test_nutrition_blueprint_reflects_goal_and_prefs():
    prefs = {"avoid": ["oats"], "prefer": ["eggs"], "breakfast_time": 10, "cooking": "minimal"}
    bp = architect.design("nutrition", decision=_decision(intervention="nutrition"),
                          profile={"goal": "muscle_gain"}, preferences=prefs, subject="device:n1")
    assert bp.protein_g >= 45 and bp.max_prep_minutes == 10 and bp.difficulty == "no-cook"
    assert bp.avoided_foods == ["oats"] and bp.preferred_foods == ["eggs"]
    whys = {c: b for c, b in bp.explanations}
    assert whys.get("High protein") == "muscle gain"
    assert whys.get("Quick breakfast") == "user has 10 minutes"
    assert whys.get("No oats") == "preference"


def test_route_decision_designs_nothing():
    d = _decision(intervention="medical_followup", halt=True)
    assert architect.design(decision=d, profile={}, preferences={}, subject="device:r1") is None


# ── Diversity rotation ───────────────────────────────────────────────────────
def test_diversity_rotates_and_avoids_recent():
    subj = "device:div1"
    seen = []
    for _ in range(4):
        a, _rec = diversity.next_anchor(subj, "nutrition")
        seen.append(a)
    assert len(set(seen)) == 4                                    # no repeats across a short run


def test_diversity_respects_avoided_food_anchor():
    subj = "device:div2"
    a, _ = diversity.next_anchor(subj, "nutrition", avoid=["eggs"])
    assert a != "eggs"


# ── Renderer: render-only, values preserved ──────────────────────────────────
def test_render_prompt_is_render_only_and_contains_values():
    bp = architect.design("nutrition", decision=_decision(intervention="nutrition"),
                          profile={"goal": "muscle_gain"}, preferences={"avoid": ["oats"]},
                          subject="device:rp1")
    prompt = renderer.render_prompt(bp)
    assert "renderer, not a decider" in prompt and "Do NOT change any number" in prompt
    payload = json.loads(prompt.split("do not alter values):", 1)[1])
    assert payload["protein_g"] == bp.protein_g and payload["avoided_foods"] == ["oats"]


# ── End-to-end pipeline + real cascade Decision ──────────────────────────────
def test_pipeline_plan_updates_prefs_and_designs():
    out = recommend.plan(decision=_decision(intervention="nutrition"), profile={"goal": "weight_loss"},
                         subject="device:e2e", message="I hate oats and only have 5 minutes")
    assert out["kind"] == "nutrition"
    assert "oats" in out["preferences"]["avoid"] and out["preferences"]["breakfast_time"] == 5
    assert out["blueprint_dict"]["max_prep_minutes"] == 5
    assert out["prompt"] and "BLUEPRINT" in out["prompt"]


def test_pipeline_over_a_real_cascade_decision():
    d = cascade.decide({"goal": "strength", "healthNotes": "high blood pressure"},
                       message="give me a workout")
    out = recommend.plan(decision=d, kind="workout", profile={"goal": "strength"}, subject="device:live")
    assert out["kind"] == "workout"
    # the Brain's hypertension constraints propagate into the blueprint contraindications
    assert out["blueprint"].contraindications and out["blueprint"].kind == "workout"


# ── Knowledge System foundation: immutable registry + inert DI seam ──────────
def test_knowledge_registry_is_complete_versioned_and_source_traceable():
    registry = load_default_registry()
    assert registry.version == "apex-knowledge-registry-v1"
    assert {document.domain for document in registry.documents} == set(KnowledgeDomain)
    assert {document.document_id for document in registry.documents} == {
        "training.minimum-effective-dose.v1",
        "nutrition.energy-first.v1",
        "recovery.recoverable-load.v1",
        "supplementation.unavailable.v1",
    }


def test_knowledge_resolver_is_deterministic_domain_separated_and_read_only():
    resolver = KnowledgeResolver(load_default_registry())
    training = resolver.resolve(KnowledgeDomain.TRAINING, tags=("progression",))
    repeated = resolver.resolve("training", tags=("progression",))
    nutrition = resolver.resolve("nutrition")
    supplementation = resolver.resolve("supplementation")

    assert training == repeated
    assert [document.domain for document in training.documents] == [KnowledgeDomain.TRAINING]
    assert [document.domain for document in nutrition.documents] == [KnowledgeDomain.NUTRITION]
    assert supplementation.domain_available is False and supplementation.documents == ()


def test_knowledge_loader_fails_closed_for_invalid_provenance_and_duplicate_identity(tmp_path):
    source = Path(__file__).resolve().parents[1] / "knowledge" / "data" / "registry-v1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["documents"][0]["source_document"] = "docs/research/missing.md"
    broken_source = tmp_path / "broken-source.json"
    broken_source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source is unavailable"):
        load_registry_file(broken_source)

    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["documents"][1]["document_id"] = payload["documents"][0]["document_id"]
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate knowledge document"):
        load_registry_file(duplicate)


def test_knowledge_resolver_is_injected_without_changing_blueprint_values():
    class ResolverSpy:
        def __init__(self):
            self.kinds = []
            self.delegate = KnowledgeResolver(load_default_registry())

        def resolve_for_recommendation(self, kind):
            self.kinds.append(kind)
            return self.delegate.resolve_for_recommendation(kind)

    decision = _decision(intervention="training")
    baseline = architect.design("workout", decision=decision, profile={"goal": "strength"},
                                preferences={}, subject="device:knowledge", record=False)
    spy = ResolverSpy()
    injected = architect.design("workout", decision=decision, profile={"goal": "strength"},
                                preferences={}, subject="device:knowledge", record=False,
                                knowledge_resolver=spy)

    assert spy.kinds == ["workout"]
    assert to_dict(injected) == to_dict(baseline)


def test_knowledge_resolver_reaches_the_recommendation_pipeline_without_output_change():
    class ResolverSpy:
        def __init__(self):
            self.kinds = []

        def resolve_for_recommendation(self, kind):
            self.kinds.append(kind)

    spy = ResolverSpy()
    output = recommend.plan(decision=_decision(intervention="nutrition"), kind="nutrition",
                            profile={"goal": "weight_loss"}, subject="device:knowledge-pipeline",
                            knowledge_resolver=spy)

    assert spy.kinds == ["nutrition"]
    assert output["blueprint"].kind == "nutrition"


# ── Recommendation Engine V1: deterministic planning before prompt generation ─
def _recommendation_engine():
    return RecommendationEngine(KnowledgeResolver(load_default_registry()))


def test_recommendation_engine_produces_a_deterministic_blueprint_for_sufficient_profile():
    profile = ImmutableUserProfile.from_verified_facts({
        "goal": "strength", "equipment": "gym", "level": "intermediate",
    })
    engine = _recommendation_engine()
    first = engine.plan(RecommendationIntent.WORKOUT, profile)
    second = engine.plan("workout", profile)

    assert first == second
    assert first.outcome is RecommendationOutcome.RECOMMEND
    assert first.profile_completeness is ProfileCompleteness.SUFFICIENT
    assert first.knowledge_document_ids == ("training.minimum-effective-dose.v1",)
    assert {reason.source for reason in first.reasons} == {"profile", "knowledge"}


def test_recommendation_engine_preserves_the_verified_training_split():
    blueprint = _recommendation_engine().plan("workout", ImmutableUserProfile.from_verified_facts({
        "goal": "strength", "equipment": "gym", "level": "intermediate",
        "training_split": "push_pull_legs",
    }))

    assert blueprint.outcome is RecommendationOutcome.RECOMMEND
    assert blueprint.training_split == "push_pull_legs"


def test_recommendation_engine_normalizes_unordered_verified_profile_values_deterministically():
    engine = _recommendation_engine()
    first = engine.plan("workout", ImmutableUserProfile.from_verified_facts({
        "goal": "strength", "equipment": {"gym"}, "level": "intermediate",
    }))
    second = engine.plan("workout", ImmutableUserProfile.from_verified_facts({
        "goal": "strength", "equipment": {"gym"}, "level": "intermediate",
    }))

    assert first.blueprint_id == second.blueprint_id


def test_recommendation_engine_uses_only_missing_verified_fields_for_one_clarification():
    engine = _recommendation_engine()
    profile = ImmutableUserProfile.from_verified_facts({"goal": "strength", "equipment": "gym"})
    blueprint = engine.plan("workout", profile)

    assert blueprint.outcome is RecommendationOutcome.CLARIFY
    assert blueprint.profile_completeness is ProfileCompleteness.INCOMPLETE
    assert blueprint.missing_fields == ("level",)
    assert blueprint.clarification_field == "level"


def test_recommendation_engine_never_repeats_a_clarification_for_the_same_missing_field():
    engine = _recommendation_engine()
    profile = ImmutableUserProfile.from_verified_facts(
        {"goal": "strength", "equipment": "gym"}, clarification_history=("level",))
    blueprint = engine.plan("workout", profile)

    assert blueprint.outcome is RecommendationOutcome.AWAITING_PROFILE
    assert blueprint.clarification_field is None
    assert blueprint.missing_fields == ("level",)


def test_recommendation_engine_detects_conflicting_verified_profile_aliases():
    engine = _recommendation_engine()
    profile = ImmutableUserProfile.from_verified_facts({
        "goal": "strength", "equipment": "gym", "level": "beginner", "experience_level": "advanced",
    })
    blueprint = engine.plan("workout", profile)

    assert blueprint.outcome is RecommendationOutcome.CLARIFY
    assert blueprint.profile_completeness is ProfileCompleteness.CONFLICTING
    assert blueprint.conflict_fields == ("experience_level",)
    assert blueprint.clarification_field == "experience_level"


def test_recommendation_engine_uses_nutrition_knowledge_without_prompt_or_engine_changes():
    engine = _recommendation_engine()
    blueprint = engine.plan("nutrition", ImmutableUserProfile.from_verified_facts({
        "age": "30", "height": "180", "weight": "80", "goal": "fat_loss",
    }))

    assert blueprint.outcome is RecommendationOutcome.RECOMMEND
    assert blueprint.knowledge_document_ids == ("nutrition.energy-first.v1",)


def test_nutrition_profile_completeness_requests_only_the_one_missing_verified_card():
    engine = _recommendation_engine()
    blueprint = engine.plan("nutrition", ImmutableUserProfile.from_verified_facts({
        "age": "30", "height": "180", "goal": "fat_loss",
    }))

    assert blueprint.outcome is RecommendationOutcome.CLARIFY
    assert blueprint.missing_fields == ("weight",)
    assert blueprint.clarification_field == "weight"


def test_clarification_history_prevents_the_same_field_from_being_requested_twice():
    history = [{"role": "assistant", "content": clarification_message("weight", "en")}]
    profile = ImmutableUserProfile.from_verified_facts(
        {"age": "30", "height": "180", "goal": "fat_loss"},
        clarification_history=clarification_history(history, "en"),
    )
    blueprint = _recommendation_engine().plan("nutrition", profile)

    assert blueprint.outcome is RecommendationOutcome.AWAITING_PROFILE
    assert blueprint.clarification_field is None


def test_recommendation_engine_marks_unavailable_domains_without_inventing_guidance():
    engine = _recommendation_engine()
    blueprint = engine.plan("supplementation", ImmutableUserProfile.from_verified_facts({}))

    assert blueprint.outcome is RecommendationOutcome.UNAVAILABLE
    assert blueprint.knowledge_document_ids == ()
    assert blueprint.reasons[0].code == "knowledge_unavailable"


def test_recommendation_engine_accepts_immutable_context_snapshot_facts_without_chat_wiring():
    snapshot = build_context(
        intent="workout", subject=Subject("account", "recommendation-test", True),
        request_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        db_profile={"goal": "strength", "equipment": "gym", "level": "intermediate"},
    )
    profile = ImmutableUserProfile.from_verified_facts(
        snapshot.profile, locked_preferences=snapshot.locked_preferences.as_dict())
    blueprint = _recommendation_engine().plan("workout", profile)

    assert blueprint.outcome is RecommendationOutcome.RECOMMEND
    assert blueprint.profile_completeness is ProfileCompleteness.SUFFICIENT


def test_recommendation_pipeline_generates_the_planning_blueprint_before_its_prompt():
    engine = _recommendation_engine()
    profile = ImmutableUserProfile.from_verified_facts({
        "goal": "strength", "equipment": "gym", "level": "intermediate",
    })
    output = recommend.plan(
        decision=_decision(intervention="training"), kind="workout", profile=dict(profile.facts),
        subject="device:planned", recommendation_engine=engine, immutable_profile=profile,
    )

    assert output["recommendation_blueprint"].outcome is RecommendationOutcome.RECOMMEND
    assert output["blueprint"].kind == "workout"
    assert output["prompt"]


def test_recommendation_pipeline_does_not_generate_a_prompt_for_incomplete_profile(monkeypatch):
    engine = _recommendation_engine()
    profile = ImmutableUserProfile.from_verified_facts({"goal": "strength", "equipment": "gym"})
    monkeypatch.setattr(architect, "design", lambda *args, **kwargs: pytest.fail("architect must not run"))

    output = recommend.plan(
        decision=_decision(intervention="training"), kind="workout", profile=dict(profile.facts),
        subject="device:incomplete", recommendation_engine=engine, immutable_profile=profile,
    )

    assert output["recommendation_blueprint"].outcome is RecommendationOutcome.CLARIFY
    assert output["blueprint"] is None and output["prompt"] is None
