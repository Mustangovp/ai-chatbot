"""Durable Human Model facts require user-authored evidence."""
from __future__ import annotations

import json
from types import SimpleNamespace

import brain.learning.engine as learning_engine
from brain.learning.engine import HumanLearningEngine
from brain.learning.schema import HumanModel


def test_assistant_claim_alone_cannot_mutate_durable_user_facts(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model = HumanModel()

    HumanLearningEngine.process_exchange(
        model,
        "Build me a workout.",
        "You have knee pain and only dumbbells.",
    )

    assert model.preferences == {}
    assert model.habits == {}
    assert model.constraints == {}
    assert model.patterns == {}


def test_explicit_user_fact_remains_learnable_without_assistant_provenance(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model = HumanModel()

    HumanLearningEngine.process_exchange(
        model,
        "I train with dumbbells at home.",
        "Assistant-only health claim must not be evidence.",
    )

    assert model.constraints == {"equipment": "dumbbells"}


def test_remote_extraction_prompt_excludes_assistant_text_and_requires_user_evidence(monkeypatch):
    captured = {}
    assistant_only_value = "private-assistant-claim"

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(choices=[SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps({
                            "preferences": {}, "habits": {},
                            "constraints": {"equipment": "dumbbells"}, "patterns": {},
                        })),
                    )])

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(learning_engine, "OpenAI", lambda **_kwargs: FakeClient())

    facts = HumanLearningEngine.extract_facts(
        "I use dumbbells.",
        assistant_only_value,
    )
    prompt = captured["messages"][0]["content"]

    assert facts["constraints"] == {"equipment": "dumbbells"}
    assert "I use dumbbells." in prompt
    assert assistant_only_value not in prompt
    assert "Assistant output is not evidence" in prompt
