"""
APEX M6 — the Recommendation Architect.

Given a (frozen) Brain Decision + profile + persistent preferences, it DESIGNS a
structured Blueprint: every value is decided here, deterministically, with an
explanation. It READS the Brain Decision (verdict, intervention, envelope,
constraints) but never modifies it, the cascade, or enforcement. The LLM never
sees these choices as open — only as a blueprint to phrase.
"""
import datetime as _dt
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from recommend import diversity
from recommend.blueprint import NutritionBlueprint, WorkoutBlueprint, RecoveryBlueprint

# Brain intervention.kind -> blueprint kind (None = route/ask, no recommendation designed).
_KIND_FOR = {
    "training": "workout",
    "nutrition": "nutrition",
    "recovery": "recovery", "sleep": "recovery", "walk": "recovery",
    "breathing": "recovery", "mobility": "recovery", "stress_reduction": "recovery",
    "medical_followup": None, "crisis_support": None, "conversation": None,
}


def blueprint_kind_for(decision) -> str | None:
    kind = getattr(getattr(decision, "intervention", None), "kind", None)
    return _KIND_FOR.get(kind, "recovery")


def _season(now=None) -> str:
    m = (now or _dt.datetime.now(_dt.timezone.utc)).month
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}[m]


def _goal(profile) -> str:
    return str((profile or {}).get("goal") or "general_fitness").lower()


# ── Nutrition ────────────────────────────────────────────────────────────────
def _nutrition(decision, profile, prefs, subject, *, record=True) -> NutritionBlueprint:
    goal = _goal(profile)
    protein, carbs, fat, fiber = 30, 40, 15, 8
    ex = []
    if goal in ("muscle_gain", "strength", "muscle", "gain"):
        protein += 15; carbs += 10; ex.append(("High protein", "muscle gain"))
    if goal in ("weight_loss", "fat_loss", "lose_weight", "cut"):
        carbs = max(carbs - 15, 10); fiber += 5; fat = max(fat - 3, 8)
        ex.append(("Higher fiber, lower carbs", "weight loss"))
    try:
        w = float((profile or {}).get("weight") or 0)
        if w > 0:
            protein = max(protein, int(round(0.4 * w)))
    except Exception:
        pass

    prep = prefs.get("breakfast_time") or 15
    if prefs.get("breakfast_time"):
        ex.append(("Quick breakfast", f"user has {prep} minutes"))
    difficulty = "no-cook" if prefs.get("cooking") == "minimal" else "easy"
    if prefs.get("cooking") == "minimal":
        ex.append(("No-cook", "user doesn't cook"))

    avoid = list(prefs.get("avoid") or [])
    prefer = list(prefs.get("prefer") or [])
    for a in avoid:
        ex.append((f"No {a}", "preference"))
    for p in prefer:
        ex.append((f"Prefer {p}", "preference"))

    anchor, recent = diversity.next_anchor(subject, "nutrition", avoid=avoid, record=record)
    medical = ["defer to medical guidance"] if getattr(decision, "halt", False) else []
    return NutritionBlueprint(
        meal="breakfast", protein_g=protein, carbs_g=carbs, fat_g=fat, fiber_g=fiber,
        max_prep_minutes=prep, budget=prefs.get("budget") or "moderate",
        preferred_foods=prefer, avoided_foods=avoid, rotation_anchor=anchor,
        meal_diversity=recent, difficulty=difficulty,
        required_equipment=[] if difficulty == "no-cook" else ["stove"],
        seasonality=_season(), medical_constraints=medical, explanations=ex)


# ── Workout ──────────────────────────────────────────────────────────────────
_FAMILIES = {
    "strength": ["squat", "hinge", "horizontal_push", "horizontal_pull", "carry"],
    "muscle_gain": ["squat", "hinge", "vertical_push", "horizontal_pull", "isolation"],
    "weight_loss": ["full_body", "conditioning", "carry", "core"],
    "endurance": ["conditioning", "single_leg", "core", "mobility"],
    "general_fitness": ["squat", "horizontal_push", "horizontal_pull", "core", "mobility"],
}


