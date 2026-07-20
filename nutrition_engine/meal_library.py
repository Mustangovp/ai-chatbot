"""Immutable, catalog-backed meal definitions for the isolated nutrition engine.

Meal definitions contain only stable identity, catalog ingredients, portions,
tags, and preparation difficulty. ``build_nutrition_knowledge_library``
resolves their macros from a supplied catalog, making the catalog rather than
free-form text the sole source of nutrition values.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .catalog import Catalog
from .models import MEAL_TYPES, Nutrients


MEAL_CATEGORIES = MEAL_TYPES + ("pre_workout", "post_workout")
PREPARATION_DIFFICULTIES = ("no_cook", "easy", "moderate")
NUTRITION_LIBRARY_VERSION = "nutrition-knowledge-library-v1"


@dataclass(frozen=True)
class MealIngredient:
    """One fixed catalog ingredient and its declared portion in grams."""

    food_id: str
    grams: Decimal
    macros: Nutrients


@dataclass(frozen=True)
class MealCandidate:
    """Resolved immutable meal data. It contains no prompt or generated prose."""

    meal_id: str
    version: str
    category: str
    ingredients: tuple[MealIngredient, ...]
    macros: Nutrients
    tags: tuple[str, ...]
    dietary_compatibility: frozenset[str]
    preparation_difficulty: str


@dataclass(frozen=True)
class NutritionKnowledgeLibrary:
    """One validated, catalog-version-bound collection of meal candidates."""

    version: str
    catalog_version: str
    meals: tuple[MealCandidate, ...]

    def __post_init__(self) -> None:
        if not self.version or not self.catalog_version:
            raise ValueError("nutrition library identity is required")
        ids = [meal.meal_id for meal in self.meals]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate meal_id in nutrition library")
        categories = {meal.category for meal in self.meals}
        missing = set(MEAL_CATEGORIES) - categories
        if missing:
            raise ValueError("nutrition library category coverage is incomplete")


@dataclass(frozen=True)
class LibraryMeal:
    meal_id: str
    display_name_bg: str
    display_name_en: str
    meal_type: str
    food_ids: tuple[str, ...]
    default_portions_g: tuple[Decimal, ...]
    version: str = "nutrition-meal-v1"
    tags: tuple[str, ...] = ()
    preparation_difficulty: str = "easy"

    def __post_init__(self) -> None:
        if self.meal_type not in MEAL_CATEGORIES:
            raise ValueError(f"unknown meal type: {self.meal_type}")
        if not self.meal_id or not self.version:
            raise ValueError("meal identity is required")
        if not self.food_ids:
            raise ValueError("a library meal needs at least one food")
        if len(self.food_ids) != len(self.default_portions_g):
            raise ValueError("food_ids and default portions must align")
        if len(set(self.food_ids)) != len(self.food_ids):
            raise ValueError("a library meal must not repeat a food")
        if any(portion <= 0 for portion in self.default_portions_g):
            raise ValueError("default portions must be positive")
        if self.preparation_difficulty not in PREPARATION_DIFFICULTIES:
            raise ValueError("unknown preparation difficulty")
        object.__setattr__(self, "tags", tuple(sorted({
            str(tag).strip().lower() for tag in self.tags if str(tag).strip()
        })))


def _meal(meal_id, bg, en, meal_type, items, *, tags=(), difficulty="easy") -> LibraryMeal:
    return LibraryMeal(meal_id, bg, en, meal_type,
                       tuple(fid for fid, _ in items),
                       tuple(Decimal(str(g)) for _, g in items),
                       tags=tuple(tags), preparation_difficulty=difficulty)


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
    _meal("pre_banana_oats", "Banana and oats", "Banana and oats", "pre_workout",
          (("dev_banana", 120), ("dev_oats_dry", 50)),
          tags=("pre_workout", "carbohydrate_focused"), difficulty="no_cook"),
    _meal("post_chicken_rice", "Chicken and rice", "Chicken and rice", "post_workout",
          (("dev_chicken_breast_cooked", 175), ("dev_rice_cooked", 225)),
          tags=("post_workout", "high_protein")),
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


def _macros(food, grams: Decimal) -> Nutrients:
    factor = grams / Decimal("100")
    return Nutrients(
        protein_g=food.protein_per_100g * factor,
        carbs_g=food.carbs_per_100g * factor,
        fat_g=food.fat_per_100g * factor,
        kcal=food.kcal_per_100g * factor,
    )


def _dietary_compatibility(foods) -> frozenset[str]:
    """Derive compatibility only from catalog facts, never a meal-name guess."""
    compatibility = {"standard_omnivore"}
    dietary_tags = [food.dietary_tags for food in foods]
    allergens = [food.allergens for food in foods]
    if all("vegetarian" in tags for tags in dietary_tags):
        compatibility.add("vegetarian")
    if all("vegan" in tags for tags in dietary_tags):
        compatibility.add("vegan")
    if all("gluten_free" in tags for tags in dietary_tags):
        compatibility.add("gluten_free")
    if all("dairy" not in values for values in allergens):
        compatibility.add("dairy_free")
        compatibility.add("no_dairy")
    if all("chicken" not in tags for tags in dietary_tags):
        compatibility.add("no_chicken")
    return frozenset(compatibility)


def build_nutrition_knowledge_library(
        catalog: Catalog, *, version: str = NUTRITION_LIBRARY_VERSION) -> NutritionKnowledgeLibrary:
    """Resolve fixed meal definitions into immutable catalog-backed candidates.

    The function performs no selection, optimization, persistence, model call,
    or runtime integration. A changed catalog deterministically changes the
    resolved candidate macros and the resulting catalog-bound library.
    """
    candidates: list[MealCandidate] = []
    for definition in _LIBRARY:
        resolved_foods = []
        ingredients = []
        totals = Nutrients.zero()
        for food_id, grams in zip(definition.food_ids, definition.default_portions_g):
            food = catalog.by_id(food_id)
            if food is None:
                raise ValueError(f"meal library references unknown food: {food_id}")
            if definition.meal_type in MEAL_TYPES and definition.meal_type not in food.allowed_meals:
                raise ValueError(f"meal library category is unsupported by catalog: {definition.meal_id}")
            macros = _macros(food, grams)
            if macros.kcal <= 0:
                raise ValueError(f"meal ingredient has invalid energy: {food_id}")
            resolved_foods.append(food)
            ingredients.append(MealIngredient(food_id, grams, macros))
            totals = totals.plus(macros)
        tags = tuple(sorted({*definition.tags, f"category:{definition.meal_type}"}))
        candidates.append(MealCandidate(
            meal_id=definition.meal_id,
            version=definition.version,
            category=definition.meal_type,
            ingredients=tuple(ingredients),
            macros=totals,
            tags=tags,
            dietary_compatibility=_dietary_compatibility(tuple(resolved_foods)),
            preparation_difficulty=definition.preparation_difficulty,
        ))
    return NutritionKnowledgeLibrary(version=version, catalog_version=catalog.version, meals=tuple(candidates))
