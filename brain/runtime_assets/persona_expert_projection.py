"""Pure, ID-free communication projections for active workout blueprints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


_RECOVERY_STATES = frozenset({"tired", "fatigued", "poor"})
_EFFECTIVE_RULE_IDS = frozenset({"MCG-001", "GRV-001", "GRV-003", "WNK-003"})
_HOME_EQUIPMENT = frozenset({"bodyweight", "dumbbell", "resistance_band", "bench", "pullup_bar"})


@dataclass(frozen=True)
class PersonaCommunicationProjection:
    """Presentation-only persona signals without corpus identifiers or metadata."""

    guided_explanation: bool = False
    equipment_reality: bool = False
    recovery_sensitive: bool = False
    advanced_autonomy: bool = False

    @property
    def is_none(self) -> bool:
        return not any((self.guided_explanation, self.equipment_reality,
                        self.recovery_sensitive, self.advanced_autonomy))


@dataclass(frozen=True)
class ExpertCommunicationConstraints:
    """Presentation-only effects of the architect-effective expert rules."""

    state_exclusion_reason: bool = False
    state_recovery_reason: bool = False
    single_actionable_cue: bool = False

    @property
    def is_none(self) -> bool:
        return not any((self.state_exclusion_reason, self.state_recovery_reason,
                        self.single_actionable_cue))


def _reduced_demand(blueprint) -> bool:
    return (getattr(blueprint, "session_minutes", 0) <= 25 and
            getattr(blueprint, "mobility_requirement", "") == "gentle_rom")


def build_projections(*, persona_adaptation: Mapping[str, object] | None,
                      authority, blueprint, expert_consensus) -> tuple[
                          PersonaCommunicationProjection, ExpertCommunicationConstraints]:
    """Build deterministic wording constraints from already-approved runtime inputs."""
    adaptation = persona_adaptation or {}
    recovery_state = str(getattr(authority, "recovery_state", "") or "").strip().lower()
    reduced_demand = recovery_state in _RECOVERY_STATES and _reduced_demand(blueprint)
    equipment = {str(item).strip().lower() for item in (getattr(blueprint, "equipment", ()) or ())}
    persona = PersonaCommunicationProjection(
        guided_explanation=bool(adaptation.get("beginner")),
        equipment_reality=bool(adaptation.get("home_equipment")) and "home" in equipment,
        recovery_sensitive=reduced_demand,
        advanced_autonomy=bool(adaptation.get("advanced")),
    )
    rule_ids = set(getattr(expert_consensus, "applicable_rule_ids", ()) or ()) & _EFFECTIVE_RULE_IDS
    exclusion_present = bool(getattr(blueprint, "contraindications", ()) or ())
    constraints = ExpertCommunicationConstraints(
        state_exclusion_reason="MCG-001" in rule_ids and exclusion_present,
        state_recovery_reason=bool(rule_ids & {"GRV-001", "GRV-003", "WNK-003"}) and reduced_demand,
        single_actionable_cue="WNK-003" in rule_ids and bool(getattr(blueprint, "exercise_families", ()) or ()),
    )
    return persona, constraints


def build_training_projections(*, persona_adaptation: Mapping[str, object] | None,
                               profile_facts: Mapping[str, object] | None,
                               locked_preferences: Mapping[str, object] | None,
                               training_plan, exercise_library, expert_consensus) -> tuple[
                                   PersonaCommunicationProjection, ExpertCommunicationConstraints]:
    """Project an immutable deterministic plan into ID-free wording constraints.

    This adapter deliberately reads the completed training plan and registry only
    to establish presentation facts. It returns no exercise identity, policy
    value, score, or recommendation and cannot mutate the plan.
    """
    facts = profile_facts or {}
    preferences = locked_preferences or {}
    sessions = tuple(getattr(training_plan, "sessions", ()) or ())
    if not sessions:
        return PersonaCommunicationProjection(), ExpertCommunicationConstraints()

    equipment = set()
    for session in sessions:
        for prescription in tuple(getattr(session, "prescriptions", ()) or ()):
            exercise = exercise_library.get(
                getattr(prescription, "exercise_id", ""),
                getattr(prescription, "exercise_version", None),
            )
            if exercise is None:
                # A presentation enhancement must abstain if registry grounding
                # is unavailable; it must never infer an equipment statement.
                return PersonaCommunicationProjection(), ExpertCommunicationConstraints()
            equipment.update(item.value for item in exercise.equipment)

    adaptation = persona_adaptation or {}
    recovery_state = str(facts.get("recoveryFeel") or facts.get("sleepQuality") or "").strip().lower()
    delivered_session_minutes = min(
        int(getattr(session, "estimated_duration_minutes", 0) or 0) for session in sessions)
    reduced_demand = recovery_state in _RECOVERY_STATES and 0 < delivered_session_minutes <= 25
    raw_exclusions = preferences.get("exercise_exclusions", ())
    has_exclusion = bool(raw_exclusions)
    persona = PersonaCommunicationProjection(
        guided_explanation=bool(adaptation.get("beginner")),
        equipment_reality=(bool(adaptation.get("home_equipment")) and bool(equipment)
                           and equipment.issubset(_HOME_EQUIPMENT)),
        recovery_sensitive=reduced_demand,
        advanced_autonomy=bool(adaptation.get("advanced")),
    )
    rule_ids = set(getattr(expert_consensus, "applicable_rule_ids", ()) or ()) & _EFFECTIVE_RULE_IDS
    constraints = ExpertCommunicationConstraints(
        state_exclusion_reason="MCG-001" in rule_ids and has_exclusion,
        state_recovery_reason=bool(rule_ids & {"GRV-001", "GRV-003", "WNK-003"}) and reduced_demand,
        single_actionable_cue="WNK-003" in rule_ids and bool(equipment),
    )
    return persona, constraints