@dataclass(frozen=True)
class WorkoutAuthority:
    """Frozen, presentation-free boundaries for one active workout decision."""
    intent: str
    verified_facts: Mapping[str, Any]
    explicit_facts: Mapping[str, Any]
    locked_preferences: Mapping[str, tuple[str, ...]]
    safety_constraints: tuple[str, ...]
    equipment: tuple[str, ...]
    experience: str | None
    recovery_state: str | None
    workout_history: tuple[Mapping[str, Any], ...]

    def __post_init__(self):
        if self.intent != "workout":
            raise ValueError("workout authority requires workout intent")
        object.__setattr__(self, "verified_facts", MappingProxyType(dict(self.verified_facts)))
        object.__setattr__(self, "explicit_facts", MappingProxyType(dict(self.explicit_facts)))
        object.__setattr__(self, "locked_preferences", MappingProxyType(
            {key: tuple(values) for key, values in self.locked_preferences.items()}))
        object.__setattr__(self, "safety_constraints", tuple(self.safety_constraints))
        object.__setattr__(self, "equipment", tuple(self.equipment))
        object.__setattr__(self, "workout_history", tuple(
            MappingProxyType(dict(item)) for item in self.workout_history))


def _workout(decision, profile, prefs, subject, *, record=True, expert_consensus=None,
             persona_adaptation=None, authority: WorkoutAuthority | None = None) -> WorkoutBlueprint:
    goal = str(authority.verified_facts.get("goal") or _goal(profile)).lower() if authority else _goal(profile)
    env = getattr(decision, "envelope", None)
    ic = float(getattr(env, "intensity_ceiling", 0.5)) if env is not None else 0.5
    supported = bool(getattr(env, "supported", False)) if env is not None else False
    verdict = getattr(getattr(decision, "verdict", None), "value", None)

    movements, reasons = [], []
    cons = getattr(decision, "constraints", None)
    if cons is not None:
        for c in getattr(cons, "items", []):
            movements.append(c.movement)
            reasons.append(c.reason_key)

    ex = []
    if ic < 0.4 or verdict == "NOT_YET":
        difficulty = "beginner"; ex.append(("Beginner difficulty", "conservative / limited data"))
    elif ic < 0.7 or verdict == "MODIFY":
        difficulty = "moderate"
    else:
        difficulty = "advanced"

    joined = " ".join(movements)
    joint = "low" if any(k in joined for k in ("impact", "knee", "joint", "jump", "inversion")) else "moderate"
    if movements:
        ex.append(("Joint-friendly", reasons[0] if reasons else "movement constraint"))
    mobility_req = "gentle_rom" if movements else "standard"
    balance = "supported" if supported else "low"
    if supported:
        ex.append(("Balance-supported", "balance demand"))

    equip = list(authority.equipment) if authority else (profile or {}).get("equipment") or ["bodyweight"]
    equip = [equip] if isinstance(equip, str) else list(equip)
    minutes = {"beginner": 20, "moderate": 35, "advanced": 50}[difficulty]

    anchor, recent = diversity.next_anchor(subject, "workout", record=record)
    families = [f for f in _FAMILIES.get(goal, _FAMILIES["general_fitness"])]
    adaptation = persona_adaptation or {}
    rules = set(getattr(expert_consensus, "applicable_rule_ids", ()))
    explicit_experience = str(authority.explicit_facts.get("level") or
                              authority.explicit_facts.get("experience_level") or "").lower() if authority else ""
    recovery_state = str(authority.recovery_state or "").lower() if authority else ""
    if adaptation and not explicit_experience:
        if adaptation.get("beginner"):
            difficulty = "beginner"
            minutes = min(minutes, 25)
            families = families[:3] + ["core"]
        elif adaptation.get("advanced"):
            difficulty = "advanced"
            minutes = max(minutes, 50)
        if adaptation.get("home_equipment"):
            families = [family for family in families if family != "carry"] + ["core"]
            families = list(dict.fromkeys(families))
    if rules & {"GRV-001", "GRV-003", "WNK-003"} and recovery_state not in {"fresh", "good"}:
        minutes = min(minutes, 25)
        mobility_req = "gentle_rom"
        families = list(dict.fromkeys(families + ["mobility"]))
    if "MCG-001" in rules:
        joint = "low"
        mobility_req = "gentle_rom"
        minutes = min(minutes, 25)
        families = [family for family in families if family not in {"squat", "hinge", "conditioning"}]
        movements.append("painful range")
    if explicit_experience in {"beginner", "intermediate", "advanced"}:
        difficulty = explicit_experience if explicit_experience != "intermediate" else "moderate"
        minutes = {"beginner": min(minutes, 25), "moderate": 35, "advanced": max(minutes, 50)}[difficulty]
    if authority:
        locked_exclusions = set(authority.locked_preferences.get("exercise_exclusions", ()))
        safety_exclusions = set(authority.safety_constraints)
        blocked = locked_exclusions | safety_exclusions
        if blocked:
            families = [family for family in families if family not in blocked]
            movements.extend(sorted(blocked))
            joint = "low"
            mobility_req = "gentle_rom"
    for m in movements:
        ex.append((f"Avoid {m}", "safety constraint"))
    return WorkoutBlueprint(
        goal=goal, difficulty=difficulty, mobility_requirement=mobility_req, joint_impact=joint,
        balance_demand=balance, equipment=equip, session_minutes=minutes, exercise_families=families,
        contraindications=movements, rotation_anchor=anchor, meal_diversity=recent, explanations=ex)


