from decimal import Decimal
import base64
import json
from types import SimpleNamespace

import nutrition_plan
from nutrition_validation import NutritionTargets
from recipe_engine.recipe_engine import match_plan
from recipe_engine.recipe_library import load_recipes
from recipe_engine.recipe_matcher import match_meal, profile_equipment
from recipe_engine.recipe_renderer import recipe_token


def _plan():
    return nutrition_plan.build_plan({"meals": [
        {"meal_type": "breakfast", "foods": [
            {"display_name": "Eggs", "grams": "200", "protein_g": "40", "carbs_g": "0", "fat_g": "20", "kcal": "340"},
            {"display_name": "Oats", "grams": "100", "protein_g": "0", "carbs_g": "100", "fat_g": "0", "kcal": "360"},
        ]},
        {"meal_type": "lunch", "foods": [
            {"display_name": "Chicken breast", "grams": "200", "protein_g": "70", "carbs_g": "0", "fat_g": "15", "kcal": "500"},
            {"display_name": "Rice", "grams": "200", "protein_g": "0", "carbs_g": "140", "fat_g": "15", "kcal": "600"},
        ]},
        {"meal_type": "dinner", "foods": [
            {"display_name": "Salmon", "grams": "200", "protein_g": "65", "carbs_g": "0", "fat_g": "28", "kcal": "600"},
            {"display_name": "Rice", "grams": "300", "protein_g": "0", "carbs_g": "110", "fat_g": "0", "kcal": "400"},
        ]},
    ]}, NutritionTargets(Decimal("2800"), Decimal("175"), Decimal("350"), Decimal("78")),
        restrictions=(), provenance={"test": "recipe"})


def test_recipe_library_is_small_and_curated():
    recipes = load_recipes()
    assert 20 <= len(recipes) <= 25
    assert sum(recipe.meal_type == "breakfast" for recipe in recipes) >= 8
    assert sum(recipe.meal_type in {"lunch", "dinner"} for recipe in recipes) >= 8
    assert sum(recipe.meal_type == "snack" for recipe in recipes) >= 5
    assert all(1 <= len(recipe.steps) <= 6 for recipe in recipes)
    assert all(1 <= len(recipe.healthy_cooking_tips) <= 3 for recipe in recipes)


def test_recipe_matching_is_deterministic_and_preserves_plan_macros():
    plan = _plan()
    before = tuple((meal.id, meal.macros, tuple((food.id, food.macros) for food in meal.foods)) for meal in plan.meals)

    first = match_plan(plan, {"cooking_equipment": ["pan", "oven"]})
    second = match_plan(plan, {"cooking_equipment": ["pan", "oven"]})

    assert {key: value.recipe.id for key, value in first.items()} == {
        key: value.recipe.id for key, value in second.items()
    }
    assert len(first) == 3
    assert before == tuple((meal.id, meal.macros, tuple((food.id, food.macros) for food in meal.foods)) for meal in plan.meals)


def test_recipe_token_is_emitted_in_its_own_table_column():
    plan = _plan()
    match = match_plan(plan, {"cooking_equipment": ["pan", "oven"]})
    rendered = nutrition_plan.render(
        plan,
        "en",
        {meal_id: f"recipe:{item.recipe.id}" for meal_id, item in match.items()},
    )

    breakfast_row = rendered.splitlines()[2].split("|")
    assert breakfast_row[2].strip() == plan.meals[0].id
    assert breakfast_row[9].strip().startswith("Starts the day")
    assert breakfast_row[10].strip().startswith("recipe:")


def test_recipe_token_carries_the_immutable_meal_id():
    match = match_plan(_plan(), {"cooking_equipment": ["pan", "oven"]})
    meal_id, recipe_match = next(iter(match.items()))

    token = recipe_token(recipe_match, meal_id)
    payload = json.loads(base64.b64decode(token.removeprefix("recipe:")))

    assert payload["meal_id"] == meal_id
    assert payload["id"] == recipe_match.recipe.id


def test_recipe_matcher_accepts_exact_bulgarian_catalog_display_names():
    breakfast = nutrition_plan.NutritionMeal(
        id="meal-bg", name="Закуска", meal_type="breakfast", time="08:00",
        foods=(
            nutrition_plan.NutritionFood("food-bg-oats", None, "Овесени ядки, сухи", Decimal("150"),
                                        nutrition_plan.NutritionMacros(Decimal("20"), Decimal("100"), Decimal("10"), Decimal("570"))),
            nutrition_plan.NutritionFood("food-bg-eggs", None, "Яйце, сварено", Decimal("150"),
                                        nutrition_plan.NutritionMacros(Decimal("18"), Decimal("1"), Decimal("15"), Decimal("215"))),
        ), macros=nutrition_plan.NutritionMacros(Decimal("38"), Decimal("101"), Decimal("25"), Decimal("785")),
    )

    assert match_meal(breakfast, load_recipes(), profile_equipment({})).recipe.id == "breakfast-eggs-oats"


