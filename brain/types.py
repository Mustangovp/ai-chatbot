"""
APEX Brain — shared types.

M1 subset: the S1 Somatic Constraint Model outputs only. Verdict / Urgency /
RedFlag / Intervention / Decision are added with their own organs in later
milestones — nothing here anticipates unbuilt stations.

A Constraint is always a MOVEMENT (e.g. "valsalva"), never a diagnosis. The
coach-safe explanation is carried as a reason_key, never a clinical label.
"""
from dataclasses import dataclass, field
from enum import Enum


class ConstraintTier(str, Enum):
    ABSOLUTE = "absolute"   # never program this movement
    RELATIVE = "relative"   # modify / avoid load / limit range
    MONITOR = "monitor"     # permit but watch


@dataclass(frozen=True)
class Constraint:
    movement: str                 # a movement/intensity, never a diagnosis
    tier: ConstraintTier
    reason_key: str               # coach-safe key; never a clinical label


_TIER_RANK = {ConstraintTier.MONITOR: 0, ConstraintTier.RELATIVE: 1, ConstraintTier.ABSOLUTE: 2}


@dataclass
class ConstraintSet:
    items: list = field(default_factory=list)   # list[Constraint]

    def add(self, c: Constraint) -> None:
        """Add a constraint, keeping the STRICTEST tier per movement."""
        for i, existing in enumerate(self.items):
            if existing.movement == c.movement:
                if _TIER_RANK[c.tier] > _TIER_RANK[existing.tier]:
                    self.items[i] = c
                return
        self.items.append(c)

    def forbids(self, movement: str) -> bool:
        """True iff this movement is absolutely contraindicated."""
        return any(c.movement == movement and c.tier == ConstraintTier.ABSOLUTE
                   for c in self.items)

    def movements(self, tier: ConstraintTier | None = None) -> list:
        return [c.movement for c in self.items if tier is None or c.tier == tier]

    def is_empty(self) -> bool:
        return not self.items


@dataclass
class CapacityEnvelope:
    intensity_ceiling: float      # 0..1
    complexity_ceiling: float     # 0..1
    volume_ceiling: float         # 0..1
    supported: bool               # balance-supported required
    confidence: float             # 0..1 — how much the profile actually specified
