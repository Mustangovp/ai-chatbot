"""Restricted-tester API boundary. Missing bounds deny BEFORE provider I/O.

All retries reserve separately; SDK retries are disabled only inside this test
scope. No prompts, audio, transcripts or API credentials enter budget records.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import math
import os
import uuid
from types import SimpleNamespace

from flask import g, has_request_context, request
from sqlalchemy import select

import db
from voice.safety import SUBJECT, control
from voice.session_store import Denied, SessionStore


_principal = ContextVar("live_voice_cost_principal", default=None)


@dataclass(frozen=True)
class Principal:
    account: str
    session: str


def capture():
    current = _principal.get()
    if current is not None: return current
    if not has_request_context(): return None
    # The executable loopback mock never calls a real provider or uses real keys.
    if (os.getenv("APEX_LIVE_VOICE_TRANSPORT") == "mock"
            and request.host.split(":")[0] in {"localhost", "127.0.0.1"}
            and request.remote_addr in {"127.0.0.1", "::1"}
            and not any(name.lower().startswith(("x-forwarded-", "forwarded")) for name in request.headers.keys())):
        return None
    sid = request.cookies.get("apex_session", "")
    if g.get("user"):
        try: account = str(uuid.UUID(str(g.user["id"])))
        except (ValueError, TypeError, KeyError): return None
    else:
        # A revoked/expired cookie is NOT authentication. Its durable owner may
        # only identify a restricted budget subject; reserve() will reject it.
        try: session_id = uuid.UUID(sid)
        except (ValueError, TypeError): return None
        with control.engine.connect() as connection:
            row = connection.execute(select(db.sessions.c.user_id).where(db.sessions.c.id == session_id)).first()
        if not row: return None
        account = str(row[0])
    # Track a provisioned account even when OFF, revoked, or voice=false: those
    # values must not turn existing /chat and /speak into a budget bypass.
    with control.engine.connect() as connection:
        rows = connection.execute(select(db.user_preferences.c.subject, db.user_preferences.c.data).where(
            db.user_preferences.c.subject.in_([SessionStore.subject(account), SUBJECT]))).all()
    tracked = False
    for subject, data in rows:
        if subject != SUBJECT:
            tracked = True
        else:
            if not isinstance(data, dict) or not isinstance(data.get("tester"), str):
                raise Denied("invalid_test_budget")
            if str(uuid.UUID(data["tester"])) != data["tester"]:
                raise Denied("invalid_test_budget")
            tracked = tracked or data["tester"] == account
    if tracked: return Principal(account, sid)
    return None


@contextmanager
def scope(principal):
    token = _principal.set(principal)
    try: yield
    finally: _principal.reset(token)


def quote(kind, parameters, *, tts_pilot=False):
    """Conservative internal usage envelope, not promised provider billing.

    Text byte counts bound BPE content tokens, with additional protocol overhead.
    Only bounded text-only Chat Completions are supported. Rates reserve at least
    10x current standard GPT-6 prices; actual usage is reconciled at standard rates.
    """
    model = parameters.get("model")
    if kind == "gpt6":
        messages = parameters.get("messages")
        output = parameters.get("max_completion_tokens")
        formatting = parameters.get("response_format")
        permitted = {"model", "messages", "max_completion_tokens", "reasoning_effort", "temperature",
                     "response_format", "stream", "stream_options", "seed"}
        if (set(parameters) - permitted or model not in {"gpt-6-luna", "gpt-6.1-sol"} or type(output) is not int
                or not 1 <= output <= 8000 or not isinstance(messages, list) or not messages
                or parameters.get("tools") or parameters.get("functions")
                or parameters.get("service_tier") not in {None, "default"}
                or formatting is not None and (not isinstance(formatting, dict)
                    or set(formatting) != {"type"} or formatting["type"] not in {"text", "json_object"})
                or any(not isinstance(item, dict) or not isinstance(item.get("content"), str)
                       or item.get("role") not in {"system", "user", "assistant", "developer"}
                       for item in messages)):
            raise Denied("cost_bound_unavailable")
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 4096 + 64 * len(messages)
        if input_bound > 200000: raise Denied("cost_bound_unavailable")
        rates = (1, 5) if model == "gpt-6-luna" else (20, 100)
        return input_bound * rates[0] + output * rates[1], input_bound, output
    if kind == "tts":
        if tts_pilot:
            return mini_tts_pilot_estimate(parameters), None, None
        # Character-billed legacy models have a bounded cost for bounded input.
        # The existing mini-TTS model exposes no supported audio-output cap; do
        # NOT invent one or switch the user's model to make the release pass.
        text = parameters.get("input")
        if (set(parameters) - {"model", "input", "voice", "response_format", "instructions", "speed"}
                or model not in {"tts-1", "tts-1-hd"} or not isinstance(text, str)
                or not 1 <= len(text) <= 1600 or not isinstance(parameters.get("voice", "alloy"), str)):
            raise Denied("tts_cost_bound_unavailable")
        return len(text.encode("utf-8")) * 60, None, None
    raise Denied("cost_bound_unavailable")


def mini_tts_pilot_estimate(parameters):
    """Owner-approved restricted-pilot estimate, never an invoice guarantee.

    $0.10 for <=400 characters budgets a hypothetical 8000 audio output tokens
    ($0.096) plus 2000 text input tokens ($0.0012) at published rates. The audio
    allowance is NOT enforced by the Speech API. This is NOT an invoice bound.
    Only a durable approval for the verified tester may select this estimate.
    """
    text, instructions = parameters.get("input"), parameters.get("instructions", "")
    if (set(parameters) - {"model", "input", "voice", "response_format", "instructions"}
            or parameters.get("model") != "gpt-4o-mini-tts" or not isinstance(text, str)
            or not text.strip() or not 1 <= len(text) <= 400 or not isinstance(instructions, str)
            or len(instructions) > 512 or parameters.get("voice", "alloy") not in {"ash", "alloy"}
            or parameters.get("response_format", "mp3") not in {"mp3", "opus", "aac", "wav", "flac"}):
        raise Denied("tts_estimate_unavailable")
    return 100_000


def actual_text_cost(model, usage, input_bound, output_bound):
    prompt, completion = getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
    if (type(prompt) is not int or type(completion) is not int or prompt < 0 or completion < 0
            or prompt > input_bound or completion > output_bound): return None
    return math.ceil(prompt * .1 + completion * .5) if model == "gpt-6-luna" else prompt * 2 + completion * 10


def settle_text(grant, model, usage, inputs, outputs):
    prompt, completion = getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
    if (type(prompt) is int and prompt > inputs or type(completion) is int and completion > outputs):
        control.set_enabled(False)
        raise Denied("provider_usage_bound_violated")
    actual = actual_text_cost(model, usage, inputs, outputs)
    if actual is not None:
        try: control.reconcile(grant, actual)
        except Exception: pass  # Keep the full reservation; do not invent an ACK.


class ProtectedClient:
    def __init__(self, raw):
        self.raw = raw
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: self.call("gpt6", kwargs)))
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=lambda **kwargs: self.call("tts", kwargs)))

    def __getattr__(self, name): return getattr(self.raw, name)

    def with_options(self, **kwargs):
        # Returning the raw SDK client here would bypass account budget checks.
        return ProtectedClient(self.raw.with_options(**kwargs))

    def call(self, kind, parameters):
        principal = capture()
        if principal is None:
            target = self.raw.chat.completions if kind == "gpt6" else self.raw.audio.speech
            return target.create(**parameters)
        policy = control.require(principal.account)
        tts_pilot = kind == "tts" and policy.get("tts_pilot_approved") is True
        maximum, inputs, outputs = quote(kind, parameters, tts_pilot=tts_pilot)
        grant = control.reserve(principal.account, principal.session, kind, maximum, tts_pilot=tts_pilot)
        options = dict(parameters)
        if kind == "gpt6" and options.get("stream"):
            options["stream_options"] = {"include_usage": True}
        try:
            raw = self.raw.with_options(max_retries=0, timeout=20)
            target = raw.chat.completions if kind == "gpt6" else raw.audio.speech
        except Exception:
            if kind == "tts": control.finish_tts(grant, unused=True)
            raise
        if kind == "tts":
            try:
                control.tts_submitted(grant)
            except Exception:
                control.finish_tts(grant, unused=True)
                raise
        result = target.create(**options)  # Failure/unknown usage keeps the full reservation.
        if kind == "gpt6" and options.get("stream"):
            return self.stream(result, principal, grant, options["model"], inputs, outputs)
        control.require(principal.account, grant["epoch"])
        if kind == "gpt6":
            settle_text(grant, options["model"], getattr(result, "usage", None), inputs, outputs)
        else:
            return ReservedSpeech(result, principal, grant)
        return result

    @staticmethod
    def stream(result, principal, grant, model, inputs, outputs):
        terminal, usage = False, None
        try:
            for chunk in result:
                control.require(principal.account, grant["epoch"])
                if getattr(chunk, "usage", None) is not None: usage = chunk.usage
                terminal = terminal or any(getattr(choice, "finish_reason", None) for choice in chunk.choices)
                yield chunk
            if terminal and usage is not None:
                settle_text(grant, model, usage, inputs, outputs)
        finally:
            result.close()


class ReservedSpeech:
    """Hold the shared synthesis slot until the full binary response is read.

    Binary audio has no trustworthy numeric usage: retain the cost reservation.
    Failed/abandoned reads also retain the slot, including across worker restart.
    """
    def __init__(self, result, principal, grant):
        self.result, self.principal, self.grant = result, principal, grant

    def read(self):
        audio = self.result.read()
        control.require(self.principal.account, self.grant["epoch"])
        control.finish_tts(self.grant)
        return audio

    def close(self):
        close = getattr(self.result, "close", None)
        if callable(close): close()


def protect(client):
    return client if isinstance(client, ProtectedClient) else ProtectedClient(client)
