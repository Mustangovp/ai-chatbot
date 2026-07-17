"""Immutable, catalog-only meal definitions for the isolated nutrition engine.

A library meal is a fixed set of catalog food_ids with default portions in
grams. It contains no generated text and no macros: names are static BG/EN
labels and every food is a real catalog id. The library is a source of
deterministic alternatives for rotation; it never computes nutrition.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import MEAL_TYPES


@dataclass(frozen=True)
class LibraryMeal:
    meal_id: str
    display_name_bg: str
    display_name_en: str
    meal_type: str
    food_ids: tuple[str, ...]
    default_portions_g: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        if self.meal_type not in MEAL_TYPES:
            raise ValueError(f"unknown meal type: {self.meal_type}")
        if not self.food_ids:
            raise ValueError("a library meal needs at least one food")
        if len(self.food_ids) != len(self.default_portions_g):
            raise ValueError("food_ids and default portions must align")
        if len(set(self.food_ids)) != len(self.food_ids):
            raise ValueError("a library meal must not repeat a food")
        if any(portion <= 0 for portion in self.default_portions_g):
            raise ValueError("default portions must be positive")


def _meal(meal_id, bg, en, meal_type, items) -> LibraryMeal:
    return LibraryMeal(meal_id, bg, en, meal_type,
                       tuple(fid for fid, _ in items),
                       tuple(Decimal(str(g)) for _, g in items))


_LIBRARY: tuple[LibraryMeal, ...] = (
    _meal("brk_eggs_oats", "Яйчен белтък, овес и банан", "Egg whites, oats and banana", "breakfast",
          (("dev_egg_whites", 200), ("dev_oats_dry", 80), ("dev_banana", 120))),
    _meal("brk_yogurt_berries", "Кисело мляко с боровинки и бадеми", "Yogurt with blueberries and almonds", "breakfast",
          (("dev_greek_yogurt_nonfat", 200), ("dev_blueberries", 125), ("dev_almonds", 25))),
    _meal("brk_eggs_bread", "Варени яйца, пълнозърнест хляб и авокадо", "Boiled eggs, wholegrain bread and avocado", "breakfast",
          (("dev_whole_egg_boiled", 100), ("dev_wholegrain_bread", 80), ("dev_avocado", 100))),

    _meal("snk_yogurt_apple", "Кисело мляко и ябълка", "Yogurt and apple", "snack",
          (("dev_greek_yogurt_nonfat", 200), ("dev_apple", 150))),
    _meal("snk_tuna_walnuts", "Риба тон и орехи", "Tuna and walnuts", "snack",
          (("dev_tuna_water_drained", 140), ("dev_walnuts", 20))),
    _meal("snk_cottage_berries", "Извара с боровинки", "Cottage cheese with blueberries", "snack",
          (("dev_cottage_cheese", 200), ("dev_blueberries", 125))),

    _meal("lnch_chicken_rice", "Пиле, ориз и броколи", "Chicken, rice and broccoli", "lunch",
          (("dev_chicken_breast_cooked", 175), ("dev_rice_cooked", 250), ("dev_broccoli_cooked", 200), ("dev_olive_oil", 10))),
    _meal("lnch_beef_potato", "Телешко, картофи и спанак", "Beef, potatoes and spinach", "lunch",
          (("dev_lean_beef_cooked", 175), ("dev_potatoes_boiled", 250), ("dev_spinach_cooked", 150))),
    _meal("lnch_tofu_quinoa", "Тофу, киноа и салата", "Tofu, quinoa and salad", "lunch",
          (("dev_tofu_firm", 175), ("dev_quinoa_cooked", 225), ("dev_mixed_salad", 200), ("dev_olive_oil", 10))),

    _meal("dnr_turkey_pasta", "Пуйка, паста и чушки", "Turkey, pasta and peppers", "dinner",
          (("dev_turkey_breast_cooked", 175), ("dev_pasta_cooked", 225), ("dev_green_pepper", 150))),
    _meal("dnr_fish_sweet_potato", "Риба, сладък картоф и броколи", "Fish, sweet potato and broccoli", "dinner",
          (("dev_white_fish_cooked", 175), ("dev_sweet_potato_cooked", 225), ("dev_broccoli_cooked", 200), ("dev_olive_oil", 10))),
    _meal("dnr_salmon_rice", "Сьомга, ориз и спанак", "Salmon, rice and spinach", "dinner",
          (("dev_salmon_cooked", 150), ("dev_rice_cooked", 250), ("dev_spinach_cooked", 150))),
)


def _validate_unique() -> None:
    ids = [meal.meal_id for meal in _LIBRARY]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate meal_id in library")


_validate_unique()

_BY_ID: dict[str, LibraryMeal] = {meal.meal_id: meal for meal in _LIBRARY}


def all_library_meals() -> tuple[LibraryMeal, ...]:
    return _LIBRARY


def library_meal(meal_id: str) -> LibraryMeal | None:
    return _BY_ID.get(meal_id)


def library_meals_for(meal_type: str) -> tuple[LibraryMeal, ...]:
    """Meals for a type in stable definition order."""
    return tuple(meal for meal in _LIBRARY if meal.meal_type == meal_type)
