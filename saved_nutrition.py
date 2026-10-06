"""Public read projection of one validated saved NutritionPlan, never intake."""
from datetime import datetime
from decimal import Decimal

import nutrition_plan


_MACROS = ("kcal", "protein_g", "carbs_g", "fat_g")


def _value(value):
    if value is None:
        return None
    if not value.is_finite():
        raise ValueError("non-finite saved quantity")
    # Decimal strings preserve the saved values without float rounding.
    return format(value, "f")


def _macros(value):
    return {key: _value(getattr(value, key)) for key in _MACROS}


def _consistent_macros(raw, validated):
    # from_record validates food facts and reconstructs their sums. A corrupt
    # redundant stored total must not be presented as a validated saved total.
    if not isinstance(raw, dict) or any(
            Decimal(str(raw.get(key))) != getattr(validated, key) for key in _MACROS):
        raise ValueError("inconsistent saved totals")


def latest_saved_plan(row):
    if row is None:
        return None
    try:
        raw = row["plan"]
        plan = nutrition_plan.from_record(raw)
        if plan.id != row["plan_id"] or plan.version != row["version"]:
            return None
        stamp = datetime.fromisoformat(plan.created_at_utc.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        _consistent_macros(raw.get("totals"), plan.totals)
        meals = []
        for source, meal in zip(raw["meals"], plan.meals, strict=True):
            _consistent_macros(source.get("macros"), meal.macros)
            meals.append({
                "meal_type": meal.meal_type,
                # The existing loader's meal-type fallback is not a clock time.
                "time": meal.time if meal.time and meal.time != meal.meal_type else None,
                "foods": [{"display_name": food.display_name, "grams": _value(food.grams),
                           "measurement_state": food.measurement_state.value if food.measurement_state else None}
                          for food in meal.foods],
                "macros": _macros(meal.macros),
            })
        return {
            "created_at": plan.created_at_utc,
            "targets": {"kcal": _value(plan.targets.kcal), "protein_g": _value(plan.targets.protein),
                        "carbs_g": _value(plan.targets.carbs), "fat_g": _value(plan.targets.fat)},
            "totals": _macros(plan.totals), "meals": meals, "restrictions": list(plan.restrictions),
        }
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        return None
