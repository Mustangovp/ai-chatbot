"""
APEX M6 — Recommendation Architecture Engine.

Pipeline:  Brain Decision  →  Recommendation Architect  →  Blueprint  →  LLM Renderer

APEX stops generating recommendations directly. It DESIGNS them first (the
Architect decides every value, deterministically, with explanations), then the
LLM only phrases the blueprint. A persistent Preference Engine and a diversity
rotation shape the blueprint. This layer sits ENTIRELY downstream of the Brain —
it never modifies S1–S5, the cascade, or enforcement.
"""
from recommend import architect, preferences, diversity, renderer
from recommend.blueprint import to_dict, NutritionBlueprint, WorkoutBlueprint, RecoveryBlueprint

__all__ = ["plan", "architect", "preferences", "diversity", "renderer", "to_dict",
           "NutritionBlueprint", "WorkoutBlueprint", "RecoveryBlueprint"]


def plan(*, decision=None, kind=None, profile=None, subject="anon", message=None):
    """Run the full pipeline for one turn.

    1. update persistent preferences from the message (if any),
    2. design a blueprint (Architect decides every value),
    3. produce the render-only LLM prompt.

    Returns {blueprint, blueprint_dict, prompt, preferences, kind} — or a dict with
    blueprint=None when the decision routes/asks (nothing to design)."""
    prefs = preferences.update_from_message(subject, message) if message is not None \
        else preferences.load(subject)
    bp = architect.design(kind, decision=decision, profile=profile, preferences=prefs, subject=subject)
    if bp is None:
        return {"blueprint": None, "blueprint_dict": None, "prompt": None,
                "preferences": prefs, "kind": None}
    return {"blueprint": bp, "blueprint_dict": to_dict(bp), "prompt": renderer.render_prompt(bp),
            "preferences": prefs, "kind": bp.kind}
