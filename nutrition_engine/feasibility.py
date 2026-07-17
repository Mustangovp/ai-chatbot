"""Stable, user-safe feasibility codes for the isolated optimizer."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import OptimizedNutritionDay


class FeasibilityCode(str, Enum):
    FEASIBLE = "feasible"
    CALORIE_TARGET_UNREACHABLE = "calorie_target_unreachable"
    PROTEIN_MINIMUM_UNREACHABLE = "protein_minimum_unreachable"
    PROTEIN_CAP_CONFLICT = "protein_cap_conflict"
    EXCLUSIONS_REMOVE_ALL_PROTEIN_SOURCES = "exclusions_remove_all_protein_sources"
    MEAL_STRUCTURE_INFEASIBLE = "meal_structure_infeasible"
    PORTION_BOUNDS_INFEASIBLE = "portion_bounds_infeasible"
    UNSUPPORTED_DIET = "unsupported_diet"
    CATALOG_NOT_PRODUCTION_READY = "catalog_not_production_ready"
    CATALOG_VERSION_MISMATCH = "catalog_version_mismatch"
    SEARCH_LIMIT_REACHED = "search_limit_reached"


@dataclass(frozen=True)
class FeasibilityResult:
    code: FeasibilityCode
    day: OptimizedNutritionDay | None = None
    conflicts: tuple[str, ...] = ()

    @property
    def feasible(self) -> bool:
        return self.code is FeasibilityCode.FEASIBLE
