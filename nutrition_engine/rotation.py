"""Deterministic meal rotation for the isolated nutrition engine.

Rotation only *reorders and selects* among alternatives that already exist. It
holds no macros and never mutates a plan, so it cannot change an optimizer
total. When more than one alternative exists for a slot it guarantees no two
consecutive days repeat the same choice; with a single alternative, repetition
is unavoidable and is reported honestly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence, TypeVar

from .meal_library import LibraryMeal, library_meals_for

T = TypeVar("T")

_ROTATION_SLOTS = ("breakfast", "lunch", "dinner")


def rotate(candidates: Sequence[T], count: int, start: int = 0) -> tuple[T, ...]:
    """Deterministic round-robin selection of `count` items from `candidates`.

    Consecutive picks differ whenever more than one candidate exists. Raises on
    an empty candidate list or negative count.
    """
    if count < 0:
        raise ValueError("count must be non-negative")
    if count and not candidates:
        raise ValueError("cannot rotate an empty candidate list")
    size = len(candidates)
    if size == 0:
        return ()
    base = start % size
    return tuple(candidates[(base + index) % size] for index in range(count))


def has_no_immediate_repeat(sequence: Sequence[object]) -> bool:
    """True if no two consecutive items are equal."""
    return all(sequence[i] != sequence[i + 1] for i in range(len(sequence) - 1))


@dataclass(frozen=True)
class RotationDay:
    day_index: int
    meals_by_slot: tuple[tuple[str, str], ...]  # (slot, meal_id), stable slot order


def rotate_library_days(days: int,
                        candidates_by_slot: Mapping[str, Sequence[LibraryMeal]] | None = None,
                        slots: Sequence[str] = _ROTATION_SLOTS) -> tuple[RotationDay, ...]:
    """Build `days` rotated days of library meals, one entry per slot.

    Each slot rotates independently with a slot-specific offset so a full day is
    unlikely to repeat, and no slot repeats its meal on consecutive days when at
    least two alternatives exist for that slot. Deterministic for identical
    input.
    """
    if days < 0:
        raise ValueError("days must be non-negative")
    resolved: dict[str, Sequence[LibraryMeal]] = {}
    for offset, slot in enumerate(slots):
        pool = list(candidates_by_slot[slot]) if candidates_by_slot else list(library_meals_for(slot))
        if not pool:
            raise ValueError(f"no rotation candidates for slot: {slot}")
        resolved[slot] = pool

    out: list[RotationDay] = []
    for day_index in range(days):
        entries: list[tuple[str, str]] = []
        for offset, slot in enumerate(slots):
            pool = resolved[slot]
            chosen = pool[(day_index + offset) % len(pool)]
            entries.append((slot, chosen.meal_id))
        out.append(RotationDay(day_index, tuple(entries)))
    _assert_no_consecutive_repeat(out, resolved, slots)
    return tuple(out)


def _assert_no_consecutive_repeat(days: Sequence[RotationDay],
                                  resolved: Mapping[str, Sequence[LibraryMeal]],
                                  slots: Sequence[str]) -> None:
    for slot in slots:
        if len(resolved[slot]) < 2:
            continue  # only one option: repetition is unavoidable, not a defect
        picks = [dict(day.meals_by_slot)[slot] for day in days]
        if not has_no_immediate_repeat(picks):
            raise AssertionError(f"rotation repeated slot {slot} on consecutive days")
