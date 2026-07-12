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
    "Return exactly one JSON object with only two keys: `blueprint` and `explanations`. "
    "`blueprint` must be an exact copy of the supplied BLUEPRINT. `explanations` must be a "
    "subset of the exact explanation objects already in the supplied BLUEPRINT. Do not add prose "
    "or any new recommendation content."
)


def render_prompt(blueprint) -> str:
    """The system-prompt addendum that turns the blueprint into natural language."""
    payload = to_dict(blueprint)
    return _RENDER_RULES + "\n\nBLUEPRINT (render exactly, do not alter values):\n" + \
        json.dumps(payload, ensure_ascii=False, indent=2)


def verified_explanations(response: str, blueprint) -> list[dict]:
    """Return only explanation entries already present in an unchanged blueprint."""
    payload = json.loads(str(response or ""))
    if set(payload) != {"blueprint", "explanations"}:
        raise ValueError("unexpected recommendation response contract")
    if payload["blueprint"] != to_dict(blueprint):
        raise ValueError("recommendation blueprint changed by LLM")
    explanations = payload["explanations"]
    if not isinstance(explanations, list):
        raise ValueError("invalid recommendation explanations")
    allowed = to_dict(blueprint)["explanations"]
    if any(item not in allowed for item in explanations):
        raise ValueError("recommendation explanation changed by LLM")
    return explanations


def render_delivery(blueprint, explanations: list[dict], lang: str) -> str:
    """Present only blueprint values and verified blueprint explanations."""
    english = str(lang).lower() == "en"
    if blueprint.kind == "workout":
        title = "Workout" if english else "Тренировка"
        labels = ("Goal", "Difficulty", "Duration", "Equipment", "Focus", "Avoid") if english else \
                 ("Цел", "Ниво", "Продължителност", "Оборудване", "Фокус", "Избягвай")
        values = (
            blueprint.goal,
            blueprint.difficulty,
            f"{blueprint.session_minutes} min",
            ", ".join(blueprint.equipment),
            ", ".join(blueprint.exercise_families),
            ", ".join(blueprint.contraindications) or ("None" if english else "Няма"),
        )
    else:
        title = "Nutrition" if english else "Хранене"
        labels = ("Meal", "Protein", "Carbs", "Fat", "Fiber", "Preparation", "Avoid") if english else \
                 ("Хранене", "Протеин", "Въглехидрати", "Мазнини", "Фибри", "Приготвяне", "Избягвай")
        values = (
            blueprint.meal,
            f"{blueprint.protein_g} g",
            f"{blueprint.carbs_g} g",
            f"{blueprint.fat_g} g",
            f"{blueprint.fiber_g} g",
            f"{blueprint.max_prep_minutes} min",
            ", ".join(blueprint.avoided_foods) or ("None" if english else "Няма"),
        )
    details = "\n".join(f"- **{label}:** {value}" for label, value in zip(labels, values))
    why = "\n".join(f"- {item['claim']}: {item['because']}" for item in explanations)
    return f"**{title}**\n{details}" + (f"\n\n{why}" if why else "")
