"""
APEX M6 — Blueprint types.

A Blueprint is a fully-specified, machine-decided recommendation. EVERY value is
chosen by the Architect (deterministic Python); the LLM only phrases it. Blueprints
carry their own explanations ("why this recommendation?"). No Brain logic here.
"""
from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Explanation:
    claim: str        # e.g. "High protein", "Joint-friendly", "No oats"
    because: str      # e.g. "muscle gain", "knee pain", "preference"

    def as_tuple(self):
        return (self.claim, self.because)


@dataclass(frozen=True)
class NutritionBlueprint:
    meal: str                    # breakfast | lunch | dinner | snack
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    max_prep_minutes: int
    budget: str                  # low | moderate | premium
    preferred_foods: list
    avoided_foods: list
    rotation_anchor: str         # the anchor the LLM must build around (diversity)
    meal_diversity: list         # recent anchors to AVOID repeating
    difficulty: str              # no-cook | easy | moderate
    required_equipment: list
    seasonality: str             # spring | summer | autumn | winter
    medical_constraints: list
    explanations: list = field(default_factory=list)
    kind: str = "nutrition"


@dataclass(frozen=True)
class WorkoutBlueprint:
    goal: str
    difficulty: str              # beginner | moderate | advanced
    mobility_requirement: str    # standard | gentle_rom
    joint_impact: str            # low | moderate | high
    balance_demand: str          # supported | low | moderate
    equipment: list
    session_minutes: int
    exercise_families: list
    contraindications: list
    rotation_anchor: str         # rotated family emphasis (diversity)
    meal_diversity: list         # recent anchors to avoid (naming kept generic)
    explanations: list = field(default_factory=list)
    kind: str = "workout"


@dataclass(frozen=True)
class RecoveryBlueprint:
    sleep_hours: float
    hydration_liters: float
    walking_minutes: int
    mobility_minutes: int
    stress_reduction: str        # breathing | walk | nature | none
    breathing_minutes: int
    rotation_anchor: str
    meal_diversity: list
    explanations: list = field(default_factory=list)
    kind: str = "recovery"


def to_dict(blueprint) -> dict:
    """Serialize a blueprint (explanations become {claim, because} dicts)."""
    d = asdict(blueprint)
    d["explanations"] = [{"claim": e[0], "because": e[1]} for e in blueprint.explanations]
    return d
