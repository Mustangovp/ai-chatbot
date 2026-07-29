"""Regression coverage for non-authoritative, production-safe shadow telemetry."""
import threading
import time

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
        components=("brain",), timeout_ms=250, work=lambda: _observation(locale="bg"),
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
        components=("persona", "expert"), timeout_ms=10,
        work=lambda: (release.wait(1.0), _observation())[1], request_id="timeout-request",
    )
    assert time.monotonic() - started < 0.1
    _wait_for(lambda: observability.snapshot_for_internal_use()["components"]["persona"]["TIMEOUT"] == 1)
    release.set()


def test_worker_exception_is_categorized_without_raising_to_the_caller():
    observability.reset_for_testing()
    assert observability.submit(
        locale="en", authoritative_path="legacy", authoritative_intent="workout",
        components=("brain",), timeout_ms=250,
        work=lambda: (_ for _ in ()).throw(RuntimeError("not delivered")),
    )
    _wait_for(lambda: observability.snapshot_for_internal_use()["components"]["brain"]["ERROR"] == 1)
    assert observability.snapshot_for_internal_use()["fallback_categories"] == {"SHADOW_EXCEPTION": 1}
