"""Bounded rotation context from authoritative structured nutrition plans."""
from __future__ import annotations

from typing import Mapping, Sequence

import nutrition_plan

from .models import RotationContext


def rotation_context_from_plan_records(records: Sequence[Mapping[str, object]] | object,
                                       *, maximum_history_depth: int = 14) -> RotationContext:
    """Read only canonical plan records; rendered chat history is never parsed."""
    if (not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray))
            or not isinstance(maximum_history_depth, int) or not 0 <= maximum_history_depth <= 14):
        return RotationContext(maximum_history_depth=0)
    slots: dict[str, list[str]] = {"breakfast": [], "lunch": [], "dinner": []}
    proteins: list[str] = []
    starches: list[str] = []
    for record in records[:maximum_history_depth]:
        raw = record.get("plan") if isinstance(record, Mapping) else None
        try:
            plan = nutrition_plan.from_record(raw) if isinstance(raw, Mapping) else None
        except (TypeError, ValueError, nutrition_plan.NutritionPlanError):
            continue
        if plan is None:
            continue
        for meal in plan.meals:
            if meal.meal_type not in slots:
                continue
            food_ids = tuple(food.food_id for food in meal.foods if food.food_id)
            if not food_ids:
                continue
            slots[meal.meal_type].append("|".join(food_ids))
            if meal.meal_type in {"lunch", "dinner"}:
                for food in meal.foods:
                    food_id = food.food_id or ""
                    if any(token in food_id for token in ("chicken", "turkey", "salmon", "tuna", "beef", "tofu", "lentil", "chickpea")):
                        proteins.append(food_id)
                    if any(token in food_id for token in ("rice", "potato", "pasta", "oat", "quinoa", "bread")):
                        starches.append(food_id)
    return RotationContext(
        tuple(slots["breakfast"]), tuple(slots["lunch"]), tuple(slots["dinner"]),
        tuple(proteins), tuple(starches), maximum_history_depth,
    ).sanitized()
