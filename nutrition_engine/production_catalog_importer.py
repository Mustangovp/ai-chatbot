"""Strict, deterministic import for production nutrition-catalog documents.

The importer is an acceptance boundary: it validates a source document and
constructs immutable catalog objects. It never repairs, normalizes, infers, or
enriches imported records.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .production_catalog import (
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
)


class ProductionCatalogImportError(ProductionCatalogError):
    """A source document cannot be accepted as a production catalog."""


_CATALOG_FIELDS = frozenset({"version", "schema_version", "records"})
_RECORD_FIELDS = frozenset({
    "meal_id", "version", "category", "ingredients", "macros", "tags",
    "dietary_compatibility", "preparation_difficulty", "review_status",
    "production_status", "provenance", "approval", "supersedes",
})
_INGREDIENT_FIELDS = frozenset({
    "ingredient_id", "catalog_food_id", "display_name", "serving",
    "macros_per_100g", "provenance",
})
_MACRO_FIELDS = frozenset({"protein_g", "carbs_g", "fat_g", "fiber_g", "kcal"})
_SERVING_FIELDS = frozenset({"default_g", "minimum_g", "maximum_g", "increment_g"})
_PROVENANCE_FIELDS = frozenset({
    "source_name", "source_record_id", "source_version", "retrieved_at_utc",
    "preparation_state", "edible_basis",
})
_APPROVAL_FIELDS = frozenset({
    "nutrition_reviewer", "data_reviewer", "release_approver", "approved_at_utc",
    "evidence_references",
})
_SUPERSEDES_FIELDS = frozenset({"meal_id", "version"})


def load_production_catalog_file(path: str | Path) -> ProductionMealCatalog:
    """Load JSON and accept it only when it satisfies the production schema."""
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ProductionCatalogImportError(f"catalog file cannot be read: {error}") from error
    return import_production_catalog(document)


def import_production_catalog(document: object) -> ProductionMealCatalog:
    """Validate a complete source document and return its immutable artifact."""
    root = _mapping(document, "catalog")
    _exact_fields(root, _CATALOG_FIELDS, "catalog")
    version = _string(root["version"], "catalog.version")
    schema_version = _string(root["schema_version"], "catalog.schema_version")
    if schema_version != PRODUCTION_CATALOG_SCHEMA_VERSION:
        raise ProductionCatalogImportError("catalog.schema_version is unsupported")
    record_documents = _sequence(root["records"], "catalog.records")
    if not record_documents:
        raise ProductionCatalogImportError("catalog.records must not be empty")

    records = tuple(_record(value, f"catalog.records[{index}]")
                    for index, value in enumerate(record_documents))
    _reject_duplicate_record_identities(records)
    try:
        return ProductionMealCatalog(version, schema_version, records)
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"catalog integrity failure: {error}") from error


def _record(value: object, path: str) -> ProductionMealRecord:
    data = _mapping(value, path)
    _exact_fields(data, _RECORD_FIELDS, path)
    ingredients = tuple(
        _ingredient(item, f"{path}.ingredients[{index}]")
        for index, item in enumerate(_sequence(data["ingredients"], f"{path}.ingredients"))
    )
    approval_value = data["approval"]
    approval = None if approval_value is None else _approval(approval_value, f"{path}.approval")
    supersedes_value = data["supersedes"]
    supersedes = None if supersedes_value is None else _supersedes(supersedes_value, f"{path}.supersedes")
    try:
        return ProductionMealRecord(
            _string(data["meal_id"], f"{path}.meal_id"),
            _string(data["version"], f"{path}.version"),
            _string(data["category"], f"{path}.category"),
            ingredients,
            _macros(data["macros"], f"{path}.macros"),
            _strings(data["tags"], f"{path}.tags"),
            _strings(data["dietary_compatibility"], f"{path}.dietary_compatibility"),
            _string(data["preparation_difficulty"], f"{path}.preparation_difficulty"),
            _enum(ReviewStatus, data["review_status"], f"{path}.review_status"),
            _enum(ProductionStatus, data["production_status"], f"{path}.production_status"),
            _provenance(data["provenance"], f"{path}.provenance"),
            approval,
            supersedes,
        )
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"{path}: {error}") from error


def _ingredient(value: object, path: str) -> ProductionIngredient:
    data = _mapping(value, path)
    _exact_fields(data, _INGREDIENT_FIELDS, path)
    try:
        return ProductionIngredient(
            _string(data["ingredient_id"], f"{path}.ingredient_id"),
            _string(data["catalog_food_id"], f"{path}.catalog_food_id"),
            _string(data["display_name"], f"{path}.display_name"),
            _serving(data["serving"], f"{path}.serving"),
            _macros(data["macros_per_100g"], f"{path}.macros_per_100g"),
            _provenance(data["provenance"], f"{path}.provenance"),
        )
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"{path}: {error}") from error


def _macros(value: object, path: str) -> MacroProfile:
    data = _mapping(value, path)
    _exact_fields(data, _MACRO_FIELDS, path)
    try:
        return MacroProfile(*(_decimal(data[field], f"{path}.{field}") for field in (
            "protein_g", "carbs_g", "fat_g", "fiber_g", "kcal",
        )))
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"{path}: {error}") from error


def _serving(value: object, path: str) -> ApprovedServing:
    data = _mapping(value, path)
    _exact_fields(data, _SERVING_FIELDS, path)
    try:
        return ApprovedServing(*(_decimal(data[field], f"{path}.{field}") for field in (
            "default_g", "minimum_g", "maximum_g", "increment_g",
        )))
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"{path}: {error}") from error


def _provenance(value: object, path: str) -> ProvenanceMetadata:
    data = _mapping(value, path)
    _exact_fields(data, _PROVENANCE_FIELDS, path)
    try:
        return ProvenanceMetadata(*(_string(data[field], f"{path}.{field}") for field in (
            "source_name", "source_record_id", "source_version", "retrieved_at_utc",
            "preparation_state", "edible_basis",
        )))
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"{path}: {error}") from error


def _approval(value: object, path: str) -> ApprovalMetadata:
    data = _mapping(value, path)
    _exact_fields(data, _APPROVAL_FIELDS, path)
    try:
        return ApprovalMetadata(
            *(_string(data[field], f"{path}.{field}") for field in (
                "nutrition_reviewer", "data_reviewer", "release_approver", "approved_at_utc",
            )),
            _strings(data["evidence_references"], f"{path}.evidence_references"),
        )
    except ProductionCatalogError as error:
        raise ProductionCatalogImportError(f"{path}: {error}") from error


def _supersedes(value: object, path: str) -> tuple[str, str]:
    data = _mapping(value, path)
    _exact_fields(data, _SUPERSEDES_FIELDS, path)
    return (_string(data["meal_id"], f"{path}.meal_id"),
            _string(data["version"], f"{path}.version"))


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionCatalogImportError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ProductionCatalogImportError(f"{path} keys must be strings")
    return value


def _exact_fields(data: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    missing = sorted(expected - data.keys())
    unexpected = sorted(data.keys() - expected)
    if missing:
        raise ProductionCatalogImportError(f"{path} missing required fields: {', '.join(missing)}")
    if unexpected:
        raise ProductionCatalogImportError(f"{path} contains unsupported fields: {', '.join(unexpected)}")


def _sequence(value: object, path: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ProductionCatalogImportError(f"{path} must be an array")
    return tuple(value)


def _strings(value: object, path: str) -> tuple[str, ...]:
    values = _sequence(value, path)
    strings = tuple(_string(item, f"{path}[{index}]") for index, item in enumerate(values))
    if not strings:
        raise ProductionCatalogImportError(f"{path} must not be empty")
    if len(strings) != len(set(strings)):
        raise ProductionCatalogImportError(f"{path} contains duplicate values")
    return strings


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProductionCatalogImportError(f"{path} must be a non-empty unmodified string")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ProductionCatalogImportError(f"{path} must be a decimal number")
    try:
        return Decimal(str(value))
    except Exception as error:  # Decimal exposes several conversion exception types.
        raise ProductionCatalogImportError(f"{path} must be a decimal number") from error


def _enum(enum_type: type[ReviewStatus] | type[ProductionStatus], value: object,
          path: str) -> ReviewStatus | ProductionStatus:
    text = _string(value, path)
    try:
        return enum_type(text)
    except ValueError as error:
        raise ProductionCatalogImportError(f"{path} has unsupported value: {text}") from error


def _reject_duplicate_record_identities(records: tuple[ProductionMealRecord, ...]) -> None:
    identities = [(record.meal_id, record.version) for record in records]
    if len(identities) != len(set(identities)):
        raise ProductionCatalogImportError("catalog.records contains duplicate meal_id/version identities")
