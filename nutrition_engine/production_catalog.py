"""Immutable, versioned production meal-catalog contract.

This module is deliberately isolated from chat and runtime routing. It models
and validates only production-approved meal records; it does not promote the
development food catalog or infer approval evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable


PRODUCTION_CATALOG_SCHEMA_VERSION = "production-meal-catalog-v1"
MEAL_CATEGORIES = frozenset({
    "breakfast", "snack", "lunch", "dinner", "pre_workout", "post_workout",
})
PREPARATION_DIFFICULTIES = frozenset({"no_cook", "easy", "moderate"})
MACRO_KCAL_TOLERANCE = Decimal("15")


class ProductionCatalogError(ValueError):
    """A production meal record or catalog violates its governance contract."""


class ReviewStatus(str, Enum):
    DRAFT = "DRAFT"
    NUTRITION_REVIEW = "NUTRITION_REVIEW"
    MACRO_VERIFIED = "MACRO_VERIFIED"
    SERVING_VERIFIED = "SERVING_VERIFIED"
    PRODUCTION_APPROVED = "PRODUCTION_APPROVED"
    PRODUCTION_READY = "PRODUCTION_READY"


class ProductionStatus(str, Enum):
    NOT_PRODUCTION_READY = "NOT_PRODUCTION_READY"
    PRODUCTION_READY = "PRODUCTION_READY"


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ProductionCatalogError(f"{field} must be decimal") from error
    if result < 0:
        raise ProductionCatalogError(f"{field} must be non-negative")
    return result


def _tokens(values: Iterable[str]) -> tuple[str, ...]:
    """Validate categorical labels without normalizing imported source values."""
    if isinstance(values, (str, bytes)):
        raise ProductionCatalogError("token collection must not be a string")
    try:
        result = tuple(values)
    except TypeError as error:
        raise ProductionCatalogError("token collection must be iterable") from error
    if not result or any(not isinstance(value, str) or not value or value != value.strip()
                         for value in result):
        raise ProductionCatalogError("token collection contains an invalid value")
    if len(result) != len(set(result)):
        raise ProductionCatalogError("token collection contains duplicate values")
    return result


def _semantic_version(value: str) -> tuple[int, int, int]:
    parts = str(value).strip().split(".")
    if len(parts) != 3:
        raise ProductionCatalogError("version must be major.minor.patch")
    try:
        result = tuple(int(part) for part in parts)
    except ValueError as error:
        raise ProductionCatalogError("version must be numeric") from error
    if any(part < 0 for part in result):
        raise ProductionCatalogError("version must be non-negative")
    return result


@dataclass(frozen=True)
class MacroProfile:
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal
    kcal: Decimal

    def __post_init__(self) -> None:
        for field in ("protein_g", "carbs_g", "fat_g", "fiber_g", "kcal"):
            object.__setattr__(self, field, _decimal(getattr(self, field), field))
        estimated = self.protein_g * Decimal("4") + self.carbs_g * Decimal("4") + self.fat_g * Decimal("9")
        if abs(self.kcal - estimated) > MACRO_KCAL_TOLERANCE:
            raise ProductionCatalogError("macro kcal consistency exceeds tolerance")

    def plus(self, other: "MacroProfile") -> "MacroProfile":
        return MacroProfile(
            self.protein_g + other.protein_g,
            self.carbs_g + other.carbs_g,
            self.fat_g + other.fat_g,
            self.fiber_g + other.fiber_g,
            self.kcal + other.kcal,
        )

    def scale(self, multiplier: Decimal) -> "MacroProfile":
        return MacroProfile(
            self.protein_g * multiplier,
            self.carbs_g * multiplier,
            self.fat_g * multiplier,
            self.fiber_g * multiplier,
            self.kcal * multiplier,
        )

    @classmethod
    def zero(cls) -> "MacroProfile":
        return cls(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))


@dataclass(frozen=True)
class ProvenanceMetadata:
    source_name: str
    source_record_id: str
    source_version: str
    retrieved_at_utc: str
    preparation_state: str
    edible_basis: str

    def __post_init__(self) -> None:
        for field in (
            "source_name", "source_record_id", "source_version", "retrieved_at_utc",
            "preparation_state", "edible_basis",
        ):
            if not str(getattr(self, field)).strip():
                raise ProductionCatalogError(f"provenance {field} is required")


@dataclass(frozen=True)
class ApprovalMetadata:
    nutrition_reviewer: str
    data_reviewer: str
    release_approver: str
    approved_at_utc: str
    evidence_references: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("nutrition_reviewer", "data_reviewer", "release_approver", "approved_at_utc"):
            if not str(getattr(self, field)).strip():
                raise ProductionCatalogError(f"approval {field} is required")
        evidence = tuple(str(value).strip() for value in self.evidence_references if str(value).strip())
        if not evidence:
            raise ProductionCatalogError("approval evidence references are required")
        object.__setattr__(self, "evidence_references", evidence)


@dataclass(frozen=True)
class ApprovedServing:
    default_g: Decimal
    minimum_g: Decimal
    maximum_g: Decimal
    increment_g: Decimal

    def __post_init__(self) -> None:
        for field in ("default_g", "minimum_g", "maximum_g", "increment_g"):
            object.__setattr__(self, field, _decimal(getattr(self, field), field))
        if self.minimum_g <= 0 or self.increment_g <= 0:
            raise ProductionCatalogError("serving minimum and increment must be positive")
        if not self.minimum_g <= self.default_g <= self.maximum_g:
            raise ProductionCatalogError("default serving must be within approved bounds")
        if (self.default_g - self.minimum_g) % self.increment_g != 0:
            raise ProductionCatalogError("default serving must align to increment")
        if (self.maximum_g - self.minimum_g) % self.increment_g != 0:
            raise ProductionCatalogError("maximum serving must align to increment")

    @property
    def minimum_multiplier(self) -> Decimal:
        return self.minimum_g / self.default_g

    @property
    def maximum_multiplier(self) -> Decimal:
        return self.maximum_g / self.default_g

    def validate_grams(self, grams: Decimal) -> None:
        grams = _decimal(grams, "grams")
        if not self.minimum_g <= grams <= self.maximum_g:
            raise ProductionCatalogError("serving grams exceed approved bounds")
        if (grams - self.minimum_g) % self.increment_g != 0:
            raise ProductionCatalogError("serving grams do not align to approved increment")


@dataclass(frozen=True)
class ProductionIngredient:
    ingredient_id: str
    catalog_food_id: str
    display_name: str
    serving: ApprovedServing
    macros_per_100g: MacroProfile
    provenance: ProvenanceMetadata

    def __post_init__(self) -> None:
        if not str(self.ingredient_id).strip() or not str(self.catalog_food_id).strip():
            raise ProductionCatalogError("ingredient identity is required")
        if not str(self.display_name).strip():
            raise ProductionCatalogError("ingredient display_name is required")

    @property
    def default_macros(self) -> MacroProfile:
        return self.macros_for(self.serving.default_g)

    def macros_for(self, grams: Decimal) -> MacroProfile:
        self.serving.validate_grams(grams)
        return self.macros_per_100g.scale(grams / Decimal("100"))


@dataclass(frozen=True)
class ProductionMealRecord:
    meal_id: str
    version: str
    category: str
    ingredients: tuple[ProductionIngredient, ...]
    macros: MacroProfile
    tags: tuple[str, ...]
    dietary_compatibility: tuple[str, ...]
    preparation_difficulty: str
    review_status: ReviewStatus
    production_status: ProductionStatus
    provenance: ProvenanceMetadata
    approval: ApprovalMetadata | None = None
    supersedes: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if not str(self.meal_id).strip():
            raise ProductionCatalogError("meal_id is required")
        _semantic_version(self.version)
        if self.category not in MEAL_CATEGORIES:
            raise ProductionCatalogError("meal category is unsupported")
        if not self.ingredients:
            raise ProductionCatalogError("meal requires ingredients")
        ingredient_ids = [ingredient.ingredient_id for ingredient in self.ingredients]
        food_ids = [ingredient.catalog_food_id for ingredient in self.ingredients]
        if len(ingredient_ids) != len(set(ingredient_ids)) or len(food_ids) != len(set(food_ids)):
            raise ProductionCatalogError("meal ingredients must be unique")
        if self.preparation_difficulty not in PREPARATION_DIFFICULTIES:
            raise ProductionCatalogError("preparation difficulty is unsupported")
        object.__setattr__(self, "tags", _tokens(self.tags))
        object.__setattr__(self, "dietary_compatibility", _tokens(self.dietary_compatibility))
        if not self.tags or not self.dietary_compatibility:
            raise ProductionCatalogError("meal tags and dietary compatibility are required")
        expected = MacroProfile.zero()
        for ingredient in self.ingredients:
            expected = expected.plus(ingredient.default_macros)
        if self.macros != expected:
            raise ProductionCatalogError("meal macros must equal approved ingredient totals")
        self._validate_lifecycle()
        if self.supersedes is not None:
            predecessor_id, predecessor_version = self.supersedes
            if predecessor_id != self.meal_id:
                raise ProductionCatalogError("successor must retain meal_id")
            _semantic_version(predecessor_version)
            if _semantic_version(self.version) <= _semantic_version(predecessor_version):
                raise ProductionCatalogError("successor version must increase")

    def _validate_lifecycle(self) -> None:
        final = self.review_status is ReviewStatus.PRODUCTION_READY
        if final != (self.production_status is ProductionStatus.PRODUCTION_READY):
            raise ProductionCatalogError("review and production status are inconsistent")
        if final and not isinstance(self.approval, ApprovalMetadata):
            raise ProductionCatalogError("production-ready record requires approval metadata")
        if not final and self.approval is not None:
            raise ProductionCatalogError("non-production record cannot carry production approval")

    def validate_production_promotion(self) -> None:
        if self.review_status is not ReviewStatus.PRODUCTION_READY:
            raise ProductionCatalogError("record has not completed production lifecycle")
        if self.production_status is not ProductionStatus.PRODUCTION_READY:
            raise ProductionCatalogError("record is not production-ready")
        if self.approval is None:
            raise ProductionCatalogError("production approval is missing")
        for ingredient in self.ingredients:
            ingredient.serving.validate_grams(ingredient.serving.default_g)
            ingredient.macros_for(ingredient.serving.minimum_g)
            ingredient.macros_for(ingredient.serving.maximum_g)


@dataclass(frozen=True)
class ProductionMealCatalog:
    version: str
    schema_version: str
    records: tuple[ProductionMealRecord, ...]

    def __post_init__(self) -> None:
        _semantic_version(self.version)
        if self.schema_version != PRODUCTION_CATALOG_SCHEMA_VERSION:
            raise ProductionCatalogError("unsupported production catalog schema")
        if not self.records:
            raise ProductionCatalogError("production catalog requires records")
        identities = [(record.meal_id, record.version) for record in self.records]
        if len(identities) != len(set(identities)):
            raise ProductionCatalogError("duplicate meal record identity")
        for record in self.records:
            record.validate_production_promotion()


def validate_version_upgrade(previous: ProductionMealRecord,
                             successor: ProductionMealRecord) -> None:
    """Validate immutable supersession without overwriting historical records."""
    if successor.supersedes != (previous.meal_id, previous.version):
        raise ProductionCatalogError("successor must explicitly supersede prior record")
    if successor.meal_id != previous.meal_id:
        raise ProductionCatalogError("successor must retain immutable meal_id")
    if _semantic_version(successor.version) <= _semantic_version(previous.version):
        raise ProductionCatalogError("successor version must increase")
    successor.validate_production_promotion()
