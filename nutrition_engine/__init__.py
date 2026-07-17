"""Isolated Nutrition Engine V2 foundation.

This package has no production request-path integration in Phase 1.
"""

from .catalog import Catalog, CatalogGovernance, load_catalog_file, load_catalog_records
from .feasibility import FeasibilityCode, FeasibilityResult
from .models import (
    DietConstraints,
    FoodItem,
    MealSelection,
    NutritionTargets,
    PracticalityPolicy,
)
from .optimizer import optimize

__all__ = [
    "Catalog", "CatalogGovernance", "DietConstraints", "FeasibilityCode",
    "FeasibilityResult", "FoodItem", "MealSelection", "NutritionTargets",
    "PracticalityPolicy", "load_catalog_file", "load_catalog_records", "optimize",
]
