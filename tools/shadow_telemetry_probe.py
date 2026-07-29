"""One-shot, synthetic-only diagnosis for the production shadow telemetry path."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
import context_builder
import decision_engine
from brain.runtime_assets import expert_consensus, persona_matcher
from brain.runtime_assets import shadow_observability


PROBE_ID = uuid.uuid4().hex


def marker(stage: str, status: str = "SUCCESS", error_category: str | None = None,
           started: float | None = None) -> None:
    print(json.dumps({"event": "APEX_SHADOW_PROBE", "probe_id": PROBE_ID,
                      "stage": stage, "status": status,
                      "elapsed_ms": round((time.perf_counter() - started) * 1000, 3) if started else 0.0,
                      "error_category": error_category}, separators=(",", ":")), flush=True)


def main() -> int:
    started = time.perf_counter()
    marker("PROBE_STARTED", started=started)
    profile = {"goal": "strength", "equipment": "home", "level": "beginner",
               "age": "30", "height": "175", "weight": "70"}
    marker("CONFIG_LOADED", started=started)
    marker("ELIGIBILITY_EVALUATED", started=started)
    try:
        snapshot = context_builder.build_context(
            intent="workout", subject=context_builder.Subject("anonymous_device", "synthetic", False),
            request_time=app._dt.datetime.now(app._dt.timezone.utc), access={"plan": "free"},
            browser_profile=profile, legacy_profile=profile, legacy_conversation=[], legacy_workouts=[])
        decision = decision_engine.decide(snapshot, "workout")
    except Exception:
        marker("SNAPSHOT_ERROR", "FAILED", "SNAPSHOT_ERROR", started)
        marker("PROBE_FINISHED", "FAILED", "SNAPSHOT_ERROR", started)
        return 1
    marker("SNAPSHOT_BUILT", started=started)
    marker("BRAIN_STARTED", started=started)
    brain = app._brain_shadow_observation(profile, "synthetic workout request", [], "gpt-4o-mini",
                                          locale="bg", authoritative_path="legacy", authoritative_intent="workout")
    marker("BRAIN_COMPLETED" if brain.brain_status == "SUCCESS" else "BRAIN_FAILED",
           brain.brain_status, brain.fallback_category, started)
    marker("PERSONA_STARTED", started=started)
    try:
        match = persona_matcher.match(snapshot, decision.intent)
        persona_status = "ABSTAIN" if match.abstained else "SUCCESS"
        marker("PERSONA_ABSTAINED" if match.abstained else "PERSONA_COMPLETED", persona_status, started=started)
    except Exception:
        match = None
        persona_status = "ERROR"
        marker("PERSONA_FAILED", "FAILED", "PERSONA_EXCEPTION", started)
    marker("EXPERT_STARTED", started=started)
    try:
        consensus = expert_consensus.evaluate(snapshot, match, decision.intent) if match else None
        expert_status = "SKIPPED" if consensus is None else ("ABSTAIN" if consensus.abstained else "SUCCESS")
        marker("EXPERT_ABSTAINED" if expert_status == "ABSTAIN" else "EXPERT_COMPLETED", expert_status, started=started)
    except Exception:
        consensus = None
        expert_status = "ERROR"
        marker("EXPERT_FAILED", "FAILED", "EXPERT_EXCEPTION", started)
    marker("EVENT_BUILD_STARTED", started=started)
    try:
        event = shadow_observability.ShadowObservation(
            locale="bg", authoritative_path="legacy", authoritative_intent="workout",
            brain_status=brain.brain_status, persona_status=persona_status, expert_status=expert_status,
            persona_match_class="ABSTAIN" if match and match.abstained else "MATCHED" if match else None,
            expert_domain_classes=app._shadow_expert_domains(consensus), decision_parity="NOT_COMPARABLE",
            safety_parity="NOT_COMPARABLE", constraint_parity="NOT_COMPARABLE",
            duration_ms=(time.perf_counter() - started) * 1000, fallback_category=None,
            request_id=PROBE_ID, timestamp_utc=app._dt.datetime.now(app._dt.timezone.utc).isoformat())
        event.as_log_record()
        marker("EVENT_BUILT", started=started)
    except Exception:
        marker("EVENT_BUILD_FAILED", "FAILED", "EVENT_BUILD_EXCEPTION", started)
        marker("PROBE_FINISHED", "FAILED", "EVENT_BUILD_EXCEPTION", started)
        return 1
    marker("SINK_WRITE_STARTED", started=started)
    try:
        shadow_observability._record(event)
        marker("SINK_WRITE_COMPLETED", started=started)
        marker("FLUSH_STARTED", started=started)
        sys.stdout.flush()
        marker("FLUSH_COMPLETED", started=started)
    except Exception:
        marker("SINK_WRITE_FAILED", "FAILED", "SINK_WRITE_EXCEPTION", started)
        marker("PROBE_FINISHED", "FAILED", "SINK_WRITE_EXCEPTION", started)
        return 1
    marker("PROBE_FINISHED", started=started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
