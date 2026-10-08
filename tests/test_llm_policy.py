"""Exact Phase 1 request contracts, including real SDK serialization (no API I/O)."""
import json
from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai import OpenAI

import llm_policy
from brain.learning.engine import HumanLearningEngine


@pytest.mark.parametrize("policy,model,effort,budget", [
    (llm_policy.FREE_CORE, "gpt-6-luna", "none", 1500),
    (llm_policy.PRO, "gpt-6.1-sol", "low", 8000),
    (llm_policy.REPAIR, "gpt-6.1-sol", "low", 5500),
    (llm_policy.PROFILE_EXTRACTION, "gpt-6-luna", "none", 1500),
    (llm_policy.LEARNING_EXTRACTION, "gpt-6-luna", "none", 300),
])
def test_exact_model_and_token_contract(policy, model, effort, budget):
    parameters = policy.request_parameters()
    assert parameters["model"] == model
    assert parameters["reasoning_effort"] == effort
    assert parameters["max_completion_tokens"] == budget
    assert "max_tokens" not in parameters
    if effort != "none":
        assert "temperature" not in parameters


@pytest.mark.parametrize("is_pro,primary,repair", [
    (False, llm_policy.FREE_CORE, llm_policy.REPAIR),
    (True, llm_policy.PRO, llm_policy.PRO),
])
def test_role_routing_does_not_compare_model_names(is_pro, primary, repair):
    assert llm_policy.chat_policy(is_pro=is_pro) is primary
    assert llm_policy.nutrition_repair_policy(is_pro=is_pro) is repair


def test_request_parameters_are_fresh_and_invalid_sampling_fails_closed():
    parameters = llm_policy.PRO.request_parameters()
    parameters["model"] = "caller-override"
    assert llm_policy.PRO.request_parameters()["model"] == "gpt-6.1-sol"
    with pytest.raises(ValueError, match="reasoning_effort=none"):
        llm_policy.TextModelPolicy("gpt-6.1-sol", "low", 4000, temperature=0).request_parameters()


@pytest.mark.parametrize("policy", [
    llm_policy.FREE_CORE, llm_policy.PRO, llm_policy.REPAIR,
    llm_policy.PROFILE_EXTRACTION, llm_policy.LEARNING_EXTRACTION,
])
@pytest.mark.parametrize("stream", [False, True])
def test_pinned_sdk_serializes_and_reads_request_contract(policy, stream):
    # Mock only HTTP: the pinned SDK builds the actual JSON request and parses
    # actual completion/SSE shapes. This proves SDK shape support, not API access.
    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text()
    pin = next(line.split("==", 1)[1] for line in requirements.splitlines()
               if line.startswith("openai=="))
    assert openai.__version__ == pin == "3.3.1"
    requests = []

    def transport(request):
        assert request.url.path == "/v1/chat/completions"
        requests.append(json.loads(request.content))
        if stream:
            chunks = [
                {"id": "synthetic", "object": "chat.completion.chunk", "created": 0,
                 "model": policy.model, "choices": [
                     {"index": 0, "delta": {"content": "{}"}, "finish_reason": None}]},
                {"id": "synthetic", "object": "chat.completion.chunk", "created": 0,
                 "model": policy.model, "choices": [
                     {"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
            return httpx2.Response(200, text=body + "data: [DONE]\n\n",
                                   headers={"Content-Type": "text/event-stream"})
        return httpx2.Response(200, json={
            "id": "synthetic", "object": "chat.completion", "created": 0,
            "model": policy.model, "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "{}"}}],
        })

    parameters = dict(messages=[{"role": "user", "content": "Return a JSON object."}],
                      stream=stream, response_format={"type": "json_object"},
                      **policy.request_parameters())
    with OpenAI(api_key="sk-synthetic-sdk-test", base_url="https://api.openai.test/v1",
                max_retries=0, http_client=httpx2.Client(
                    transport=httpx2.MockTransport(transport))) as client:
        response = client.chat.completions.create(**parameters)
        if stream:
            with response:
                chunks = list(response)
            assert chunks[0].choices[0].delta.content == "{}"
            assert chunks[-1].choices[0].finish_reason == "stop"
        else:
            assert response.choices[0].message.content == "{}"
    assert requests == [parameters]


@pytest.mark.parametrize("language,user_message", [
    ("en", "I prefer short workouts."),
    ("bg", "\u041f\u0440\u0435\u0434\u043f\u043e\u0447\u0438\u0442\u0430\u043c \u043a\u0440\u0430\u0442\u043a\u0438 \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0438."),
])
def test_learning_uses_luna_without_changing_fact_contract(monkeypatch, language, user_message):
    calls = []
    facts = {"preferences": {"duration": "short"}, "habits": {}, "constraints": {}, "patterns": {}}

    def create(**parameters):
        calls.append(parameters)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(facts)))])

    monkeypatch.setenv("OPENAI_API_KEY", "sk-synthetic-test")
    monkeypatch.setattr("brain.learning.engine.OpenAI", lambda **_kwargs:
                        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    assert HumanLearningEngine.extract_facts(user_message, "Understood.") == facts
    assert len(calls) == 1
    parameters = calls[0]
    assert {key: parameters[key] for key in llm_policy.LEARNING_EXTRACTION.request_parameters()} == {
        "model": "gpt-6-luna", "reasoning_effort": "none",
        "max_completion_tokens": 300, "temperature": 0,
    }
    assert "max_tokens" not in parameters and "response_format" not in parameters


@pytest.mark.parametrize("failure", ["api", "json"])
def test_learning_local_fallback_is_preserved(monkeypatch, failure):
    def create(**_parameters):
        if failure == "api":
            raise RuntimeError("synthetic API failure")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not JSON"))])

    monkeypatch.setenv("OPENAI_API_KEY", "sk-synthetic-test")
    monkeypatch.setattr("brain.learning.engine.OpenAI", lambda **_kwargs:
                        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    facts = HumanLearningEngine.extract_facts("I prefer short workout sessions.", "Understood.")
    assert facts["preferences"]["duration"] == "short"


def test_production_text_calls_have_no_legacy_model_or_token_parameters():
    root = Path(__file__).parents[1]
    for filename in ("app.py", "brain/learning/engine.py"):
        source = (root / filename).read_text(encoding="utf-8")
        assert "gpt-4o" not in source
        assert "max_tokens=" not in source
        assert "responses.create" not in source
