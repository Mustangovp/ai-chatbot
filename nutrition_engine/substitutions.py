"""Deterministic, approved food substitutions for the isolated nutrition engine.

This module is pure metadata: it answers "what may replace this food?" from a
fixed, curated set of chains. It never reads or writes macros, quantities, or
calories, so it can never change an optimizer total. Applying a substitution to
an actual plan is the caller's responsibility and must re-run the optimizer;
this module only decides whether a swap is approved and in what deterministic
order alternatives are offered.
"""
from __future__ import annotations

# Ordered, curated chains. Order is the deterministic preference order.
# Every id is a catalog food_id. A chain groups foods that fill the same role.
_CHAINS: tuple[tuple[str, ...], ...] = (
    # Main animal/plant proteins (the canonical chicken -> tofu ladder).
    ("dev_chicken_breast_cooked", "dev_turkey_breast_cooked", "dev_lean_beef_cooked",
     "dev_lean_pork_cooked", "dev_white_fish_cooked", "dev_salmon_cooked", "dev_tofu_firm"),
    # Legume proteins.
    ("dev_lentils_cooked", "dev_chickpeas_cooked", "dev_pink_beans_cooked"),
    # Canned/lean fish proteins.
    ("dev_tuna_water_drained", "dev_tuna_canned"),
    # Dairy/breakfast proteins.
    ("dev_greek_yogurt_nonfat", "dev_greek_yogurt_2pct", "dev_cottage_cheese"),
    # Starches.
    ("dev_rice_cooked", "dev_potatoes_boiled", "dev_pasta_cooked", "dev_bulgur_cooked",
     "dev_quinoa_cooked", "dev_sweet_potato_cooked"),
    # Cooked/leafy vegetables.
    ("dev_broccoli_cooked", "dev_spinach_cooked", "dev_zucchini_cooked", "dev_mixed_salad"),
    # Raw vegetables.
    ("dev_broccoli_raw", "dev_carrots_raw", "dev_cabbage_raw", "dev_green_pepper",
     "dev_tomatoes", "dev_cucumber"),
    # Fruits.
    ("dev_banana", "dev_apple", "dev_orange", "dev_blueberries", "dev_blackberries"),
    # Whole-food fats.
    ("dev_almonds", "dev_walnuts", "dev_avocado"),
)


def _validate_chains() -> None:
    seen: set[str] = set()
    for chain in _CHAINS:
        if len(chain) < 2:
            raise ValueError("a substitution chain needs at least two foods")
        for food_id in chain:
            if food_id in seen:
                raise ValueError(f"food {food_id} appears in more than one chain")
            seen.add(food_id)


_validate_chains()

_CHAIN_OF: dict[str, tuple[str, ...]] = {
    food_id: chain for chain in _CHAINS for food_id in chain
}


def approved_substitutes(food_id: str) -> tuple[str, ...]:
    """All approved replacements for a food, in deterministic preference order.

    Returns the other members of the food's chain, chain order preserved. An
    unknown or non-substitutable food returns an empty tuple.
    """
    chain = _CHAIN_OF.get(food_id)
    if chain is None:
        return ()
    return tuple(other for other in chain if other != food_id)


def is_supported_substitution(original_id: str, replacement_id: str) -> bool:
    """True only when both foods share a curated chain and differ."""
    if original_id == replacement_id:
        return False
    chain = _CHAIN_OF.get(original_id)
    return chain is not None and replacement_id in chain


def next_substitute(food_id: str, exclude: frozenset[str] = frozenset()) -> str | None:
    """First approved substitute not in `exclude`, or None when none remain."""
    for candidate in approved_substitutes(food_id):
        if candidate not in exclude:
            return candidate
    return None


def chain_for(food_id: str) -> tuple[str, ...]:
    """The full ordered chain a food belongs to, or () if it has none."""
    return _CHAIN_OF.get(food_id, ())
