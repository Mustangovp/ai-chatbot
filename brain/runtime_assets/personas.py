"""Pure promotion of the frozen 140-scenario acceptance corpus into runtime assets.

This module deliberately uses only literal fixture fields and literal text matches. It
does not identify users, call models, write data, or participate in production routing.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


PERSONA_CORPUS_VERSION = "runtime-personas-v1"
_FIXTURES = Path(__file__).resolve().parents[1] / "corpus" / "corpus_fixtures.json"
_VERDICTS = {"GO", "MODIFY", "N/A", "NOT_YET", "NO_TRAIN"}
_EXPERIENCE_LEVELS = {"unknown", "beginner", "intermediate", "advanced"}
_EQUIPMENT_CONTEXTS = {"unknown", "home", "gym", "bodyweight"}

# Tags are intentionally phrased as literal mentions, rather than inferred diagnoses.
_LITERAL_TAGS = {
    "problem": {
        "mentions_sleep": ("sleep", "slept", "insomnia"),
        "mentions_stress": ("stress", "stressed", "exams"),
        "mentions_pain": ("pain", "ache", "sore", "injury"),
        "mentions_weight": ("weight", "fat", "cut", "shredded"),
        "mentions_motivation": ("motivation", "motivated", "discipline"),
    },
    "constraint": {
        "mentions_no_rest": ("no rest", "every day"),
        "mentions_restriction": ("1000 calories", "one meal", "fasting"),
        "mentions_pain": ("pain", "ache", "injury"),
        "mentions_time": ("minutes", "hours", "busy"),
    },
    "goal": {
        "strength": ("strength", "bench", "strong"),
        "muscle_gain": ("muscle", "hypertrophy", "gain"),
        "fat_loss": ("fat loss", "lose", "cut", "shredded"),
        "endurance": ("run", "marathon", "endurance", "cardio"),
    },
    "nutrition": {
        "mentions_calories": ("calorie", "calories", "kcal"),
        "mentions_fasting": ("fasting", "one meal"),
        "mentions_food": ("food", "diet", "protein", "meal"),
        "mentions_dietary_restriction": ("vegan", "vegetarian", "allergy", "gluten"),
    },
    "recovery": {
        "mentions_sleep": ("sleep", "slept", "insomnia"),
        "mentions_fatigue": ("fatigue", "tired", "exhausted"),
        "mentions_stress": ("stress", "stressed", "exams"),
    },
}


@dataclass(frozen=True)
class RuntimePersona:
    id: str
    version: str
    cluster: str
    problem_tags: tuple[str, ...]
    constraint_tags: tuple[str, ...]
    goal_tags: tuple[str, ...]
    experience_level: str
    equipment_context: str
    recovery_context: tuple[str, ...]
    nutrition_context: tuple[str, ...]
    medical_or_safety_flags: tuple[str, ...]
    expected_decision_behavior: tuple[tuple[str, Any], ...]
    prohibited_assumptions: tuple[str, ...]
    source_fixture_id: str


def _text(fixture: dict[str, Any]) -> str:
    return "\n".join(str(value) for value in fixture.get("messages", ())).lower()


def _tags(text: str, kind: str) -> tuple[str, ...]:
    return tuple(sorted(tag for tag, phrases in _LITERAL_TAGS[kind].items()
                        if any(phrase in text for phrase in phrases)))


def _context(text: str, kind: str) -> str:
    if kind == "experience":
        for value in ("beginner", "advanced", "intermediate"):
            if value in text:
                return value
    if kind == "equipment":
        for value in ("home", "gym", "bodyweight"):
            if value in text:
                return value
    return "unknown"


def promote_fixture(fixture: dict[str, Any]) -> RuntimePersona:
    """Create one conservative asset using only the immutable fixture's own evidence."""
    text = _text(fixture)
    safety = []
    if fixture.get("expected_red_flag"):
        safety.append("fixture_red_flag")
    if fixture.get("expected_refuses_training"):
        safety.append("fixture_refuses_training")
    behavior = (
        ("verdict", fixture["expected_verdict"]),
        ("generate", bool(fixture["expected_generate"])),
        ("refuses_training", bool(fixture["expected_refuses_training"])),
    )
    return RuntimePersona(
        id=fixture["id"], version=PERSONA_CORPUS_VERSION, cluster=fixture["cluster"],
        problem_tags=_tags(text, "problem"), constraint_tags=_tags(text, "constraint"),
        goal_tags=_tags(text, "goal"), experience_level=_context(text, "experience"),
        equipment_context=_context(text, "equipment"), recovery_context=_tags(text, "recovery"),
        nutrition_context=_tags(text, "nutrition"), medical_or_safety_flags=tuple(safety),
        expected_decision_behavior=behavior, prohibited_assumptions=(),
        source_fixture_id=fixture["id"],
    )


def _fixtures(path: Path = _FIXTURES) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_runtime_personas(records: tuple[RuntimePersona, ...], fixtures: list[dict[str, Any]]) -> None:
    expected_ids = tuple(f"P-{number:03d}" for number in range(1, 141))
    if len(records) != 140 or tuple(record.id for record in records) != expected_ids:
        raise ValueError("runtime persona IDs must be the complete P-001..P-140 sequence")
    fixture_map = {fixture.get("id"): fixture for fixture in fixtures}
    if len(fixture_map) != 140 or tuple(fixture.get("id") for fixture in fixtures) != expected_ids:
        raise ValueError("source fixtures must be the complete P-001..P-140 sequence")
    for record in records:
        if record.version != PERSONA_CORPUS_VERSION or not record.cluster:
            raise ValueError(f"invalid runtime persona metadata: {record.id}")
        if record.source_fixture_id != record.id or record.source_fixture_id not in fixture_map:
            raise ValueError(f"invalid source reference: {record.id}")
        if record.experience_level not in _EXPERIENCE_LEVELS or record.equipment_context not in _EQUIPMENT_CONTEXTS:
            raise ValueError(f"invalid context enum: {record.id}")
        behavior = dict(record.expected_decision_behavior)
        fixture = fixture_map[record.id]
        if behavior != {"verdict": fixture["expected_verdict"], "generate": bool(fixture["expected_generate"]),
                        "refuses_training": bool(fixture["expected_refuses_training"])}:
            raise ValueError(f"unsupported decision behavior: {record.id}")
        if behavior["verdict"] not in _VERDICTS:
            raise ValueError(f"invalid verdict: {record.id}")
        if record != promote_fixture(fixture):
            raise ValueError(f"unsupported inferred facts: {record.id}")


def load_runtime_personas() -> tuple[RuntimePersona, ...]:
    """Load and validate the deterministic, non-activated runtime persona assets."""
    fixtures = _fixtures()
    records = tuple(promote_fixture(fixture) for fixture in fixtures)
    validate_runtime_personas(records, fixtures)
    return records
