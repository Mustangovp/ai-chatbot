"""Closed food-suitability checks over explicitly recorded restrictions only.

This module neither extracts facts from conversation nor supplies nutrient values.
An identity allowlist is deliberately narrower than the generator's vocabulary.
"""
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import json
from pathlib import Path
import re


class ConstraintKind(str, Enum):
    ALLERGEN = "allergen"
    DIET = "diet"
    EXCLUDED_FOOD = "excluded_food"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class DietaryConstraint:
    kind: ConstraintKind
    value: str


@dataclass(frozen=True)
class FoodIdentity:
    key: str
    allergens: frozenset[str]
    diets: frozenset[str]


class RestrictionSafetyError(ValueError):
    pass


def _token(value):
    return re.sub(r"[\s_-]+", " ", str(value).strip().casefold())


_ALLERGENS = {
    "peanut": ("peanut", "peanuts", "фъстък", "фъстъци"),
    "tree_nut": ("tree nut", "tree nuts"),
    "dairy": ("dairy", "milk", "мляко", "млечни"),
    "egg": ("egg", "eggs", "яйца"),
    "fish": ("fish", "риба"),
    "shellfish": ("shellfish", "crustaceans", "molluscs", "морски дарове"),
    "soy": ("soy", "soya", "соя"),
    "gluten": ("gluten", "глутен", "wheat", "пшеница"),
    "sesame": ("sesame", "сусам"),
    "mustard": ("mustard", "горчица"),
    "celery": ("celery", "целина"),
    "lupin": ("lupin", "лупина"),
    "sulphites": ("sulphites", "sulfites", "сулфити"),
}

# Explicit equivalences across preparation variants; no substring matching.
_CATALOG_FAMILIES = {
    "dev_chicken_breast_cooked": "chicken", "dev_turkey_breast_cooked": "turkey",
    "dev_whole_egg_boiled": "eggs", "dev_egg_whites": "eggs",
    "dev_greek_yogurt_2pct": "greek_yogurt", "dev_greek_yogurt_nonfat": "greek_yogurt",
    "dev_milk_lowfat": "milk", "dev_oats_dry": "oats", "dev_rice_cooked": "rice",
    "dev_potatoes_boiled": "potatoes", "dev_banana": "banana", "dev_apple": "apple",
    "dev_salmon_cooked": "salmon", "dev_tuna_water_drained": "tuna", "dev_tuna_canned": "tuna",
    "dev_broccoli_cooked": "broccoli", "dev_broccoli_raw": "broccoli",
}


@lru_cache(maxsize=1)
def _identities():
    identities = {}

    def add(key, aliases, allergens=(), diets=("vegan", "vegetarian")):
        item = FoodIdentity(key, frozenset(allergens), frozenset(diets))
        for alias in (key, *aliases):
            identities[_token(alias)] = item

    # Exact simple-food names; composite dishes and brands are not assumed safe.
    add("peanuts", ("peanut", "фъстъци", "фъстък"), ("peanut",))
    add("rice", ("white rice", "cooked rice", "ориз", "сварен ориз"))
    add("oats", ("oatmeal", "овес", "овесени ядки"), ("gluten",))
    add("chicken", ("chicken breast", "пилешко", "пилешки гърди"), diets=())
    add("eggs", ("egg", "whole eggs", "boiled eggs", "яйца", "варени яйца"), ("egg",), ("vegetarian",))
    add("salmon", ("сьомга",), ("fish",), ())
    add("turkey", ("turkey breast", "пуешко филе"), diets=())
    add("milk", ("мляко",), ("dairy",), ("vegetarian",))
    add("greek_yogurt", ("greek yogurt", "greek yoghurt", "гръцко кисело мляко"), ("dairy",), ("vegetarian",))
    add("banana", ("bananas", "банан", "банани"))
    add("apple", ("apples", "ябълка", "ябълки"))
    add("potatoes", ("potato", "картофи", "картоф"))
    catalog = json.loads((Path(__file__).parent / "nutrition_engine/data/food_catalog_v1.json").read_text(encoding="utf-8"))
    for row in catalog["foods"]:
        aliases = (row["display_name_en"], row["display_name_bg"])
        # Reuse catalog identities/allergens, never trust generator-supplied tags.
        add(row["food_id"], aliases, tuple("tree_nut" if tag == "tree_nuts" else tag for tag in row["allergens"]),
            tuple(tag for tag in row["dietary_tags"] if tag in ("vegan", "vegetarian")))
    return identities


