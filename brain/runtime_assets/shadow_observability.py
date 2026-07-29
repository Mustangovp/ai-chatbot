"""Bounded, PII-minimized telemetry for non-authoritative shadow evaluation."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import threading
import time
from typing import Callable
import uuid


_COMPONENTS = ("brain", "persona", "expert")
_STATUSES = ("SUCCESS", "ABSTAIN", "ERROR", "TIMEOUT", "SKIPPED")
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="apex-shadow")
_SLOTS = threading.BoundedSemaphore(16)
_LOCK = threading.Lock()


@dataclass(frozen=True)
class ShadowObservation:
    """Safe event shape. It deliberately excludes messages, profiles, prompts and IDs."""
    locale: str
    authoritative_path: str
    authoritative_intent: str
    brain_status: str
    persona_status: str
    expert_status: str
    persona_match_class: str | None
    expert_domain_classes: tuple[str, ...]
    decision_parity: str
    safety_parity: str
    constraint_parity: str
    duration_ms: float
    fallback_category: str | None = None
    request_id: str = ""
    timestamp_utc: str = ""

    def as_log_record(self) -> dict[str, object]:
        return {
            "event": "shadow_observation",
            "request_id": self.request_id,
            "timestamp": self.timestamp_utc,
            "locale": self.locale,
            "authoritative_path": self.authoritative_path,
            "authoritative_intent": self.authoritative_intent,
            "brain_shadow_status": self.brain_status,
            "persona_shadow_status": self.persona_status,
            "expert_shadow_status": self.expert_status,
            "persona_match_class": self.persona_match_class,
            "expert_domain_classes": self.expert_domain_classes,
            "decision_parity": self.decision_parity,
            "safety_parity": self.safety_parity,
            "constraint_parity": self.constraint_parity,
            "shadow_duration_ms": round(self.duration_ms, 3),
            "fallback_category": self.fallback_category,
        }


class _Telemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self.events: list[ShadowObservation] = []
            self.durations: list[float] = []
            self.counts = {component: {status: 0 for status in _STATUSES}
                           for component in _COMPONENTS}
            self.fallbacks: dict[str, int] = {}

    def record(self, observation: ShadowObservation) -> None:
        with self._lock:
            self.events.append(observation)
            self.durations.append(observation.duration_ms)
            for component, status in (("brain", observation.brain_status),
                                      ("persona", observation.persona_status),
                                      ("expert", observation.expert_status)):
                self.counts[component][status] += 1
            if observation.fallback_category:
                self.fallbacks[observation.fallback_category] = (
                    self.fallbacks.get(observation.fallback_category, 0) + 1)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            durations = sorted(self.durations)
            def percentile(percent: float) -> float:
                if not durations:
                    return 0.0
                index = max(0, min(len(durations) - 1, round((len(durations) - 1) * percent)))
                return round(durations[index], 3)
            return {
                "total": len(self.events),
                "components": {key: dict(value) for key, value in self.counts.items()},
                "duration_ms": {"p50": percentile(0.50), "p95": percentile(0.95),
                                "max": round(max(durations), 3) if durations else 0.0},
                "fallback_categories": dict(self.fallbacks),
            }


_TELEMETRY = _Telemetry()


def snapshot_for_internal_use() -> dict[str, object]:
    """Process-local aggregation seam. Never expose this through a public route."""
    return _TELEMETRY.snapshot()


def reset_for_testing() -> None:
    _TELEMETRY.reset()


def _timeout_observation(locale: str, path: str, intent: str, components: tuple[str, ...], duration_ms: float) -> ShadowObservation:
    statuses = {component: "SKIPPED" for component in _COMPONENTS}
    for component in components:
        statuses[component] = "TIMEOUT"
    return ShadowObservation(locale, path, intent, statuses["brain"], statuses["persona"], statuses["expert"],
                             None, (), "NOT_COMPARABLE", "NOT_COMPARABLE", "NOT_COMPARABLE", duration_ms,
                             "SHADOW_TIMEOUT")


def submit(*, locale: str, authoritative_path: str, authoritative_intent: str,
           components: tuple[str, ...], timeout_ms: int,
           work: Callable[[], ShadowObservation], request_id: str | None = None) -> bool:
    """Start bounded shadow work without waiting for it in the request lifecycle."""
    request_id = request_id or uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).isoformat()
    def stamp(observation: ShadowObservation) -> ShadowObservation:
        return replace(observation, request_id=request_id, timestamp_utc=timestamp)

    if not _SLOTS.acquire(blocking=False):
        statuses = {component: "SKIPPED" for component in _COMPONENTS}
        for component in components:
            statuses[component] = "SKIPPED"
        _record(stamp(ShadowObservation(locale, authoritative_path, authoritative_intent,
                                  statuses["brain"], statuses["persona"], statuses["expert"], None, (),
                                  "NOT_COMPARABLE", "NOT_COMPARABLE", "NOT_COMPARABLE", 0.0,
                                  "SHADOW_DISPATCH_SATURATED")))
        return False

    started = time.perf_counter()
    resolved = threading.Event()
    future: Future[ShadowObservation] = _EXECUTOR.submit(work)

    def complete(done: Future[ShadowObservation]) -> None:
        try:
            if not resolved.is_set():
                resolved.set()
                try:
                    observation = done.result()
                except Exception:
                    statuses = {component: "SKIPPED" for component in _COMPONENTS}
                    for component in components:
                        statuses[component] = "ERROR"
                    observation = ShadowObservation(
                        locale, authoritative_path, authoritative_intent,
                        statuses["brain"], statuses["persona"], statuses["expert"], None, (),
                        "NOT_COMPARABLE", "NOT_COMPARABLE", "NOT_COMPARABLE",
                        (time.perf_counter() - started) * 1000, "SHADOW_EXCEPTION")
                _record(stamp(observation))
        finally:
            _SLOTS.release()

    def timeout() -> None:
        if not resolved.is_set():
            resolved.set()
            _record(stamp(_timeout_observation(locale, authoritative_path, authoritative_intent, components,
                                               (time.perf_counter() - started) * 1000)))

    future.add_done_callback(complete)
    timer = threading.Timer(timeout_ms / 1000.0, timeout)
    timer.daemon = True
    timer.start()
    return True


def _record(observation: ShadowObservation) -> None:
    _TELEMETRY.record(observation)
    # Railway captures the process stream reliably; the record shape has no
    # messages, profiles, prompts, persona IDs, rule IDs, or user identifiers.
    print(json.dumps(observation.as_log_record(), separators=(",", ":"), sort_keys=True), flush=True)
