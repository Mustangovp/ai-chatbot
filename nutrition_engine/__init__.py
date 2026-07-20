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
from .meal_library import (
    MEAL_CATEGORIES,
    NUTRITION_LIBRARY_VERSION,
    MealCandidate,
    MealIngredient,
    NutritionKnowledgeLibrary,
    build_nutrition_knowledge_library,
)
from .meal_selection import MealMacroBounds, MealSelectionEngine, MealSelectionQuery
from .plan_construction import (
    PLAN_CONSTRUCTION_VERSION,
    ConstructedMeal,
    MealDistribution,
    NutritionConstructionError,
    NutritionConstructionRequest,
    NutritionPlanBlueprint,
    NutritionPlanConstructionEngine,
    NutritionTargetPolicy,
    calculate_target_macros,
)
from .production_catalog import (
    MACRO_KCAL_TOLERANCE,
    PRODUCTION_CATALOG_SCHEMA_VERSION,
    ApprovalMetadata,
    ApprovedServing,
    MacroProfile,
    ProductionCatalogError,
    ProductionIngredient,
    ProductionMealCatalog,
    ProductionMealRecord,
    ProductionStatus,
    ProvenanceMetadata,
    ReviewStatus,
    validate_version_upgrade,
)
from .production_catalog_importer import (
    ProductionCatalogImportError,
    import_production_catalog,
    load_production_catalog_file,
)

__all__ = [
    "Catalog", "CatalogGovernance", "DietConstraints", "FeasibilityCode",
    "FeasibilityResult", "FoodItem", "MealSelection", "NutritionTargets",
    "PracticalityPolicy", "load_catalog_file", "load_catalog_records", "optimize",
    "MEAL_CATEGORIES", "NUTRITION_LIBRARY_VERSION", "MealCandidate", "MealIngredient",
    "NutritionKnowledgeLibrary", "build_nutrition_knowledge_library", "MealMacroBounds",
    "MealSelectionEngine", "MealSelectionQuery",
    "PLAN_CONSTRUCTION_VERSION", "ConstructedMeal", "MealDistribution",
    "NutritionConstructionError", "NutritionConstructionRequest", "NutritionPlanBlueprint",
    "NutritionPlanConstructionEngine", "NutritionTargetPolicy", "calculate_target_macros",
    "MACRO_KCAL_TOLERANCE", "PRODUCTION_CATALOG_SCHEMA_VERSION", "ApprovalMetadata",
    "ApprovedServing", "MacroProfile", "ProductionCatalogError", "ProductionIngredient",
    "ProductionMealCatalog", "ProductionMealRecord", "ProductionStatus",
    "ProvenanceMetadata", "ReviewStatus", "validate_version_upgrade",
    "ProductionCatalogImportError", "import_production_catalog",
    "load_production_catalog_file",
]
