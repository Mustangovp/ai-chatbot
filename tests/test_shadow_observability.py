"""Regression coverage for non-authoritative, production-safe shadow telemetry."""
import threading
import time
import json

import pytest

from brain.runtime_assets import shadow_observability as observability


def _observation(**overrides):
    values = {
        "locale": "en", "authoritative_path": "legacy", "authoritative_intent": "workout",
        "brain_status": "SUCCESS", "persona_status": "SKIPPED", "expert_status": "SKIPPED",
        "persona_match_class": None, "expert_domain_classes": (),
        "decision_parity": "NOT_COMPARABLE", "safety_parity": "NOT_COMPARABLE",
        "constraint_parity": "NOT_COMPARABLE", "duration_ms": 1.0,
    }
    values.update(overrides)
    return observability.ShadowObservation(**values)


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate()


def test_observability_records_safe_aggregate_fields_only():
    observability.reset_for_testing()
    observability.submit(
        locale="bg", authoritative_path="legacy", authoritative_intent="workout",
        components=("brain",), task_kind="brain", timeout_ms=250, work=lambda: _observation(locale="bg"),
        request_id="safe-request",
    )
    _wait_for(lambda: observability.snapshot_for_internal_use()["total"] == 1)
    snapshot = observability.snapshot_for_internal_use()
    assert snapshot["components"]["brain"]["SUCCESS"] == 1
    assert snapshot["duration_ms"]["p50"] == 1.0
    event = observability._TELEMETRY.events[0].as_log_record()
    assert event["request_id"] == "safe-request"
    assert "message" not in event and "profile" not in event and "prompt" not in event


def test_timeout_is_recorded_without_waiting_for_the_shadow_worker():
    observability.reset_for_testing()
    release = threading.Event()
    started = time.monotonic()
    assert observability.submit(
        locale="en", authoritative_path="legacy", authoritative_intent="nutrition",
        components=("persona", "expert"), task_kind="persona_expert", timeout_ms=10,
        work=lambda: (release.wait(1.0), _observation())[1], request_id="timeout-request",
    )
    assert time.monotonic() - started < 0.1
    _wait_for(lambda: observability.snapshot_for_internal_use()["components"]["persona"]["TIMEOUT"] == 1)
    release.set()


def test_timeout_releases_admission_for_the_next_shadow_request():
    observability.reset_for_testing()
    original_slots = observability._SLOTS
    observability._SLOTS = threading.BoundedSemaphore(1)
    release = threading.Event()
    try:
        assert observability.submit(
            locale="en", authoritative_path="legacy", authoritative_intent="nutrition",
            components=("brain",), task_kind="brain", timeout_ms=10,
            work=lambda: (release.wait(1.0), _observation())[1], request_id="first",
        )
        _wait_for(lambda: observability.snapshot_for_internal_use()["components"]["brain"]["TIMEOUT"] == 1)
        assert observability.submit(
            locale="en", authoritative_path="legacy", authoritative_intent="workout",
            components=("brain",), task_kind="brain", timeout_ms=250, work=_observation, request_id="second",
        )
        _wait_for(lambda: observability.snapshot_for_internal_use()["total"] == 2)
    finally:
        release.set()
        time.sleep(0.02)
        observability._SLOTS = original_slots


def test_executor_is_recreated_when_the_worker_process_changes(monkeypatch):
    observability._shutdown_executor()
    monkeypatch.setattr(observability.os, "getpid", lambda: 101)
    first = observability._worker_executor()
    monkeypatch.setattr(observability.os, "getpid", lambda: 202)
    second = observability._worker_executor()
    try:
        assert first is not second
        assert observability._EXECUTOR_PID == 202
    finally:
        observability._shutdown_executor()


def test_worker_exception_is_categorized_without_raising_to_the_caller():
    observability.reset_for_testing()
    assert observability.submit(
        locale="en", authoritative_path="legacy", authoritative_intent="workout",
        components=("brain",), task_kind="brain", timeout_ms=250,
        work=lambda: (_ for _ in ()).throw(RuntimeError("not delivered")),
    )
    _wait_for(lambda: observability.snapshot_for_internal_use()["components"]["brain"]["ERROR"] == 1)
    assert observability.snapshot_for_internal_use()["fallback_categories"] == {"SHADOW_EXCEPTION": 1}


def test_task_kinds_emit_complete_independent_lifecycle_summaries(monkeypatch):
    observability.reset_for_testing()
    records = []
    monkeypatch.setattr(observability._LOGGER, "warning",
                        lambda _template, payload: records.append(json.loads(payload)))

    assert observability.submit(
        locale="en", authoritative_path="legacy", authoritative_intent="workout",
        components=("brain",), task_kind="brain", timeout_ms=250,
        work=lambda: _observation(persona_status="SKIPPED", expert_status="SKIPPED"),
    )
    assert observability.submit(
        locale="en", authoritative_path="legacy", authoritative_intent="workout",
        components=("persona", "expert"), task_kind="persona_expert", timeout_ms=250,
        work=lambda: _observation(brain_status="SKIPPED", persona_status="SUCCESS", expert_status="SUCCESS"),
    )
    _wait_for(lambda: len([record for record in records
                            if record["event"] == "task_lifecycle_summary"]) == 2)

    for task_kind in ("brain", "persona_expert"):
        task_records = [record for record in records if record.get("task_kind") == task_kind]
        assert [record["event"] for record in task_records].count("task_submitted") == 1
        assert [record["event"] for record in task_records].count("worker_started") == 1
        assert [record["event"] for record in task_records].count("event_built") == 1
        assert [record["event"] for record in task_records].count("sink_write_completed") == 1
        assert [record["event"] for record in task_records].count("task_completed") == 1
        summary = next(record for record in task_records if record["event"] == "task_lifecycle_summary")
        assert summary["status"] == "completed"
        assert all(summary[field] is True for field in (
            "submitted", "worker_started", "event_built", "sink_completed", "flush_completed",
        ))
        assert not ({"request_id", "message", "profile", "prompt", "exception"} & set(summary))


def test_task_kind_is_closed_and_metric_logger_failure_is_fail_open(monkeypatch):
    with pytest.raises(ValueError, match="invalid task kind"):
        observability.submit(
            locale="en", authoritative_path="legacy", authoritative_intent="workout",
            components=("brain",), task_kind="unknown", timeout_ms=250, work=_observation,
        )
    observability.reset_for_testing()
    monkeypatch.setattr(observability._LOGGER, "warning",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("logger unavailable")))
    assert observability.submit(
        locale="en", authoritative_path="legacy", authoritative_intent="workout",
        components=("brain",), task_kind="brain", timeout_ms=250, work=_observation,
    )
    _wait_for(lambda: observability.snapshot_for_internal_use()["total"] == 1)
