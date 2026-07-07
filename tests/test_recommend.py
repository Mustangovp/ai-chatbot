"""
M6 Recommendation Architecture — the layer downstream of the frozen Brain.
Covers: preference parsing + persistence, the Architect's deterministic blueprint
design, explainability, diversity rotation, and the render-only LLM prompt.
"""
import json

import recommend
from recommend import architect, preferences, diversity, renderer
from recommend.blueprint import to_dict
from brain import cascade
from brain.types import (Decision, Verdict, Intervention, S2State, ConstraintSet,
                         Constraint, ConstraintTier, CapacityEnvelope)


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
