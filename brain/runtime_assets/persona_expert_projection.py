"""Pure, ID-free communication projections for active workout blueprints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from brain.runtime_assets.expert_consensus import EXPERT_CONSENSUS_VERSION


_RECOVERY_STATES = frozenset({"tired", "fatigued", "poor"})
_EFFECTIVE_RULE_IDS = frozenset({"MCG-001", "GRV-001", "GRV-003", "WNK-003", "WNK-011"})
_HOME_EQUIPMENT = frozenset({"bodyweight", "dumbbell", "resistance_band", "bench", "pullup_bar"})
_CUE_COMPLEXITY_BY_EXPERIENCE = {
    "beginner": "simple",
    "intermediate": "standard",
    "advanced": "advanced",
}
_CUE_COMPLEXITIES = frozenset(_CUE_COMPLEXITY_BY_EXPERIENCE.values())
_GLP_REASON_TYPES = frozenset({
    "restriction", "equipment", "experience", "goal", "progression",
    "recovery_adjustment", "substitution", "exclusion",
})
_GLP_PRIORITY = (
    "restriction", "exclusion", "substitution", "progression", "recovery_adjustment",
    "equipment", "experience", "goal",
)
# Profile facts identify the source; only a delivered-plan reason proves adaptation.
_GLP_DELIVERED_REASON_TYPES = {
    "validated_substitution": "substitution",
    "reduced_demand": "recovery_adjustment",
    "equipment_adaptation": "equipment",
    "experience_adaptation": "experience",
    "goal_adaptation": "goal",
}
_HIGHER_AUTHORITY_MOVEMENT_KEYS = frozenset({
    "clinicianRestrictions", "medicalRestrictions", "healthRestrictions", "trainingRestrictions",
})


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
    cue_complexity: str | None = None
    adaptation_rationale: object | None = None

    @property
    def is_none(self) -> bool:
        return not any((self.state_exclusion_reason, self.state_recovery_reason,
                        self.single_actionable_cue, self.cue_complexity in _CUE_COMPLEXITIES,
                        _valid_adaptation_rationale(self.adaptation_rationale) is not None))


@dataclass(frozen=True)
class AdaptationRationale:
    """Closed, ID-free explanation of an adaptation already fixed in a plan."""

    reason_type: str
    plan_decision: str


def _valid_adaptation_rationale(value: object) -> AdaptationRationale | None:
    if not isinstance(value, AdaptationRationale):
        return None
    if value.reason_type not in _GLP_REASON_TYPES or not isinstance(value.plan_decision, str):
        return None
    expected = f"existing_{value.reason_type}"
    return value if value.plan_decision == expected else None


def _values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _glp_001_rationale(*, facts: Mapping[str, object], preferences: Mapping[str, object],
                        training_plan, exercise_library) -> AdaptationRationale | None:
    """Select one pre-existing plan reason in the established authority order."""
    candidates: set[str] = set()
    if any(_values(facts.get(key)) for key in _HIGHER_AUTHORITY_MOVEMENT_KEYS):
        candidates.add("restriction")
    if _values(preferences.get("exercise_exclusions")):
        candidates.add("exclusion")
    revision_reasons = tuple(getattr(training_plan, "revision_reasons", ()) or ())
    for reason in revision_reasons:
        reason_type = _GLP_DELIVERED_REASON_TYPES.get(reason)
        if reason_type == "equipment" and not _values(facts.get("equipment")):
            continue
        if reason_type == "experience" and _canonical_experience(facts) is None:
            continue
        if reason_type == "goal" and not str(facts.get("goal") or "").strip():
            continue
        if reason_type is not None:
            candidates.add(reason_type)
    if tuple(getattr(training_plan, "progression_decision_ids", ()) or ()):
        candidates.add("progression")
    for reason_type in _GLP_PRIORITY:
        if reason_type in candidates:
            return AdaptationRationale(reason_type, f"existing_{reason_type}")
    return None


def _canonical_experience(facts: Mapping[str, object]) -> str | None:
    values = []
    for key in ("level", "experience_level"):
        value = facts.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if normalized not in _CUE_COMPLEXITY_BY_EXPERIENCE:
            return None
        values.append(normalized)
    if not values or len(set(values)) != 1:
        return None
    return values[0]


def _has_higher_authority_movement_instruction(facts: Mapping[str, object], preferences: Mapping[str, object]) -> bool:
    if any(facts.get(key) not in (None, "", (), []) for key in _HIGHER_AUTHORITY_MOVEMENT_KEYS):
        return True
    return bool(preferences.get("exercise_exclusions") or preferences.get("training_restrictions"))


def _cue_complexity(*, rule_ids: set[str], expert_consensus, experience: str | None,
                    higher_authority_instruction: bool) -> str | None:
    """Return a closed cue style only under the existing WNK-003 one-cue ceiling."""
    if (getattr(expert_consensus, "version", None) != EXPERT_CONSENSUS_VERSION
            or not {"WNK-003", "WNK-011"}.issubset(rule_ids)
            or higher_authority_instruction
            or experience is None):
        return None
    return _CUE_COMPLEXITY_BY_EXPERIENCE.get(experience)


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
    facts = getattr(authority, "verified_facts", {}) or {}
    experience = _canonical_experience(facts)
    constraints = ExpertCommunicationConstraints(
        state_exclusion_reason="MCG-001" in rule_ids and exclusion_present,
        state_recovery_reason=bool(rule_ids & {"GRV-001", "GRV-003", "WNK-003"}) and reduced_demand,
        single_actionable_cue="WNK-003" in rule_ids and bool(getattr(blueprint, "exercise_families", ()) or ()),
        cue_complexity=_cue_complexity(
            rule_ids=rule_ids, expert_consensus=expert_consensus, experience=experience,
            higher_authority_instruction=_has_higher_authority_movement_instruction(
                facts, getattr(authority, "locked_preferences", {}) or {})),
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
    experience = _canonical_experience(facts)
    constraints = ExpertCommunicationConstraints(
        state_exclusion_reason="MCG-001" in rule_ids and has_exclusion,
        state_recovery_reason=bool(rule_ids & {"GRV-001", "GRV-003", "WNK-003"}) and reduced_demand,
        single_actionable_cue="WNK-003" in rule_ids and bool(equipment),
        cue_complexity=_cue_complexity(
            rule_ids=rule_ids, expert_consensus=expert_consensus, experience=experience,
            higher_authority_instruction=_has_higher_authority_movement_instruction(facts, preferences)),
        adaptation_rationale=_glp_001_rationale(
            facts=facts, preferences=preferences, training_plan=training_plan,
            exercise_library=exercise_library),
    )
    return persona, constraints
