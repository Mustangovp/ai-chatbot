"""Runtime adapter and renderer contracts before `/chat` wiring."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from training_engine import (
    MovementPattern,
    TrainingRuntimeError,
    TrainingSplit,
    WorkoutFollowUp,
    WorkoutFollowUpOperation,
    apply_followup,
    build_training_plan,
    load_exercise_library,
    state_for,
)
from training_engine.advisory import TrainingAdvisorySignals, persona_expert_training_signals
from training_engine.completion import completion_projection
from training_engine.cross_session import adapt_from_persisted_history
from training_engine.rationale import build_recommendation_rationale, validate_recommendation_rationale
from training_engine.health_restrictions import (
    FitnessLimitationState,
    UnsupportedHealthRestrictionError,
    clinician_clearance_patterns,
    limitation_excluded_patterns,
    migrate_temporary_fitness_restrictions,
    project_explicit_health_restrictions,
    remove_cleared_clinician_restrictions,
    transition_fitness_limitation,
)
from brain.runtime_assets.expert_consensus import ExpertConsensusResult
from brain.runtime_assets.persona_matcher import PersonaMatchResult
from training_engine import renderer


_PROFILE = {
    "goal": "strength",
    "level": "intermediate",
    "equipment": "bodyweight, dumbbells, bench",
    "recoveryFeel": "fresh",
}
_BEGINNER_PROFILE = {**_PROFILE, "level": "beginner"}


def _persona(*, goals=(), problems=()):
    return PersonaMatchResult(
        "test", "persona", (), tuple(problems), (), tuple(goals), (), 0.9, False, None)


def _expert(*rule_ids):
    return ExpertConsensusResult(
        "test", tuple(rule_ids), (), (), (), (), (), 0.9, not bool(rule_ids))


def _exercise_ids(plan):
    return {item.exercise_id for session in plan.sessions for item in session.prescriptions}


def _movement_patterns(plan):
    return {item.movement_pattern for session in plan.sessions for item in session.prescriptions}


def _persisted_completion_record(plan, *, workout_id="cross-session-1", rpe=None, rir=None,
                                 complete=True, occurred_at="2026-08-14T12:00:00+00:00"):
    """Build the immutable shape saved by ``/api/workout`` without mutating history."""
    projection = completion_projection(plan, load_exercise_library())
    session = projection["sessions"][0]
    exercises = []
    for item in session["exercises"]:
        exercises.append({
            "prescription_id": item["prescription_id"],
            "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"],
            "completed_sets": item["prescribed_sets"] if complete else item["prescribed_sets"] - 1,
            "completed_repetitions": item["rep_max"],
            "completed_load": None,
            "completed_rpe": rpe,
            "completed_rir": rir,
        })
    return {
        "id": workout_id,
        "completion": 100,
        "occurred_at": occurred_at,
        "exercises": {"workout_completion": {
            "workout_id": workout_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "session_id": session["session_id"],
            "completion_timestamp": occurred_at,
            "exercises": exercises,
        }},
    }


def test_runtime_adapter_builds_a_deterministic_traceable_training_plan():
    first = build_training_plan(recommendation_blueprint_id="rec-runtime", facts=_PROFILE)
    second = build_training_plan(recommendation_blueprint_id="rec-runtime", facts=_PROFILE)

    assert first == second
    assert first.selection_blueprint_id.startswith("selection:rec-runtime:")
    assert all(item.exercise_id and item.exercise_version
               for item in first.sessions[0].prescriptions)
    rendered = renderer.render_delivery(first, load_exercise_library(), (), "en")
    assert "Goblet Squat" in rendered
    assert "RPE" in rendered and "tempo" in rendered


def test_runtime_adapter_fails_closed_for_unsupported_or_safety_constrained_profile():
    with pytest.raises(TrainingRuntimeError, match="unsupported equipment"):
        build_training_plan(recommendation_blueprint_id="rec-runtime", facts={**_PROFILE, "equipment": "office"})
    with pytest.raises(TrainingRuntimeError, match="safety constraints"):
        build_training_plan(recommendation_blueprint_id="rec-runtime", facts={**_PROFILE, "injuries": "knee pain"})


def test_explicit_clinician_restrictions_are_typed_removal_only_constraints():
    facts = {**_PROFILE, "equipment": "gym", "clinicianRestrictions": "Do not do overhead pressing."}
    advised = TrainingAdvisorySignals(("dumbbell.overhead_press",))
    plan = build_training_plan(
        recommendation_blueprint_id="rec-clinician", facts=facts,
        advisory_preferred_exercise_ids=advised.preferred_exercise_ids,
        locked_preferences={"exercise_exclusions": ("bodyweight.push_up",)},
    )

    assert MovementPattern.VERTICAL_PUSH not in _movement_patterns(plan)
    assert "dumbbell.overhead_press" not in _exercise_ids(plan)
    assert "bodyweight.push_up" not in _exercise_ids(plan)


def test_explicit_restriction_survives_harder_followup_and_bulgarian_mapping():
    facts = {**_PROFILE, "equipment": "gym", "clinicianRestrictions": "Без преса над глава."}
    previous = state_for(build_training_plan(recommendation_blueprint_id="rec-clinician-prior", facts=facts))
    harder = apply_followup(
        followup=WorkoutFollowUp(WorkoutFollowUpOperation.INCREASE_DIFFICULTY),
        previous=previous, recommendation_blueprint_id="rec-clinician-followup", facts=facts,
    )

    assert MovementPattern.VERTICAL_PUSH not in _movement_patterns(previous.plan)
    assert MovementPattern.VERTICAL_PUSH not in _movement_patterns(harder)


def test_unknown_explicit_health_restriction_fails_closed_without_diagnosis_inference():
    with pytest.raises(TrainingRuntimeError, match="explicit health restriction is unsupported"):
        build_training_plan(
            recommendation_blueprint_id="rec-clinician-unknown",
            facts={**_PROFILE, "clinicianRestrictions": "Avoid strenuous activity until further notice."},
        )

    assert project_explicit_health_restrictions({"healthNotes": "diabetes"}).source_count == 0
    with pytest.raises(UnsupportedHealthRestrictionError):
        project_explicit_health_restrictions({"medicalRestrictions": "No strenuous activity."})


def test_self_reported_fitness_limitation_has_deterministic_recovery_lifecycle_en_and_bg():
    active = transition_fitness_limitation(None, "My shoulder hurts with overhead pressing.")
    recovering = transition_fitness_limitation(active, "My shoulder feels much better today.")
    cleared = transition_fitness_limitation(recovering, "My shoulder doesn't hurt anymore.")
    returned = transition_fitness_limitation(cleared, "My shoulder hurts again.")

    assert active.state is FitnessLimitationState.ACTIVE
    assert recovering.state is FitnessLimitationState.RECOVERING
    assert limitation_excluded_patterns(recovering) == frozenset({MovementPattern.VERTICAL_PUSH})
    assert cleared.state is FitnessLimitationState.CLEARED
    assert limitation_excluded_patterns(cleared) == frozenset()
    assert returned.state is FitnessLimitationState.ACTIVE

    bg_active = transition_fitness_limitation(None, "Рамото ме боли при преса над глава.")
    bg_recovering = transition_fitness_limitation(bg_active, "Рамото ми е по-добре.")
    bg_cleared = transition_fitness_limitation(bg_recovering, "Рамото вече не ме боли.")
    assert bg_active.state is FitnessLimitationState.ACTIVE
    assert bg_recovering.state is FitnessLimitationState.RECOVERING
    assert bg_cleared.state is FitnessLimitationState.CLEARED


def test_generic_improvement_cannot_clear_clinician_restriction_but_explicit_clearance_can():
    restriction = "My doctor told me not to do overhead pressing."
    generic = clinician_clearance_patterns("I'm feeling better.")
    assert generic == frozenset()
    assert remove_cleared_clinician_restrictions(
        restriction, generic, clinician_field=True,
    ) == (restriction,)
    explicit = clinician_clearance_patterns(
        "My doctor cleared me to press overhead again.")
    assert explicit == frozenset({MovementPattern.VERTICAL_PUSH})
    assert remove_cleared_clinician_restrictions(
        restriction, explicit, clinician_field=True,
    ) == ()
    bg_explicit = clinician_clearance_patterns(
        "Лекарят ми каза, че мога отново да правя преса над глава.")
    assert bg_explicit == frozenset({MovementPattern.VERTICAL_PUSH})


def test_legacy_self_reported_pain_restriction_migrates_without_touching_hard_exclusion():
    temporary = "Avoid overhead pressing because my shoulder hurts."
    hard = "Do not include push-ups."
    remaining, limitation = migrate_temporary_fitness_restrictions([temporary, hard])

    assert remaining == (hard,)
    assert limitation.state is FitnessLimitationState.ACTIVE


def test_renderer_accepts_only_explanatory_llm_json_and_never_changes_plan_values():
    plan = build_training_plan(recommendation_blueprint_id="rec-runtime", facts=_PROFILE)
    prompt = renderer.render_prompt(plan, "en")
    assert "Do not add, remove, reorder, or change exercises" in prompt
    assert "one to three non-empty explanation strings" in prompt
    assert renderer.verified_explanations(json.dumps({"explanations": ["Keep each rep controlled."]})) == (
        "Keep each rep controlled.",
    )
    assert "Why this workout:" in renderer.default_explanations(plan, "en")[0]
    with pytest.raises(ValueError, match="response contract"):
        renderer.verified_explanations(json.dumps({"explanations": [], "plan": "modified"}))


def test_renderer_localizes_bulgarian_delivery_and_completion_projection_together():
    plan = build_training_plan(
        recommendation_blueprint_id="rec-bg",
        facts={
            "goal": "strength", "level": "beginner", "equipment": "home",
            "recoveryFeel": "fresh",
        },
    )
    library = load_exercise_library()

    delivery = renderer.render_delivery(plan, library, (), "bg")
    completion = renderer.render_completion_projection(plan, library, "bg")

    assert "| \u0423\u043f\u0440\u0430\u0436\u043d\u0435\u043d\u0438\u0435 | \u0421\u0435\u0440\u0438\u0438 | \u041f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f | \u041f\u043e\u0447\u0438\u0432\u043a\u0430 | \u0411\u0435\u043b\u0435\u0436\u043a\u0430 |" in delivery
    assert "\u041b\u0438\u0446\u0435\u0432\u0430 \u043e\u043f\u043e\u0440\u0430 \u043d\u0430 \u0441\u0442\u0435\u043d\u0430" in delivery
    assert "Wall Push-Up" not in delivery
    assert completion["sessions"][0]["exercises"][1]["display_name"] in delivery
    assert completion["sessions"][0]["exercises"][1]["exercise_id"] == "bodyweight.wall_push_up"


def test_recommendation_rationale_uses_only_real_constraint_and_followup_factors():
    facts = {**_PROFILE, "equipment": "gym"}
    excluded = frozenset({MovementPattern.VERTICAL_PUSH})
    previous = state_for(build_training_plan(
        recommendation_blueprint_id="rec-rationale-prior", facts=facts,
        excluded_movement_patterns=excluded,
    ))
    harder = apply_followup(
        followup=WorkoutFollowUp(WorkoutFollowUpOperation.INCREASE_DIFFICULTY),
        previous=previous, recommendation_blueprint_id="rec-rationale-harder", facts=facts,
        external_excluded_movement_patterns=excluded,
    )
    before = harder
    rationale = build_recommendation_rationale(
        harder, facts=facts, active_constraint_patterns=excluded,
        followup_direction="increased", has_previous_workout=True,
    )

    assert harder == before
    assert rationale == {
        "version": "training-rationale-v1",
        "used": [
            {"kind": "active_constraint", "value": "vertical_push"},
            {"kind": "recent_workout", "value": "previous_session"},
        ],
        "changed": [
            {"kind": "excluded_movement", "value": "vertical_push"},
            {"kind": "difficulty_adjustment", "value": "increased"},
        ],
        "reason_code": "progressed_within_constraints",
    }
    assert MovementPattern.VERTICAL_PUSH not in _movement_patterns(harder)


def test_recommendation_rationale_omits_unused_factors_and_malformed_values_fail_closed():
    plan = build_training_plan(recommendation_blueprint_id="rec-rationale-normal", facts=_PROFILE)
    rationale = build_recommendation_rationale(plan, facts=_PROFILE)

    assert [item["kind"] for item in rationale["used"]] == ["training_goal", "experience_capacity"]
    assert all(item["kind"] != "active_constraint" for item in rationale["used"])
    assert all(item["kind"] != "difficulty_adjustment" for item in rationale["changed"])
    assert validate_recommendation_rationale({
        **rationale,
        "used": [{"kind": "active_constraint", "value": "not-a-pattern"}],
    }) is None
    completion = renderer.render_completion_projection(
        plan, load_exercise_library(), recommendation_rationale={"unsafe": "ignored"})
    assert "recommendation_rationale" not in completion


def test_cross_session_easy_comparable_completion_progresses_with_native_bounds():
    plan = build_training_plan(recommendation_blueprint_id="rec-cross-easy", facts=_PROFILE)
    for workout_id, rpe, rir in (
            ("cross-session-rpe-only", "6", None),
            ("cross-session-rir-only", None, 4),
            ("cross-session-consistent", "6", 4)):
        result = adapt_from_persisted_history(
            plan, [_persisted_completion_record(plan, workout_id=workout_id, rpe=rpe, rir=rir)],
            now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc),
        )

        assert result.applied is True
        assert result.comparable_session is True
        assert result.change == "sets"
        assert result.plan != plan
        assert all(after.sets == before.sets + 1
                   for after, before in zip(result.plan.sessions[0].prescriptions,
                                            plan.sessions[0].prescriptions))


def test_cross_session_hard_or_incomplete_evidence_preserves_baseline_plan():
    plan = build_training_plan(recommendation_blueprint_id="rec-cross-hard", facts=_PROFILE)
    for workout_id, rpe, rir in (
            ("cross-session-rpe-hard", "9", None),
            ("cross-session-rir-hard", None, 0),
            ("cross-session-contradictory", "6", 0),
            ("cross-session-no-effort", None, None)):
        result = adapt_from_persisted_history(
            plan, [_persisted_completion_record(plan, workout_id=workout_id, rpe=rpe, rir=rir)],
            now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc),
        )
        assert result.plan == plan and result.applied is False
    incomplete = adapt_from_persisted_history(
        plan, [_persisted_completion_record(plan, rpe="6", rir=4, complete=False)],
        now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc),
    )

    assert incomplete.plan == plan and incomplete.applied is False
    assert incomplete.comparable_session is False


def test_cross_session_requires_comparable_history_and_preserves_constraints():
    excluded = frozenset({MovementPattern.VERTICAL_PUSH})
    plan = build_training_plan(
        recommendation_blueprint_id="rec-cross-restricted", facts={**_PROFILE, "equipment": "gym"},
        excluded_movement_patterns=excluded,
    )
    unrelated = _persisted_completion_record(plan, rpe="6", rir=4)
    unrelated["exercises"]["workout_completion"]["exercises"] = [{
        "prescription_id": "legacy-lower-1", "exercise_id": "legacy.lower_squat",
        "exercise_version": "v1", "completed_sets": 3, "completed_repetitions": 10,
        "completed_load": None, "completed_rpe": "6", "completed_rir": 4,
    }, {
        "prescription_id": "legacy-lower-2", "exercise_id": "legacy.lower_hinge",
        "exercise_version": "v1", "completed_sets": 3, "completed_repetitions": 10,
        "completed_load": None, "completed_rpe": "6", "completed_rir": 4,
    }]
    unmatched = adapt_from_persisted_history(
        plan, [unrelated], now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc))
    adapted = adapt_from_persisted_history(
        plan, [_persisted_completion_record(plan, workout_id="cross-session-restricted", rpe="6", rir=4)],
        now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc),
    )
    rationale = build_recommendation_rationale(
        adapted.plan, facts={**_PROFILE, "equipment": "gym"},
        active_constraint_patterns=excluded, cross_session_change=adapted.change,
    )

    assert unmatched.plan == plan and unmatched.applied is False
    assert adapted.applied is True
    assert MovementPattern.VERTICAL_PUSH not in _movement_patterns(adapted.plan)
    assert rationale["used"] == [
        {"kind": "active_constraint", "value": "vertical_push"},
        {"kind": "comparable_session", "value": "comfortable_completed"},
    ]
    assert rationale["changed"][1]["kind"] == "cross_session_progression"


def test_cross_session_malformed_or_duplicate_history_fails_closed_deterministically():
    plan = build_training_plan(recommendation_blueprint_id="rec-cross-malformed", facts=_PROFILE)
    valid = _persisted_completion_record(plan, workout_id="duplicate-session", rpe="6", rir=4)
    malformed = {"completion": 100, "occurred_at": "not-a-time", "exercises": {}}

    first = adapt_from_persisted_history(
        plan, [malformed, valid, dict(valid)], now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc))
    second = adapt_from_persisted_history(
        plan, [dict(valid), malformed, valid], now=datetime(2026, 8, 14, 13, tzinfo=timezone.utc))

    assert first.plan == plan and first.applied is False
    assert second == first


@pytest.mark.parametrize(("requested_split", "expected_sessions"), (
    ("full_body", ((
        MovementPattern.SQUAT, MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL,
        MovementPattern.HINGE, MovementPattern.CORE_ANTI_EXTENSION,
    ),) * 2),
    ("upper_lower", (
        (MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PUSH),
        (MovementPattern.SQUAT, MovementPattern.LUNGE, MovementPattern.HINGE,
         MovementPattern.CORE_ANTI_EXTENSION),
    )),
    ("push_pull_legs", (
        (MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH),
        (MovementPattern.HORIZONTAL_PULL,),
        (MovementPattern.SQUAT, MovementPattern.LUNGE, MovementPattern.HINGE,
         MovementPattern.CORE_ANTI_EXTENSION),
    )),
))
def test_runtime_constructs_the_explicit_requested_split_deterministically(
        requested_split, expected_sessions):
    facts = {**_PROFILE, "equipment": "gym", "training_split": requested_split}
    first = build_training_plan(recommendation_blueprint_id="rec-split", facts=facts)
    second = build_training_plan(recommendation_blueprint_id="rec-split", facts=facts)

    assert first == second
    assert first.training_split is TrainingSplit(requested_split)
    assert tuple(tuple(item.movement_pattern for item in session.prescriptions)
                 for session in first.sessions) == expected_sessions
    assert all(item.exercise_id and item.exercise_version and item.selection_policy_version
               and item.construction_policy_version for session in first.sessions
               for item in session.prescriptions)


def test_home_beginner_profile_uses_the_bodyweight_push_and_horizontal_pull():
    plan = build_training_plan(
        recommendation_blueprint_id="rec-home", facts={
            "goal": "strength", "level": "beginner", "equipment": "home",
            "recoveryFeel": "fresh",
        })

    exercise_ids = {item.exercise_id for item in plan.sessions[0].prescriptions}
    assert {"bodyweight.wall_push_up", "bodyweight.table_row"}.issubset(exercise_ids)
    exercise = load_exercise_library().require("bodyweight.table_row")
    assert exercise.movement_pattern is MovementPattern.HORIZONTAL_PULL
    assert exercise.safety_notes and exercise.progression.next_exercise_ids


def test_split_support_rejects_unknown_split_without_falling_back_to_full_body():
    with pytest.raises(TrainingRuntimeError, match="unsupported training split"):
        build_training_plan(recommendation_blueprint_id="rec-split", facts={
            **_PROFILE, "training_split": "bro split",
        })


def test_persona_signal_changes_only_a_safe_deterministic_rank_tie():
    signals = persona_expert_training_signals(persona_match=_persona(goals=("strength",)))
    baseline = build_training_plan(recommendation_blueprint_id="rec-base", facts=_PROFILE)
    advised = build_training_plan(
        recommendation_blueprint_id="rec-advised", facts=_PROFILE,
        advisory_preferred_exercise_ids=signals.preferred_exercise_ids,
    )

    assert "bodyweight.table_row" in _exercise_ids(baseline)
    assert "dumbbell.row" in _exercise_ids(advised)


def test_expert_consensus_changes_only_a_safe_deterministic_rank_tie():
    signals = persona_expert_training_signals(expert_consensus=_expert("CLR-002"))
    baseline = build_training_plan(recommendation_blueprint_id="rec-base", facts=_BEGINNER_PROFILE)
    advised = build_training_plan(
        recommendation_blueprint_id="rec-advised", facts=_BEGINNER_PROFILE,
        advisory_preferred_exercise_ids=signals.preferred_exercise_ids,
    )

    assert "bodyweight.incline_push_up" in _exercise_ids(baseline)
    assert "bodyweight.wall_push_up" in _exercise_ids(advised)


def test_hard_exclusions_beat_persona_and_expert_preferences():
    persona = persona_expert_training_signals(persona_match=_persona(goals=("strength",)))
    expert = persona_expert_training_signals(expert_consensus=_expert("CLR-002"))
    persona_plan = build_training_plan(
        recommendation_blueprint_id="rec-persona-exclusion", facts=_PROFILE,
        locked_preferences={"exercise_exclusions": ("dumbbell.row",)},
        advisory_preferred_exercise_ids=persona.preferred_exercise_ids,
    )
    expert_plan = build_training_plan(
        recommendation_blueprint_id="rec-expert-exclusion", facts=_BEGINNER_PROFILE,
        locked_preferences={"exercise_exclusions": ("bodyweight.wall_push_up",)},
        advisory_preferred_exercise_ids=expert.preferred_exercise_ids,
    )

    assert "dumbbell.row" not in _exercise_ids(persona_plan)
    assert "bodyweight.table_row" in _exercise_ids(persona_plan)
    assert "bodyweight.wall_push_up" not in _exercise_ids(expert_plan)
    assert "bodyweight.incline_push_up" in _exercise_ids(expert_plan)


def test_shoulder_review_and_followup_exclusions_beat_advisory_preferences():
    signals = TrainingAdvisorySignals(("dumbbell.overhead_press",))
    with pytest.raises(TrainingRuntimeError, match="safety constraints"):
        build_training_plan(
            recommendation_blueprint_id="rec-shoulder", facts={**_PROFILE, "healthNotes": "shoulder pain"},
            advisory_preferred_exercise_ids=signals.preferred_exercise_ids,
        )

    facts = {**_PROFILE, "equipment": "gym", "training_split": "upper_lower"}
    previous = state_for(build_training_plan(recommendation_blueprint_id="rec-prior", facts=facts))
    followup = WorkoutFollowUp(
        WorkoutFollowUpOperation.EXCLUDE_MOVEMENT_FAMILY,
        excluded_patterns=frozenset({MovementPattern.VERTICAL_PUSH}),
    )
    revised = apply_followup(
        followup=followup, previous=previous, recommendation_blueprint_id="rec-followup", facts=facts,
        advisory_preferred_exercise_ids=signals.preferred_exercise_ids,
    )

    assert MovementPattern.VERTICAL_PUSH not in {
        item.movement_pattern for session in revised.sessions for item in session.prescriptions
    }
    assert "dumbbell.overhead_press" not in _exercise_ids(revised)


def test_unknown_advisory_exercise_is_ignored_and_disabled_signals_keep_output_identical():
    ignored = persona_expert_training_signals(
        persona_match=_persona(goals=("unknown.exercise",), problems=("unknown.exercise",)),
        expert_consensus=_expert("UNKNOWN-001"),
    )
    baseline = build_training_plan(recommendation_blueprint_id="rec-compatible", facts=_PROFILE)
    no_signals = build_training_plan(
        recommendation_blueprint_id="rec-compatible", facts=_PROFILE,
        advisory_preferred_exercise_ids=(),
    )
    unknown_signal = build_training_plan(
        recommendation_blueprint_id="rec-compatible", facts=_PROFILE,
        advisory_preferred_exercise_ids=("unknown.exercise",),
    )

    assert ignored.preferred_exercise_ids == ()
    assert baseline == no_signals == unknown_signal
    assert "unknown.exercise" not in _exercise_ids(unknown_signal)
