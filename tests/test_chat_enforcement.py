"""
M4 Commit 2 — /chat enforcement wiring, gated by BRAIN_ENFORCE (OFF by default).

Proves at the /chat surface:
  • OFF  → byte-identical: no decision event, system prompt unmodified.
  • ON   → enforcement activates: leading {"decision":...} event.
  • ON + emergency → routes; generation is steered away from a workout
    (SAFETY OVERRIDE injected, should_generate=False).
  • ON + GO/MODIFY → continues through generation with S1 constraints injected.

The OpenAI stream is faked (records the exact system prompt sent). The emergency
and OFF cases use a REAL message through the REAL cascade; the MODIFY case stubs
only the Decision source (the cascade verdict is unit-tested elsewhere) so the
WIRING for a permitted-but-constrained decision is exercised end-to-end.
"""
import os
import json
import types
import pytest

import app as appmod
from brain.types import (Decision, Verdict, Intervention, S2State, ConstraintSet,
                         Constraint, ConstraintTier, CapacityEnvelope)


# ── Fake OpenAI streaming client ─────────────────────────────────────────────
class _Delta:
    def __init__(self, c): self.content = c
class _Choice:
    def __init__(self, c): self.delta = _Delta(c)
class _Chunk:
    def __init__(self, c): self.choices = [_Choice(c)]


@pytest.fixture
def captured(monkeypatch):
    box = {}

    def fake_create(**kwargs):
        box["system"] = kwargs["messages"][0]["content"]      # snapshot at call time
        box["model"] = kwargs.get("model")
        def _stream():
            yield _Chunk("ok")
        return _stream()

    monkeypatch.setattr(appmod.client.chat.completions, "create", fake_create)
    return box


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture(autouse=True)
def _enforce_off_by_default(monkeypatch):
    monkeypatch.delenv("BRAIN_ENFORCE", raising=False)        # default OFF for every test
    yield


def _events(resp):
    out = []
    for line in resp.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _post(client, message, profile=None):
    return client.post("/chat", json={"message": message, "lang": "en", "profile": profile or {}})


# ── OFF = byte-identical ─────────────────────────────────────────────────────
def test_off_is_identical_no_decision_event(client, captured):
    resp = _post(client, "my chest feels tight and heavy going uphill")
    evs = _events(resp)
    assert not any("decision" in e for e in evs)              # no leading decision event
    assert "SAFETY OVERRIDE" not in captured["system"]        # system prompt untouched
    assert any(e.get("t") == "ok" for e in evs) and any(e.get("done") for e in evs)


# ── ON + emergency → route, never a workout ──────────────────────────────────
def test_on_emergency_routes_and_blocks_workout(client, captured, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "1")
    resp = _post(client, "my chest feels tight and heavy going uphill")
    evs = _events(resp)
    decision = next(e["decision"] for e in evs if "decision" in e)
    assert decision["generate"] is False
    assert decision["verdict"] in ("NOT_YET", "NO_TRAIN")
    assert decision["route"] == "clinician_prompt"
    # Generation call was made (voice) but steered away from a workout.
    assert "SAFETY OVERRIDE" in captured["system"]
    assert "do not generate a workout" in captured["system"].lower()


# ── ON + GO/MODIFY → continues to constrained generation ─────────────────────
def test_on_modify_continues_with_constraints(client, captured, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "1")

    cs = ConstraintSet()
    cs.add(Constraint("valsalva", ConstraintTier.ABSOLUTE, "k"))
    modify = Decision(
        verdict=Verdict.MODIFY, intervention=Intervention("training", "k"),
        generate_training=True, halt=False, verdict_confidence=0.6,
        constraints=cs, envelope=CapacityEnvelope(0.4, 0.4, 0.4, False, 0.6),
        s2=S2State(readiness=0.6, readiness_conf=0.6, red_flags=[], halt=False),
        need_vector=[("training", 0.9)], decision_id="d", model=None)
    monkeypatch.setattr(appmod.brain_cascade, "decide", lambda *a, **k: modify)

    resp = _post(client, "give me a strength workout", profile={"healthNotes": "high blood pressure"})
    evs = _events(resp)
    decision = next(e["decision"] for e in evs if "decision" in e)
    assert decision["verdict"] == "MODIFY" and decision["generate"] is True
    # Generation proceeded, with the constraint injected into the system prompt.
    assert "valsalva" in captured["system"]
    assert any(e.get("t") == "ok" for e in evs) and any(e.get("done") for e in evs)


# ── ON + benign/no-cascade-signal → still generates (no false refusal) ────────
def test_on_healthy_request_still_generates(client, captured, monkeypatch):
    monkeypatch.setenv("BRAIN_ENFORCE", "1")
    # Anonymous → NOT_YET by conservative default; assert it never silently drops
    # the generation call (voice always streams) and emits a decision event.
    resp = _post(client, "what should I eat after training")
    evs = _events(resp)
    assert any("decision" in e for e in evs)
    assert any(e.get("t") == "ok" for e in evs) and any(e.get("done") for e in evs)


# ── GOLDEN: the OFF path is byte-identical to the legacy prompt ───────────────
def test_offpath_golden_prompt_identity(client, captured, monkeypatch):
    """Pre-activation guard (user precondition #2): with BRAIN_ENFORCE OFF, the
    exact system prompt sent to the model MUST equal the legacy assembly —
    enforcement injects nothing. The composed voice reads the wall clock, so we
    freeze it to make the golden deterministic."""
    import datetime as _rdt
    import personality

    class _FrozenDT:                                   # freeze personality's clock
        class datetime:
            @staticmethod
            def now(tz=None):
                return _rdt.datetime(2026, 7, 6, 10, 0, 0, tzinfo=tz or _rdt.timezone.utc)
            @staticmethod
            def fromisoformat(s):
                return _rdt.datetime.fromisoformat(s)
        timezone = _rdt.timezone
    monkeypatch.setattr(personality, "_dt", _FrozenDT)

    profile = {"level": "intermediate", "activityLevel": "active",
               "goal": "strength", "age": 34, "gender": "male"}
    msg = "plan my training week"

    resp = _post(client, msg, profile=profile)         # BRAIN_ENFORCE OFF (autouse)
    got = captured["system"]

    # Reconstruct the legacy prompt with the SAME primitives + frozen clock.
    personality_block = personality.compose(lang="en", profile=profile, workouts=[],
                                            message=msg, conversation=[])
    profile_block = appmod._build_profile_block(profile, "en")
    base = (profile_block + "\n\n" + appmod.SYSTEM_INSTRUCTIONS) if profile_block else appmod.SYSTEM_INSTRUCTIONS
    golden = (personality_block + "\n\n" + base) if personality_block else base

    assert got == golden                               # byte-identical to legacy assembly
    assert "SAFETY OVERRIDE" not in got and "AVOID/adapt" not in got
    assert not any("decision" in e for e in _events(resp))   # no leading decision event
    # Sanity: the golden is a real, non-empty APEX prompt (identity anchor present).
    assert appmod.SYSTEM_INSTRUCTIONS and appmod.SYSTEM_INSTRUCTIONS in got