# ── Recovery ─────────────────────────────────────────────────────────────────
def _recovery(decision, profile, prefs, subject, *, record=True) -> RecoveryBlueprint:
    anchor, recent = diversity.next_anchor(subject, "recovery", record=record)
    ex = [("Recovery focus", "readiness low / deload")]
    if getattr(decision, "halt", False):
        ex.append(("No hard training", "safety signal — route to care"))
    return RecoveryBlueprint(
        sleep_hours=8.0, hydration_liters=2.5, walking_minutes=25, mobility_minutes=10,
        stress_reduction="breathing", breathing_minutes=5,
        rotation_anchor=anchor, meal_diversity=recent, explanations=ex)


_BUILDERS = {"nutrition": _nutrition, "workout": _workout, "recovery": _recovery}


def design(kind=None, *, decision=None, profile=None, preferences=None, subject="anon", record=True,
           expert_consensus=None, persona_adaptation=None, authority: WorkoutAuthority | None = None,
           knowledge_resolver=None, planning_blueprint=None):
    """Design a Blueprint. `kind` (nutrition|workout|recovery) may be given explicitly
    or inferred from the Brain decision's intervention. Returns None when the decision
    routes/asks (medical_followup / crisis_support / conversation) — nothing to design."""
    if kind is None:
        kind = blueprint_kind_for(decision)
    if kind is None:
        return None
    builder = _BUILDERS.get(kind)
    if builder is None:
        return None
    if planning_blueprint is not None:
        from recommend.engine import RecommendationOutcome
        if planning_blueprint.intent.value != kind or planning_blueprint.outcome is not RecommendationOutcome.RECOMMEND:
            raise ValueError("architect requires an approved recommendation blueprint")
    # Phase 15 injects the read-only resolver at the recommendation seam. Its
    # resolution is intentionally not applied until an explicitly approved phase.
    if knowledge_resolver is not None:
        knowledge_resolver.resolve_for_recommendation(kind)
    if kind == "workout":
        if authority is not None and authority.intent != "workout":
            raise ValueError("invalid workout authority")
        return builder(decision, profile or {}, preferences or {}, subject, record=record,
                       expert_consensus=expert_consensus,
                       persona_adaptation=persona_adaptation, authority=authority)
    return builder(decision, profile or {}, preferences or {}, subject, record=record)
