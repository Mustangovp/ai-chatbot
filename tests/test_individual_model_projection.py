from datetime import datetime, timezone
import pytest
from individual_model_projection import (
    IndividualModelCoachingProjectionV1,
    build_projection,
    render_prompt,
    validate_projection,
)
from individual_model_snapshot import IndividualModelSnapshotV1

def _snapshot(**changes):
    base = dict(schema_version="individual-model-snapshot-v1", user_id="secret", profile={"goal":"strength","level":"beginner","equipment":"home","note":"secret"}, constraints=({"id":"secret","pattern":"vertical_push","source":"x","state":"active"},), training={"latest_authoritative_completed_session_evidence":True,"latest_authoritative_completed_session_freshness":"unknown","latest_authoritative_completed_session_occurred_at":datetime(2026,9,2,10,tzinfo=timezone.utc)}, progression=(), trajectory=({"trajectory_state":"progressing","completion_ids":("secret",)},), adherence="unknown", human_state={"motivation":{"value":"secret"}}, nutrition={"targets":{"calories":2000,"secret":999}}, generated_at=datetime.now(timezone.utc))
    base.update(changes); return IndividualModelSnapshotV1(**base)

def test_projection_is_closed_redacted_and_excludes_hse_ids_and_free_text():
    prompt = render_prompt(build_projection(_snapshot()))
    assert "goal=strength" in prompt and "trajectory=progressing" in prompt
    assert "authoritative completed-session evidence freshness=unknown" in prompt
    for forbidden in ("secret", "motivation", "note", "user_id", "adherence", "stalled", "regressing"):
        assert forbidden not in prompt
    assert "recent" not in prompt and "current" not in prompt and "lately" not in prompt
    assert "2026-09-02T10:00:00" not in prompt
    assert "calories:2000" in prompt

def test_invalid_or_insufficient_snapshot_never_creates_a_trajectory_claim():
    prompt = render_prompt(build_projection(_snapshot(trajectory=({"trajectory_state":"insufficient_evidence"},), profile={})))
    assert "trajectory=" not in prompt


def test_completion_ids_or_adherence_never_create_a_completion_claim():
    prompt = render_prompt(build_projection(_snapshot(
        training={"latest_completion_id": "secret", "latest_session_id": "secret"},
        adherence="missed",
    )))

    assert "completed-session" not in prompt
    assert "adherence" not in prompt


@pytest.mark.parametrize("state", ("partial", "skipped", "abandoned", "unknown"))
def test_noncompleted_execution_states_never_create_a_completed_projection_claim(state):
    prompt = render_prompt(build_projection(_snapshot(training={
        "latest_execution_state": state,
        "latest_authoritative_completed_session_evidence": False,
    })))

    assert "completed-session" not in prompt


@pytest.mark.parametrize("freshness", ("current", "stale", "invalid"))
def test_no_unsupported_freshness_state_can_reach_the_projection(freshness):
    prompt = render_prompt(build_projection(_snapshot(training={
        "latest_authoritative_completed_session_evidence": True,
        "latest_authoritative_completed_session_freshness": freshness,
        "latest_authoritative_completed_session_occurred_at": datetime(2026, 9, 2, tzinfo=timezone.utc),
    })))

    assert "freshness=unknown" in prompt
    assert f"freshness={freshness}" not in prompt


def test_projection_validator_rejects_nonproduction_freshness_states():
    with pytest.raises(ValueError):
        validate_projection(IndividualModelCoachingProjectionV1(
            None, None, None, (), "current", None, ()))
