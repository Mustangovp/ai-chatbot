"""Versioned catalog loading and governance validation for Nutrition Engine V2."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .models import FoodItem, OptimizedNutritionDay


SUPPORTED_UNITS = frozenset({"g", "ml", "pcs"})
REVIEW_STATUSES = frozenset({
    "DATA_PENDING", "SOURCE_VERIFIED", "NUTRIENTS_REVIEWED",
    "PORTIONS_PENDING", "PRODUCTION_READY",
})


@dataclass(frozen=True)
class CatalogGovernance:
    development_allow_pending: bool
    production_ready: bool
    kcal_consistency_tolerance: Decimal
    supported_units: frozenset[str] = SUPPORTED_UNITS
    liquid_categories: frozenset[str] = frozenset({"liquid"})

    def __post_init__(self) -> None:
        if self.production_ready and self.development_allow_pending:
            raise ValueError("production-ready catalog cannot allow pending records")
        if self.kcal_consistency_tolerance < 0:
            raise ValueError("kcal consistency tolerance must be non-negative")


@dataclass(frozen=True)
class Catalog:
    version: str
    foods: tuple[FoodItem, ...]

    def by_id(self, food_id: str) -> FoodItem | None:
        return next((food for food in self.foods if food.food_id == food_id), None)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _food(raw: dict[str, object]) -> FoodItem:
    return FoodItem(
        food_id=str(raw["food_id"]), catalog_version=str(raw["catalog_version"]),
        display_name_bg=str(raw["display_name_bg"]), display_name_en=str(raw["display_name_en"]),
        category=str(raw["category"]), preparation_state=str(raw["preparation_state"]),
        nutrient_reference_quantity=_decimal(raw["nutrient_reference_quantity"]),
        protein_per_100g=_decimal(raw["protein_per_100g"]), carbs_per_100g=_decimal(raw["carbs_per_100g"]),
        fat_per_100g=_decimal(raw["fat_per_100g"]), kcal_per_100g=_decimal(raw["kcal_per_100g"]),
        default_unit=str(raw["default_unit"]), allowed_units=tuple(str(v) for v in raw["allowed_units"]),
        grams_per_piece=_decimal(raw["grams_per_piece"]) if raw.get("grams_per_piece") is not None else None,
        minimum_portion=_decimal(raw["minimum_portion"]), maximum_portion=_decimal(raw["maximum_portion"]),
        portion_increment=_decimal(raw["portion_increment"]), default_portion=_decimal(raw["default_portion"]),
        allergens=frozenset(str(v) for v in raw["allergens"]), dietary_tags=frozenset(str(v) for v in raw["dietary_tags"]),
        allowed_meals=frozenset(str(v) for v in raw["allowed_meals"]), source_name=str(raw["source_name"]),
        source_record_id=str(raw["source_record_id"]), source_version=str(raw["source_version"]),
        review_status=str(raw["review_status"]), reviewer_note=str(raw["reviewer_note"]),
        data_basis=str(raw["data_basis"]),
    )


def _validate(food: FoodItem, version: str, governance: CatalogGovernance) -> None:
    if food.catalog_version != version:
        raise ValueError("catalog-version mismatch")
    if not food.display_name_bg or not food.display_name_en:
        raise ValueError("BG and EN display names are required")
    if not food.preparation_state or food.preparation_state.lower() in {"unknown", "ambiguous"}:
        raise ValueError("ambiguous preparation state")
    if not food.source_name or not food.source_record_id or not food.source_version or not food.data_basis:
        raise ValueError("missing provenance")
    if food.review_status not in REVIEW_STATUSES:
        raise ValueError("unsupported review status")
    if food.nutrient_reference_quantity != Decimal("100"):
        raise ValueError("nutrient reference quantity must be 100 g")
    if any(value < 0 for value in (food.protein_per_100g, food.carbs_per_100g, food.fat_per_100g, food.kcal_per_100g)):
        raise ValueError("negative nutrient value")
    estimated_kcal = food.protein_per_100g * 4 + food.carbs_per_100g * 4 + food.fat_per_100g * 9
    if abs(food.kcal_per_100g - estimated_kcal) > governance.kcal_consistency_tolerance:
        raise ValueError("kcal is inconsistent with supplied macro values")
    if food.default_unit not in governance.supported_units or not set(food.allowed_units) <= governance.supported_units:
        raise ValueError("unsupported units")
    if "ml" in food.allowed_units and food.category not in governance.liquid_categories:
        raise ValueError("ml is restricted to liquid catalog categories")
    if food.default_unit == "pcs" and (food.grams_per_piece is None or food.grams_per_piece <= 0):
        raise ValueError("piece-based food requires grams-per-piece")
    if food.default_unit != "pcs" and food.grams_per_piece is not None:
        raise ValueError("grams-per-piece is only valid for piece-based food")
    if not food.allowed_meals <= {"breakfast", "lunch", "dinner", "snack"}:
        raise ValueError("unsupported meal")
    if not (food.minimum_portion > 0 and food.portion_increment > 0 and
            food.maximum_portion >= food.minimum_portion and
            food.minimum_portion <= food.default_portion <= food.maximum_portion):
        raise ValueError("invalid min/max/increment relationship")
    if governance.production_ready and food.review_status != "PRODUCTION_READY":
        raise ValueError("unreviewed records are not production-ready")
    if not governance.development_allow_pending and food.review_status != "PRODUCTION_READY":
        raise ValueError("pending records are not allowed")


def load_catalog_records(version: str, records: list[dict[str, object]], governance: CatalogGovernance) -> Catalog:
    foods = tuple(_food(raw) for raw in records)
    if len({food.food_id for food in foods}) != len(foods):
        raise ValueError("duplicate food ID")
    direct_source_ids = [food.source_record_id for food in foods if "+" not in food.source_record_id]
    if len(set(direct_source_ids)) != len(direct_source_ids):
        raise ValueError("duplicate source record ID")
    for food in foods:
        _validate(food, version, governance)
    return Catalog(version, foods)


def load_catalog_file(path: str | Path, governance: CatalogGovernance) -> Catalog:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), str) or not isinstance(payload.get("foods"), list):
        raise ValueError("invalid catalog document")
    return load_catalog_records(payload["version"], payload["foods"], governance)


def project_user_day(catalog: Catalog, day: OptimizedNutritionDay, language: str) -> dict[str, object]:
    """Return the isolated, localized user projection without catalog metadata."""
    unit_labels = {
        "bg": {"g": "г", "ml": "мл", "pcs": "бр."},
        "en": {"g": "g", "ml": "ml", "pcs": "pcs"},
    }
    locale = "bg" if str(language).lower() == "bg" else "en"

    def nutrients(value):
        return {"protein_g": value.protein_g, "carbs_g": value.carbs_g,
                "fat_g": value.fat_g, "kcal": value.kcal}

    meals = []
    for meal in day.meals:
        foods = []
        for item in meal.foods:
            food = catalog.by_id(item.food_id)
            if food is None:
                raise ValueError("optimized food is absent from catalog")
            foods.append({"name": food.display_name_bg if locale == "bg" else food.display_name_en,
                          "quantity": item.quantity,
                          "unit": unit_labels[locale][item.display_unit],
                          "macros": nutrients(item.nutrients)})
        meals.append({"meal_type": meal.meal_type, "foods": foods, "totals": nutrients(meal.totals)})
    return {"meals": meals, "daily_totals": nutrients(day.daily_totals)}
