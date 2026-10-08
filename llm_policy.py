"""Phase 1 Chat Completions policy; deterministic product authority is separate."""
from dataclasses import dataclass


FREE_CORE_MODEL = "gpt-6-luna"
FREE_CORE_REASONING = "none"
PRO_MODEL = "gpt-6.1-sol"
PRO_REASONING = "low"
REPAIR_MODEL = PRO_MODEL
REPAIR_REASONING = PRO_REASONING


@dataclass(frozen=True)
class TextModelPolicy:
    model: str
    reasoning_effort: str
    output_token_budget: int
    reasoning_token_reserve: int = 0
    temperature: float | None = None

    def request_parameters(self) -> dict:
        if self.temperature is not None and self.reasoning_effort != "none":
            raise ValueError("sampling temperature requires reasoning_effort=none")
        parameters = {
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "max_completion_tokens": self.output_token_budget + self.reasoning_token_reserve,
        }
        if self.temperature is not None:
            parameters["temperature"] = self.temperature
        return parameters


FREE_CORE = TextModelPolicy(FREE_CORE_MODEL, FREE_CORE_REASONING, 1500)
# Completion limits include reasoning. This initial reserve is not a guaranteed
# visible-output quota; live latency/truncation evals must gate production rollout.
PRO = TextModelPolicy(PRO_MODEL, PRO_REASONING, 4000, reasoning_token_reserve=4000)
REPAIR = TextModelPolicy(REPAIR_MODEL, REPAIR_REASONING, 1500, reasoning_token_reserve=4000)
PROFILE_EXTRACTION = TextModelPolicy(FREE_CORE_MODEL, FREE_CORE_REASONING, 1500, temperature=0)
LEARNING_EXTRACTION = TextModelPolicy(FREE_CORE_MODEL, FREE_CORE_REASONING, 300, temperature=0)


def chat_policy(*, is_pro: bool) -> TextModelPolicy:
    return PRO if is_pro else FREE_CORE


def nutrition_repair_policy(*, is_pro: bool) -> TextModelPolicy:
    return PRO if is_pro else REPAIR