def canonical_constraints(recorded):
    """Normalize a recorded field, not arbitrary conversational prose."""
    if not recorded:
        return ()
    if not isinstance(recorded, (tuple, list)):
        recorded = (recorded,)
    result = set()
    for raw in recorded:
        text = _token(raw)
        if text in ("", "none", "no allergies", "няма", "нямам алергии"):
            continue
        if text in ("vegan", "vegetarian", "веган", "вегетарианец", "вегетарианско"):
            result.add(DietaryConstraint(ConstraintKind.DIET,
                       "vegan" if text in ("vegan", "веган") else "vegetarian"))
            continue
        matched = False
        for allergen, aliases in _ALLERGENS.items():
            forms = {form for alias in aliases for form in (
                alias, f"{alias} allergy", f"allergy to {alias}", f"allergic to {alias}",
                f"no {alias}", f"without {alias}", f"{alias} free", f"алергия към {alias}", f"без {alias}")}
            if text in forms:
                result.add(DietaryConstraint(ConstraintKind.ALLERGEN, allergen))
                matched = True
                break
        if matched:
            continue
        excluded = re.fullmatch(r"(?:no|without|без) (.+)", text)
        identity = _identities().get(excluded[1]) if excluded else None
        if identity:
            result.add(DietaryConstraint(ConstraintKind.EXCLUDED_FOOD,
                                        _CATALOG_FAMILIES.get(identity.key, identity.key)))
        else:
            result.add(DietaryConstraint(ConstraintKind.UNSUPPORTED, text))
    return tuple(sorted(result, key=lambda item: (item.kind.value, item.value)))


def recorded_profile_restrictions(profile):
    if not isinstance(profile, dict):
        return ()
    values = []
    for key in ("allergies", "foodPreferences", "diet", "dietaryRestrictions"):
        value = profile.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(value)
        elif value:
            values.extend(str(value).split(","))
    return tuple(values)


def validate_foods(foods, recorded):
    constraints = canonical_constraints(recorded)
    if not constraints:
        return
    if any(item.kind is ConstraintKind.UNSUPPORTED for item in constraints):
        raise RestrictionSafetyError("nutrition_restriction_unsupported")
    for food in foods:
        identity = _identities().get(_token(food.display_name))
        if identity is None:
            raise RestrictionSafetyError("nutrition_food_identity_unresolved")
        # A supplied catalog ID cannot contradict the resolved visible identity.
        if food.catalog_id and _identities().get(_token(food.catalog_id)) != identity:
            raise RestrictionSafetyError("nutrition_food_identity_ambiguous")
        from recipe_engine.recipe_matcher import ingredient_key
        if (food.food_id and food.food_id != ingredient_key(food.display_name)
                and _identities().get(_token(food.food_id)) != identity):
            raise RestrictionSafetyError("nutrition_food_identity_ambiguous")
        for constraint in constraints:
            blocked = (
                constraint.kind is ConstraintKind.ALLERGEN and constraint.value in identity.allergens
                or constraint.kind is ConstraintKind.DIET and constraint.value not in identity.diets
                or constraint.kind is ConstraintKind.EXCLUDED_FOOD
                and constraint.value == _CATALOG_FAMILIES.get(identity.key, identity.key)
            )
            if blocked:
                raise RestrictionSafetyError("nutrition_food_restriction_conflict")
