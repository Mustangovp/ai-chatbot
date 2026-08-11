"""Regression gates for the inactive, typed HSE presentation projection."""
from __future__ import annotations

from copy import deepcopy
import inspect

import conversation_composer as composer
from coaching.presentation import (
    PresentationProjectionV1,
    build_presentation_projection,
    validate_presentation_projection,
)
import human_state


def _state(**values):
    return {key: {"value": value, "fresh": True} for key, value in values.items()}


def _policy(**changes):
    defaults = dict(
        mode="answer_directly", tone="direct", acknowledge_context=False,
        ask_question=False, question=None, answer_depth="standard",
        reference_memory=False, explain_why=False, verbal_summary_only=False,
        preserve_blueprint=True, must_not_generate_plan=False, must_not_repeat=False,
        must_not_greet=True, safety_boundary=False, fallback_to_legacy=False,
    )
    defaults.update(changes)
    return composer.ConversationPolicy(**defaults)


def test_default_projection_and_no_eligible_state_are_noops(monkeypatch):
    monkeypatch.setattr(human_state, "view", lambda subject: _state())
    assert PresentationProjectionV1() == PresentationProjectionV1()
    assert build_presentation_projection("device:one") is None


def test_builder_maps_only_the_approved_fresh_state(monkeypatch):
    monkeypatch.setattr(human_state, "view", lambda subject: _state(motivation="low"))
    assert build_presentation_projection("device:motivation") == PresentationProjectionV1(
        tone="supportive", encouragement="gentle")

    monkeypatch.setattr(human_state, "view", lambda subject: _state(confidence="low"))
    assert build_presentation_projection("device:confidence") == PresentationProjectionV1(
        tone="reassuring", encouragement="mastery")

    monkeypatch.setattr(human_state, "view", lambda subject: _state(adherence="missed"))
    assert build_presentation_projection("device:adherence") == PresentationProjectionV1(
        acknowledgement="brief", encouragement="gentle")


def test_builder_conflict_resolution_is_deterministic(monkeypatch):
    monkeypatch.setattr(human_state, "view", lambda subject: _state(
        motivation="low", confidence="low", adherence="gap"))
    expected = PresentationProjectionV1(
        tone="reassuring", acknowledgement="brief", encouragement="mastery")
    assert build_presentation_projection("device:conflict") == expected
    assert build_presentation_projection("device:conflict") == expected


def test_blocklisted_or_stale_state_has_no_effect(monkeypatch):
    monkeypatch.setattr(human_state, "view", lambda subject: {
        "pain": {"value": "present", "fresh": True},
        "illness": {"value": "present", "fresh": True},
        "fatigue": {"value": "high", "fresh": True},
        "motivation": {"value": "low", "fresh": False},
        "confidence": {"value": "low", "fresh": False},
        "adherence": {"value": "missed", "fresh": False},
    })
    assert build_presentation_projection("device:blocklisted") is None


def test_builder_does_not_extract_or_use_trajectory(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("not an approved presentation source")

    monkeypatch.setattr(human_state.extractor, "extract", forbidden)
    monkeypatch.setattr(human_state, "view", lambda subject: _state(motivation="low"))
    assert build_presentation_projection("device:no-extractor").tone == "supportive"
    source = inspect.getsource(build_presentation_projection)
    assert "extractor." not in source and "trajectory." not in source and "profile[" not in source


def test_current_message_cannot_affect_the_builder(monkeypatch):
    """Only a future persisted fusion may change a later projection."""
    monkeypatch.setattr(human_state, "view", lambda subject: _state())
    assert build_presentation_projection("device:message-only") is None


def test_malformed_state_and_builder_failure_fail_closed(monkeypatch):
    monkeypatch.setattr(human_state, "view", lambda subject: {"motivation": "low"})
    assert build_presentation_projection("device:malformed") is None

    def failure(subject):
        raise RuntimeError("sensitive persistence detail")

    monkeypatch.setattr(human_state, "view", failure)
    assert build_presentation_projection("device:failure") is None


def test_invalid_projection_values_and_schema_are_rejected():
    assert validate_presentation_projection({"tone": "supportive"}) is None
    assert validate_presentation_projection(PresentationProjectionV1(schema_version="unknown")) is None
    assert validate_presentation_projection(PresentationProjectionV1(tone="unsafe")) is None
    assert validate_presentation_projection(PresentationProjectionV1(encouragement="free text")) is None


def test_composer_none_is_byte_identical_and_projection_is_presentation_only():
    policy = _policy()
    blueprint = {"exercise_id": "row", "sets": 3, "reps": 10, "rest": 90}
    nutrition = {"kcal": 2200, "protein": 160}
    blueprint_before, nutrition_before = deepcopy(blueprint), deepcopy(nutrition)
    baseline = composer.compose(policy, validated_blueprint=blueprint,
                                validated_nutrition_contract=True)
    explicit_none = composer.compose(policy, validated_blueprint=blueprint,
                                     validated_nutrition_contract=True,
                                     presentation_projection=None)
    assert baseline == explicit_none
    assert composer.render_prompt(baseline, "en") == composer.render_prompt(explicit_none, "en")

    projected = composer.compose(
        policy, validated_blueprint=blueprint, validated_nutrition_contract=True,
        presentation_projection=PresentationProjectionV1(
            tone="supportive", acknowledgement="brief", encouragement="gentle",
            explanation_depth="concise"),
    )
    prompt = composer.render_prompt(projected, "en")
    assert projected.tone == "supportive" and projected.answer_depth == "brief"
    assert "no-pressure encouragement" in prompt
    assert blueprint == blueprint_before and nutrition == nutrition_before
    assert "motivation" not in prompt.lower() and "confidence" not in prompt.lower()


def test_projection_cannot_change_safety_boundary_or_plan_preservation():
    policy = _policy(tone="protective", safety_boundary=True, must_not_generate_plan=True)
    frame = composer.compose(
        policy, validated_blueprint={"exercise_id": "safe"},
        presentation_projection=PresentationProjectionV1(
            tone="supportive", acknowledgement="brief", encouragement="mastery",
            explanation_depth="concise"),
    )
    assert frame.tone == "protective"
    assert frame.acknowledgement is False
    assert frame.answer_depth == "standard"
    assert frame.encouragement == "none"
    assert "Do not generate, regenerate, extend, or alter" in composer.render_prompt(frame, "en")


def test_projection_has_only_closed_id_free_fields():
    projection = PresentationProjectionV1(tone="reassuring", encouragement="mastery")
    assert set(projection.__dict__) == {
        "schema_version", "tone", "acknowledgement", "encouragement", "explanation_depth",
    }
    assert "device" not in repr(projection).lower()
