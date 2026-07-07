"""
BUILD-001 — Human State replay & regression.
Ingestion is deterministic: replaying the same conversation with the same clock
yields the same state; never-downgrade holds across a multi-turn conversation.
"""
import datetime as _dt

import human_state
import db as store

UTC = _dt.timezone.utc
_BASE = _dt.datetime(2026, 7, 7, 9, 0, 0, tzinfo=UTC)

CONVERSATION = [
    (0,   "I've slept 4 hours and I'm exhausted"),        # sleep=4 (numeric), fatigue=high (explicit)
    (30,  "kind of tired still"),                          # fatigue moderate (hedged) — must NOT downgrade
    (60,  "my lower back is sore today"),                  # pain
    (90,  "I only have 15 minutes and I hate oats"),       # time=15, preference avoid oats
    (120, "actually I'm feeling motivated now"),           # motivation high
]


def _run(subject):
    for mins, msg in CONVERSATION:
        human_state.ingest(subject, msg, now=_BASE + _dt.timedelta(minutes=mins))
    return human_state.view(subject, now=_BASE + _dt.timedelta(minutes=120))


def test_conversation_builds_expected_state():
    v = _run("device:r1")
    assert v["sleep"]["value"] == "4"
    assert v["fatigue"]["value"] == "high"                 # hedged "kind of tired" did NOT overwrite
    assert v["pain"]["value"] == "present"
    assert v["time_availability"]["value"] == "15"
    assert v["motivation"]["value"] == "high"
    assert v["preference:oats"]["value"] == {"avoid": "oats"}


def test_replay_is_deterministic():
    a = _run("device:r2")
    b = _run("device:r3")
    # same conversation + same clock → same state (compare the decision-relevant fields)
    def norm(view):
        return {k: (val["value"], val["fresh"], val["stored_confidence"]) for k, val in view.items()}
    assert norm(a) == norm(b)


def test_reingest_same_message_is_idempotent():
    now = _BASE
    human_state.ingest("device:r4", "I'm exhausted", now=now)
    first = store.hs_get("device:r4", "fatigue")
    human_state.ingest("device:r4", "I'm exhausted", now=now)   # identical reading, same clock
    second = store.hs_get("device:r4", "fatigue")
    assert (first["value"], first["confidence"]) == (second["value"], second["confidence"])


def test_never_downgrade_survives_full_conversation():
    v = _run("device:r5")
    # the high-confidence "exhausted" is preserved despite the later hedged "kind of tired"
    assert v["fatigue"]["value"] == "high" and v["fatigue"]["stored_confidence"] >= 0.8