def test_recipe_matcher_matches_the_live_delivery_ingredient_variants():
    samples = (
        ("breakfast", ("Oatmeal", "Greek Yogurt", "Almonds"), "breakfast-yogurt-oats-almond"),
        ("lunch", ("Chicken breast, roasted", "Brown rice, cooked", "Broccoli, steamed", "Olive oil"), "lunch-chicken-rice"),
        ("dinner", ("Salmon, grilled", "Quinoa, cooked", "Spinach, raw", "Avocado", "Cherry tomatoes"), "dinner-salmon-quinoa"),
    )
    for meal_type, ingredient_names, expected in samples:
        meal = SimpleNamespace(
            meal_type=meal_type,
            foods=tuple(SimpleNamespace(display_name=name) for name in ingredient_names),
        )
        assert match_meal(meal, load_recipes(), profile_equipment({})).recipe.id == expected


def test_recipe_matcher_does_not_substitute_chicken_for_live_salmon_rice_dinner():
    dinner = SimpleNamespace(
        meal_type="dinner",
        foods=tuple(SimpleNamespace(display_name=name) for name in (
            "Salmon", "Brown Rice", "Broccoli",
        )),
    )

    assert match_meal(dinner, load_recipes(), profile_equipment({})).recipe.id == "dinner-salmon-rice"


def test_recipe_matcher_falls_back_when_no_exact_ingredient_overlap_exists():
    plan = _plan()
    unmatched = nutrition_plan.NutritionMeal(
        id="meal-unmatched", name="Dinner", meal_type="dinner", time="19:00",
        foods=(nutrition_plan.NutritionFood("food-unmatched", None, "Prawns", Decimal("200"),
                                            nutrition_plan.NutritionMacros(Decimal("40"), Decimal("0"), Decimal("2"), Decimal("180"))),),
        macros=nutrition_plan.NutritionMacros(Decimal("40"), Decimal("0"), Decimal("2"), Decimal("180")),
    )

    assert match_meal(unmatched, load_recipes(), profile_equipment({})) is None
    assert nutrition_plan.render(plan, "en") == nutrition_plan.render(plan, "en", {})


def _production_meal(meal_type, foods):
    return SimpleNamespace(
        meal_type=meal_type,
        foods=tuple(SimpleNamespace(display_name=name, grams=grams) for name, grams in foods),
    )


def test_recipe_matcher_accepts_the_three_real_bulgarian_production_meals():
    breakfast = _production_meal("breakfast", (
        ("Белтъци, пастьоризирани", "300"),
        ("Овесени ядки, сухи", "150"),
        ("Ябълка, сурова", "150"),
    ))
    lunch = _production_meal("lunch", (
        ("Пилешки гърди, печени без кожа", "300"),
        ("Ориз, сварен", "200"),
        ("Тиквички, сварени", "75"),
        ("Зехтин", "5"),
    ))
    dinner = _production_meal("dinner", (
        ("Пуешко филе, печено", "300"),
        ("Паста, сварена", "200"),
        ("Тиквички, сварени", "75"),
        ("Зехтин", "5"),
        ("Ориз, сварен", "275"),
    ))

    matches = [match_meal(meal, load_recipes(), profile_equipment({})) for meal in (breakfast, lunch, dinner)]

    assert [match.recipe.id for match in matches] == [
        "breakfast-egg-whites-oats-apple", "lunch-chicken-rice", "dinner-turkey-rice-pasta",
    ]
    assert all(len(match.recipe.steps) and len(match.recipe.healthy_cooking_tips) for match in matches)
    assert all(any(char.isdigit() for char in match.recipe.storage) for match in matches)


def test_recipe_matcher_ignores_vegetables_and_auxiliaries_but_not_protein_identity():
    chicken = _production_meal("lunch", (
        ("Chicken breast, roasted", "300"), ("Brown rice, cooked", "200"),
        ("Zucchini, cooked", "75"), ("Olive oil", "5"),
    ))
    salmon = _production_meal("lunch", (
        ("Salmon, grilled", "300"), ("Brown rice, cooked", "200"),
        ("Zucchini, cooked", "75"),
    ))

    assert match_meal(chicken, load_recipes(), profile_equipment({})).recipe.id == "lunch-chicken-rice"
    assert match_meal(salmon, load_recipes(), profile_equipment({})) is None


def test_recipe_matcher_keeps_eggs_and_yogurt_on_their_matching_breakfast_recipe():
    breakfast = _production_meal("breakfast", (
        ("Eggs", "150"), ("Greek yogurt", "200"), ("Oats", "100"), ("Apple", "150"),
    ))

    assert match_meal(breakfast, load_recipes(), profile_equipment({})).recipe.id == (
        "breakfast-eggs-yogurt-oats-apple"
    )


def test_recipe_matcher_uses_largest_carbohydrate_serving_deterministically():
    dinner = _production_meal("dinner", (
        ("Turkey breast", "300"), ("Pasta, cooked", "200"), ("Rice, cooked", "275"),
        ("Zucchini", "75"),
    ))

    first = match_meal(dinner, load_recipes(), profile_equipment({}))
    second = match_meal(dinner, load_recipes(), profile_equipment({}))

    assert first.recipe.id == "dinner-turkey-rice-pasta"
    assert second.recipe.id == first.recipe.id


def test_recipe_equipment_filter_excludes_oven_only_match():
    dinner = _plan().meals[-1]

    assert match_meal(dinner, load_recipes(), frozenset({"pan"})) is None
    assert match_meal(dinner, load_recipes(), frozenset({"oven", "pan"})).recipe.id == "dinner-salmon-rice"
