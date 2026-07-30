"""
APEX — Shoulder Safety Constraint Tests.

Covers:
- Constraint library: shoulder tokens and constraint generation
- Shoulder exercise index: load metadata per exercise
- Shoulder validator: blueprint validation and fail-closed behaviour
- Composer grounding: safety claims blocked without proof
- Phrase mapping: BG/EN parity
- Integration: medical hold authority over follow-up requests
"""
import pytest

# ── Constraint library ────────────────────────────────────────────────────────

from brain.constraint_library import detect_conditions, constraints_for, CONDITION_TOKENS
from brain.types import ConstraintTier


class TestShoulderConstraintLibrary:

    def test_left_shoulder_bg_phrase_maps_to_left_shoulder_pain(self):
        conditions = detect_conditions("лявото рамо ме боли")
        assert "left_shoulder_pain" in conditions

    def test_left_shoulder_bg_alternative_phrase(self):
        conditions = detect_conditions("заболя ме лявото рамо")
        assert "left_shoulder_pain" in conditions

    def test_right_shoulder_bg_phrase(self):
        conditions = detect_conditions("болка в дясното рамо")
        assert "right_shoulder_pain" in conditions

    def test_bilateral_shoulder_bg_no_load(self):
        conditions = detect_conditions("без натоварване на рамото")
        assert "shoulder_pain" in conditions

    def test_bilateral_shoulder_bg_no_involvement(self):
        conditions = detect_conditions("рамото да не участва")
        assert "shoulder_pain" in conditions

    def test_bilateral_shoulder_bg_without_involvement(self):
        conditions = detect_conditions("без участие на рамото")
        assert "shoulder_pain" in conditions

    def test_bilateral_shoulder_bg_no_exercises_for_shoulder(self):
        conditions = detect_conditions("без упражнения за рамо")
        assert "shoulder_pain" in conditions

    def test_shoulder_pain_en(self):
        conditions = detect_conditions("I have shoulder pain")
        assert "shoulder_pain" in conditions

    def test_left_shoulder_en(self):
        conditions = detect_conditions("avoid loading the left shoulder")
        assert "left_shoulder_pain" in conditions

    def test_right_shoulder_en(self):
        conditions = detect_conditions("avoid loading the right shoulder")
        assert "right_shoulder_pain" in conditions

    def test_no_shoulder_involvement_en(self):
        conditions = detect_conditions("workout without shoulder involvement")
        assert "shoulder_pain" in conditions

    def test_do_not_use_shoulder_en(self):
        conditions = detect_conditions("do not use my shoulder")
        assert "shoulder_pain" in conditions

    def test_shoulder_pain_produces_absolute_constraints(self):
        constraints = constraints_for("shoulder_pain")
        absolute = [c for c in constraints if c.tier == ConstraintTier.ABSOLUTE]
        assert len(absolute) > 0, "shoulder_pain must produce ABSOLUTE constraints"

    def test_shoulder_pain_forbids_push(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "push" in movements

    def test_shoulder_pain_forbids_plank(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "plank" in movements

    def test_shoulder_pain_forbids_row(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "row" in movements

    def test_shoulder_pain_forbids_push_up(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "push_up" in movements

    def test_shoulder_pain_forbids_goblet_hold(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "goblet_hold" in movements

    def test_shoulder_pain_forbids_dumbbell_hinge(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "dumbbell_hinge" in movements

    def test_shoulder_pain_forbids_upper_limb_external_load(self):
        constraints = constraints_for("shoulder_pain")
        movements = {c.movement for c in constraints if c.tier == ConstraintTier.ABSOLUTE}
        assert "upper_limb_external_load" in movements

    def test_left_shoulder_produces_absolute_constraints(self):
        constraints = constraints_for("left_shoulder_pain")
        absolute = [c for c in constraints if c.tier == ConstraintTier.ABSOLUTE]
        assert len(absolute) > 0

    def test_right_shoulder_produces_absolute_constraints(self):
        constraints = constraints_for("right_shoulder_pain")
        absolute = [c for c in constraints if c.tier == ConstraintTier.ABSOLUTE]
        assert len(absolute) > 0

    def test_unrelated_text_does_not_produce_shoulder(self):
        conditions = detect_conditions("back pain and knee pain")
        assert "shoulder_pain" not in conditions
        assert "left_shoulder_pain" not in conditions

    def test_empty_text_no_shoulder(self):
        conditions = detect_conditions("")
        assert "shoulder_pain" not in conditions


# ── Exercise shoulder index ───────────────────────────────────────────────────

from brain.shoulder_exercise_index import (
    shoulder_load_movements_for,
    exercise_violates_shoulder_constraint,
    SHOULDER_LOAD_MOVEMENTS,
)


class TestShoulderExerciseIndex:

    def test_push_up_is_shoulder_loading(self):
        load = shoulder_load_movements_for("push_up")
        assert "push_up" in load or "push" in load

    def test_incline_push_up_is_shoulder_loading(self):
        load = shoulder_load_movements_for("incline_push_up")
        assert bool(load & SHOULDER_LOAD_MOVEMENTS)

    def test_front_plank_is_shoulder_loading(self):
        load = shoulder_load_movements_for("front_plank")
        assert "plank" in load

    def test_table_row_is_shoulder_loading(self):
        load = shoulder_load_movements_for("table_row")
        assert "row" in load

    def test_one_arm_dumbbell_row_is_shoulder_loading(self):
        load = shoulder_load_movements_for("one_arm_dumbbell_row")
        assert bool(load & SHOULDER_LOAD_MOVEMENTS)

    def test_goblet_squat_is_shoulder_loading(self):
        load = shoulder_load_movements_for("goblet_squat")
        assert "goblet_hold" in load

    def test_dumbbell_rdl_is_shoulder_loading(self):
        load = shoulder_load_movements_for("dumbbell_romanian_deadlift")
        assert "dumbbell_hinge" in load

    def test_external_load_dumbbell_lunge_is_shoulder_loading(self):
        load = shoulder_load_movements_for("dumbbell_lunge")
        assert "upper_limb_external_load" in load

    def test_bodyweight_squat_is_safe(self):
        load = shoulder_load_movements_for("bodyweight_squat")
        assert not bool(load & SHOULDER_LOAD_MOVEMENTS)

    def test_glute_bridge_is_safe(self):
        load = shoulder_load_movements_for("glute_bridge")
        assert not bool(load & SHOULDER_LOAD_MOVEMENTS)

    def test_seated_leg_extension_is_safe(self):
        load = shoulder_load_movements_for("seated_leg_extension")
        assert not bool(load & SHOULDER_LOAD_MOVEMENTS)

    def test_calf_raise_is_safe(self):
        load = shoulder_load_movements_for("calf_raise")
        assert not bool(load & SHOULDER_LOAD_MOVEMENTS)

    def test_unknown_exercise_fails_closed(self):
        load = shoulder_load_movements_for("totally_made_up_exercise_xyz")
        assert "unknown_shoulder_load" in load

    def test_exercise_violates_push_up_forbidden(self):
        forbidden = frozenset({"push_up", "push"})
        assert exercise_violates_shoulder_constraint("push_up", forbidden)

    def test_exercise_violates_plank_forbidden(self):
        forbidden = frozenset({"plank"})
        assert exercise_violates_shoulder_constraint("front_plank", forbidden)

    def test_exercise_violates_unknown_fails_closed(self):
        forbidden = frozenset({"unknown_shoulder_load"})
        assert exercise_violates_shoulder_constraint("unknown_exercise_abc", forbidden)

    def test_safe_exercise_does_not_violate(self):
        forbidden = frozenset({"push_up", "plank", "row", "goblet_hold"})
        assert not exercise_violates_shoulder_constraint("bodyweight_squat", forbidden)


# ── Shoulder validator ────────────────────────────────────────────────────────

from brain.shoulder_validator import (
    validate_blueprint,
    is_shoulder_constraint_active,
    ShoulderSafetyProof,
)
from brain.types import ConstraintSet, Constraint, ConstraintTier


def _shoulder_cset():
    """Build a ConstraintSet matching shoulder_pain constraints."""
    cset = ConstraintSet()
    for movement in (
        "push_up", "plank", "row", "push", "pull", "goblet_hold",
        "dumbbell_hinge", "upper_limb_external_load", "unknown_shoulder_load",
    ):
        cset.add(Constraint(movement, ConstraintTier.ABSOLUTE, "shoulder_load_forbidden"))
    return cset


class TestShoulderValidator:

    def test_no_constraint_passes_always(self):
        cset = ConstraintSet()
        exercises = [{"canonical_id": "push_up"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is True
        assert result.proof.shoulder_constraint_active is False

    def test_push_up_violates_shoulder_constraint(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "push_up"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False
        assert "push_up" in result.violating_ids

    def test_incline_push_up_violates(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "incline_push_up"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_plank_violates(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "front_plank"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_row_violates(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "table_row"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_goblet_squat_violates(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "goblet_squat"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_dumbbell_rdl_violates(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "dumbbell_romanian_deadlift"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_unknown_exercise_fails_closed(self):
        cset = _shoulder_cset()
        exercises = [{"canonical_id": "completely_new_exercise_xyz"}]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False, "Unknown exercise must fail closed"

    def test_safe_exercises_pass(self):
        cset = _shoulder_cset()
        exercises = [
            {"canonical_id": "bodyweight_squat"},
            {"canonical_id": "glute_bridge"},
            {"canonical_id": "seated_leg_extension"},
        ]
        result = validate_blueprint(exercises, cset)
        assert result.passed is True
        assert result.proof.shoulder_constraint_active is True
        assert result.proof.shoulder_constraint_validated is True
        assert result.proof.violating_exercise_count == 0

    def test_mixed_plan_fails_with_correct_violators(self):
        cset = _shoulder_cset()
        exercises = [
            {"canonical_id": "bodyweight_squat"},
            {"canonical_id": "push_up"},
            {"canonical_id": "glute_bridge"},
            {"canonical_id": "front_plank"},
        ]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False
        assert "push_up" in result.violating_ids
        assert "front_plank" in result.violating_ids
        assert "bodyweight_squat" not in result.violating_ids
        assert "glute_bridge" not in result.violating_ids

    def test_proof_may_claim_safe_only_when_validated(self):
        cset = _shoulder_cset()
        # Safe plan
        safe = [{"canonical_id": "bodyweight_squat"}, {"canonical_id": "glute_bridge"}]
        result = validate_blueprint(safe, cset)
        assert result.proof.may_claim_safe is True

        # Unsafe plan
        unsafe = [{"canonical_id": "push_up"}]
        result2 = validate_blueprint(unsafe, cset)
        assert result2.proof.may_claim_safe is False

    def test_no_constraint_proof_may_not_claim_safe(self):
        cset = ConstraintSet()
        result = validate_blueprint([{"canonical_id": "push_up"}], cset)
        assert result.proof.may_claim_safe is False

    def test_is_shoulder_constraint_active_true(self):
        cset = _shoulder_cset()
        assert is_shoulder_constraint_active(cset) is True

    def test_is_shoulder_constraint_active_false_empty(self):
        cset = ConstraintSet()
        assert is_shoulder_constraint_active(cset) is False


# ── Composer grounding ────────────────────────────────────────────────────────

from conversation_composer import compose, render_prompt, build_policy
from brain.shoulder_validator import ShoulderSafetyProof


class _MockDecision:
    """Minimal mock decision for build_policy tests."""
    outcome = "recommend"   # build_policy reads getattr(decision, 'outcome', 'converse')
    halt = False
    generate_training = True


def _base_policy():
    return build_policy(
        decision=_MockDecision(),
        message="направи ми тренировка",
        conversation=[],
        voice=False,
        session_start=False,
        blueprint_present=True,
    )


class TestComposerGrounding:

    def test_composer_without_proof_does_not_claim_safe(self):
        policy = _base_policy()
        frame = compose(policy, shoulder_safety_proof=None)
        prompt = render_prompt(frame, "bg")
        # No safety claim emitted when proof is absent
        assert "SHOULDER SAFETY GROUNDING" not in prompt

    def test_composer_with_failed_proof_suppresses_claim(self):
        proof = ShoulderSafetyProof(
            shoulder_constraint_active=True,
            shoulder_constraint_validated=False,
            violating_exercise_count=2,
            violating_exercise_ids=("push_up", "front_plank"),
        )
        policy = _base_policy()
        frame = compose(policy, shoulder_safety_proof=proof)
        prompt = render_prompt(frame, "bg")
        assert "SHOULDER SAFETY GROUNDING" in prompt
        assert "MUST NOT claim" in prompt
        assert proof.may_claim_safe is False

    def test_composer_with_valid_proof_may_claim_safe(self):
        proof = ShoulderSafetyProof(
            shoulder_constraint_active=True,
            shoulder_constraint_validated=True,
            violating_exercise_count=0,
        )
        policy = _base_policy()
        frame = compose(policy, shoulder_safety_proof=proof)
        prompt = render_prompt(frame, "bg")
        assert "SHOULDER SAFETY GROUNDING" in prompt
        assert "MAY note" in prompt
        assert proof.may_claim_safe is True

    def test_composer_with_inactive_constraint_no_grounding(self):
        proof = ShoulderSafetyProof(
            shoulder_constraint_active=False,
            shoulder_constraint_validated=False,
            violating_exercise_count=0,
        )
        policy = _base_policy()
        frame = compose(policy, shoulder_safety_proof=proof)
        prompt = render_prompt(frame, "bg")
        # Inactive constraint → no grounding block
        assert "SHOULDER SAFETY GROUNDING" not in prompt

    def test_composer_with_valid_proof_does_not_emit_must_not(self):
        proof = ShoulderSafetyProof(
            shoulder_constraint_active=True,
            shoulder_constraint_validated=True,
            violating_exercise_count=0,
        )
        policy = _base_policy()
        frame = compose(policy, shoulder_safety_proof=proof)
        prompt = render_prompt(frame, "bg")
        assert "MUST NOT claim" not in prompt


# ── Phrase parity BG/EN ───────────────────────────────────────────────────────

class TestPhraseParity:

    @pytest.mark.parametrize("phrase,expected_condition", [
        ("без натоварване на рамото", "shoulder_pain"),
        ("рамото да не участва", "shoulder_pain"),
        ("без упражнения за рамо", "shoulder_pain"),
        ("не натоварвай лявото рамо", "left_shoulder_pain"),
        ("не натоварвай дясното рамо", "right_shoulder_pain"),
        ("само упражнения без участие на рамото", "shoulder_pain"),
        ("no shoulder loading", "shoulder_pain"),
        ("do not use my shoulder", "shoulder_pain"),
        ("avoid loading the left shoulder", "left_shoulder_pain"),
        ("avoid loading the right shoulder", "right_shoulder_pain"),
        ("workout without shoulder involvement", "shoulder_pain"),
        ("заболя ме лявото рамо", "left_shoulder_pain"),
        ("боли ме дясното рамо", "right_shoulder_pain"),
    ])
    def test_phrase_maps_to_condition(self, phrase, expected_condition):
        conditions = detect_conditions(phrase)
        assert expected_condition in conditions, (
            f"Phrase {phrase!r} did not map to {expected_condition}. Got: {conditions}"
        )


# ── S1 integration: shoulder known limitation creates hard constraints ─────────

from brain.s1_constraints import build


class TestS1ShoulderIntegration:

    def test_left_shoulder_in_health_notes_creates_absolute_constraints(self):
        profile = {"healthNotes": "Имам проблем с лявото рамо."}
        cset, envelope = build(profile)
        absolute_movements = cset.movements(ConstraintTier.ABSOLUTE)
        assert len(absolute_movements) > 0, (
            "Left shoulder health note must produce ABSOLUTE movement constraints"
        )

    def test_shoulder_no_load_phrase_creates_constraints(self):
        profile = {"healthNotes": "без натоварване на рамото"}
        cset, envelope = build(profile)
        assert not cset.is_empty()

    def test_shoulder_constraint_set_is_active(self):
        profile = {"healthNotes": "left shoulder pain"}
        cset, envelope = build(profile)
        from brain.shoulder_validator import is_shoulder_constraint_active
        assert is_shoulder_constraint_active(cset) is True

    def test_no_shoulder_note_no_shoulder_constraint(self):
        profile = {"healthNotes": "back pain"}
        cset, envelope = build(profile)
        from brain.shoulder_validator import is_shoulder_constraint_active
        assert is_shoulder_constraint_active(cset) is False

    def test_push_up_forbidden_with_shoulder_constraint(self):
        profile = {"healthNotes": "shoulder pain"}
        cset, _ = build(profile)
        assert cset.forbids("push_up"), "push_up must be ABSOLUTE forbidden with shoulder constraint"

    def test_plank_forbidden_with_shoulder_constraint(self):
        profile = {"healthNotes": "shoulder pain"}
        cset, _ = build(profile)
        assert cset.forbids("plank"), "plank must be ABSOLUTE forbidden with shoulder constraint"

    def test_row_forbidden_with_shoulder_constraint(self):
        profile = {"healthNotes": "shoulder pain"}
        cset, _ = build(profile)
        assert cset.forbids("row"), "row must be ABSOLUTE forbidden with shoulder constraint"

    def test_goblet_hold_forbidden_with_shoulder_constraint(self):
        profile = {"healthNotes": "shoulder pain"}
        cset, _ = build(profile)
        assert cset.forbids("goblet_hold"), "goblet_hold must be ABSOLUTE forbidden"

    def test_dumbbell_hinge_forbidden_with_shoulder_constraint(self):
        profile = {"healthNotes": "shoulder pain"}
        cset, _ = build(profile)
        assert cset.forbids("dumbbell_hinge"), "dumbbell_hinge must be ABSOLUTE forbidden"

    def test_unknown_shoulder_load_forbidden_with_shoulder_constraint(self):
        profile = {"healthNotes": "shoulder pain"}
        cset, _ = build(profile)
        assert cset.forbids("unknown_shoulder_load"), (
            "unknown_shoulder_load must be ABSOLUTE forbidden (fail-closed)"
        )


# ── Blueprint validation integration ─────────────────────────────────────────

class TestBlueprintValidationIntegration:

    def _build_shoulder_cset_from_profile(self, phrase):
        from brain.s1_constraints import build
        profile = {"healthNotes": phrase}
        cset, _ = build(profile)
        return cset

    def test_initial_workout_with_push_up_fails_validation(self):
        cset = self._build_shoulder_cset_from_profile("shoulder pain")
        exercises = [
            {"canonical_id": "goblet_squat"},
            {"canonical_id": "push_up"},
            {"canonical_id": "table_row"},
            {"canonical_id": "dumbbell_romanian_deadlift"},
            {"canonical_id": "front_plank"},
        ]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False
        assert len(result.violating_ids) > 0

    def test_alternative_with_incline_push_up_fails(self):
        cset = self._build_shoulder_cset_from_profile("без натоварване на рамото")
        exercises = [
            {"canonical_id": "squat"},
            {"canonical_id": "incline_push_up"},
            {"canonical_id": "one_arm_dumbbell_row"},
            {"canonical_id": "bodyweight_hip_hinge"},
            {"canonical_id": "front_plank"},
        ]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_safe_lower_body_only_plan_passes(self):
        cset = self._build_shoulder_cset_from_profile("лявото рамо ме боли")
        exercises = [
            {"canonical_id": "bodyweight_squat"},
            {"canonical_id": "glute_bridge"},
            {"canonical_id": "seated_leg_extension"},
            {"canonical_id": "calf_raise"},
        ]
        result = validate_blueprint(exercises, cset)
        assert result.passed is True
        assert result.proof.may_claim_safe is True

    def test_harder_alternative_cannot_reintroduce_push_up(self):
        cset = self._build_shoulder_cset_from_profile("shoulder pain")
        exercises = [
            {"canonical_id": "bodyweight_squat"},
            {"canonical_id": "push_up"},  # introduced by "make it harder"
        ]
        result = validate_blueprint(exercises, cset)
        assert result.passed is False

    def test_constraint_preserved_across_follow_ups(self):
        """Shoulder constraint must survive an 'another workout' follow-up."""
        cset = self._build_shoulder_cset_from_profile("без натоварване на рамото")
        assert is_shoulder_constraint_active(cset) is True
        # Even after an "alternative" request, the same cset must still be active.
        result = validate_blueprint([{"canonical_id": "front_plank"}], cset)
        assert result.passed is False


# ── No internal data leakage ──────────────────────────────────────────────────

class TestNoLeakage:

    def test_proof_does_not_expose_internal_movement_names_in_frame(self):
        from conversation_composer import compose, build_policy, render_prompt
        proof = ShoulderSafetyProof(
            shoulder_constraint_active=True,
            shoulder_constraint_validated=False,
            violating_exercise_count=1,
            violating_exercise_ids=("push_up",),
        )
        policy = build_policy(
            decision=_MockDecision(),
            message="направи ми тренировка",
            conversation=[],
            voice=False,
            session_start=False,
            blueprint_present=True,
        )
        frame = compose(policy, shoulder_safety_proof=proof)
        prompt = render_prompt(frame, "bg")
        # The raw canonical ID "push_up" must not appear in the prompt to the LLM
        assert "push_up" not in prompt, (
            "Internal canonical exercise IDs must not leak into the composer prompt"
        )

