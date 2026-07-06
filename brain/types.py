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


class Verdict(str, Enum):                       # S4 Appropriateness Gate output
    GO = "GO"                                   # train within S1's envelope
    MODIFY = "MODIFY"                           # train only inside a tightened envelope
    NOT_YET = "NOT_YET"                          # precondition unmet today (reversible)
    NO_TRAIN = "NO_TRAIN"                        # training is the wrong answer (categorical)


@dataclass(frozen=True)
class Intervention:                             # S5 Intervention Selector output
    # kind ∈ training | recovery | sleep | walk | breathing | mobility |
    #        stress_reduction | nutrition | conversation | medical_followup | crisis_support
    kind: str
    rationale_key: str                          # coach-safe rationale key; never a diagnosis


@dataclass
class Decision:
    """The single object the cascade produces; the ONLY thing Inspector, Replay,
    and Regression consume. Carries the station outputs plus a deterministic,
    trace-ready payload (`trace_core`) that the Inspector merely wraps."""
    verdict: "Verdict"
    intervention: Intervention
    generate_training: bool
    halt: bool
    verdict_confidence: float
    constraints: "ConstraintSet"                # forward ref (defined below) — quoted so the
    envelope: "CapacityEnvelope"                # annotation is not evaluated at class-def time
    s2: "S2State"
    need_vector: list
    decision_id: str
    model: str | None
    trace_core: dict = field(default_factory=dict)


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


# ── S2 · Readiness + Red-Flag Sentinel ───────────────────────────────────────
class Urgency(str, Enum):                       # verification GAP-α (Addendum 01)
    EMERGENCY = "EMERGENCY_now"                 # stop now; emergency services / protocol
    URGENT = "URGENT_soon"                      # halt exertion; see a clinician promptly
    ROUTINE = "ROUTINE_mention"                 # soft — keep within limits; worth raising


@dataclass(frozen=True)
class RedFlag:
    class_key: str                # INTERNAL routing key — never rendered to a user (R7/§6)
    urgency: Urgency
    route_target: str             # emergency_services | stop_and_treat | crisis_support | clinician_prompt | gp_soft
    message_key: str              # curated, non-diagnostic template key — never a clinical label
    source: str = "message"       # where it was detected: "message" | "prior_turn" (Addendum 02)


@dataclass
class S2State:
    readiness: float              # 0..1 — today's capacity within the envelope
    readiness_conf: float         # 0..1
    red_flags: list = field(default_factory=list)   # list[RedFlag]
    halt: bool = False            # structural halt — cascade stops at S2 (Addendum 02 A2-0)

    def by_urgency(self, u: "Urgency") -> list:
        return [f for f in self.red_flags if f.urgency == u]

    def emergencies(self) -> list:
        return self.by_urgency(Urgency.EMERGENCY)
