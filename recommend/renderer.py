"""
APEX M6 — LLM Renderer.

Transforms a finished Blueprint into a SYSTEM instruction that constrains the LLM
to PHRASE the blueprint, never to decide it. The renderer does not call any LLM —
it returns the prompt; the app wires it into the existing generation call. Pure.
"""
import json

from recommend.blueprint import to_dict

_RENDER_RULES = (
    "You are APEX's voice. You are given a FIXED recommendation blueprint that was "
    "already decided for this person. Your ONLY job is to phrase it as a warm, concise "
    "coach message.\n"
    "HARD RULES — you are a renderer, not a decider:\n"
    "  • Do NOT change any number (macros, minutes, durations, targets).\n"
    "  • Do NOT add foods/exercises that contradict avoided_foods or contraindications.\n"
    "  • Do NOT remove or soften any medical_constraints / contraindications.\n"
    "  • Build the meal/session around the given rotation_anchor; do NOT reuse anything "
    "in meal_diversity (those are recent — keep it fresh).\n"
    "  • Honor preferred_foods and equipment; respect max_prep_minutes / session_minutes.\n"
    "  • Briefly weave in the 'why' from explanations so the person understands the plan.\n"
    "  • No diagnosis, no medication advice. If medical_constraints say defer to care, say so kindly.\n"
    "Return only the coach message."
)


def render_prompt(blueprint) -> str:
    """The system-prompt addendum that turns the blueprint into natural language."""
    payload = to_dict(blueprint)
    return _RENDER_RULES + "\n\nBLUEPRINT (render exactly, do not alter values):\n" + \
        json.dumps(payload, ensure_ascii=False, indent=2)
