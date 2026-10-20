"""
APEX Voice Layer — Text-to-Speech adapter (provider-independent).

One narrow interface:

    synthesize(text, lang="en", client=None, voice=None) -> (audio_bytes, mimetype)

The default provider is OpenAI TTS (`gpt-4o-mini-tts`), but the caller (the
/speak route) never depends on that — it depends on this function. Swapping
vendors means adding another `_Provider` and selecting it via APEX_TTS_PROVIDER;
the Brain, the reasoning pipeline and the UI stay untouched.

Config (all optional, env-driven):
  APEX_TTS_PROVIDER   openai            (default; the only one shipped today)
  APEX_TTS_MODEL      gpt-4o-mini-tts
  APEX_TTS_VOICE      alloy
  APEX_TTS_FORMAT     mp3
"""
import os
import time

MAX_INPUT_CHARACTERS = 1600


def validate_input(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("invalid_tts_input")
    if len(text) > MAX_INPUT_CHARACTERS:
        raise ValueError("tts_input_too_long")
    return text.strip()

_MIME = {"mp3": "audio/mpeg", "opus": "audio/ogg", "aac": "audio/aac", "wav": "audio/wav", "flac": "audio/flac"}

# The delivery style APEX should keep in its voice — calm, conversational, warm but not
# theatrical. This mirrors the Personality Core WITHOUT importing it: it steers
# only the audio delivery of text the Personality Engine already produced.
_STYLE = ("Speak naturally and confidently, like a coach in a real conversation. "
          "Use a fluent conversational pace, short natural pauses and clear articulation. "
          "Be warm and grounded, never rushed, drawn-out, theatrical or a hype announcer.")


class SpeechStream:
    """One provider response. Incomplete consumption never acknowledges synthesis.

    Timings are monotonic milliseconds, with no text, audio or identity logged.
    The byte cap is an operational download limit, NOT a provider billing cap.
    """
    def __init__(self, response, context, started, clock=time.monotonic):
        self.response, self.context, self.started, self.clock = response, context, started, clock
        self.timings = {"tts_headers": self.elapsed()}
        self.closed = False

    def elapsed(self):
        return max(0, round((self.clock() - self.started) * 1000))

    def chunks(self):
        size = 0
        try:
            for chunk in self.response.iter_bytes(chunk_size=4096):
                if not chunk:
                    continue
                size += len(chunk)
                if size > 4 * 1024 * 1024 or self.elapsed() > 20000:
                    raise RuntimeError("tts_stream_limit")
                self.timings.setdefault("tts_first_audio", self.elapsed())
                yield chunk
            if not size:
                raise RuntimeError("empty_tts_stream")
            self.timings["tts_complete"] = self.elapsed()
        finally:
            self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.context.__exit__(None, None, None)


class _OpenAITTS:
    name = "openai"

    def __init__(self):
        self.model = os.getenv("APEX_TTS_MODEL", "gpt-4o-mini-tts")
        self.voice = os.getenv("APEX_TTS_VOICE", "alloy")
        self.fmt = os.getenv("APEX_TTS_FORMAT", "mp3").lower()

    def parameters(self, text, lang, voice=None):
        text = validate_input(text)
        fmt = self.fmt if self.fmt in _MIME else "mp3"
        # Select supported arguments before submission. An error is not evidence
        # that a billable request did not run, so never retry without instructions.
        kwargs = dict(model=self.model, voice=voice or self.voice, input=text, response_format=fmt)
        locale = "English (en-US)" if str(lang).lower().startswith("en") else "Bulgarian (bg-BG)"
        instructions = _STYLE + f" Speak the supplied text in {locale}. Do not translate it or switch languages."
        if self.model not in {"tts-1", "tts-1-hd"}:
            kwargs["instructions"] = instructions
        return kwargs, _MIME[fmt]

    def synthesize(self, text, lang, client, voice=None):
        kwargs, mime = self.parameters(text, lang, voice)
        if client is None:
            raise RuntimeError("openai client not provided to TTS adapter")
        configure = getattr(client, "with_options", None)
        bounded = configure(max_retries=0, timeout=20) if callable(configure) else client
        resp = bounded.audio.speech.create(**kwargs)
        try:
            audio = resp.read() if hasattr(resp, "read") else getattr(resp, "content", None)
        finally:
            close = getattr(resp, "close", None)
            if callable(close): close()
        if not audio:
            raise RuntimeError("TTS provider returned no audio")
        return audio, mime

    def stream(self, text, lang, client, voice=None):
        kwargs, mime = self.parameters(text, lang, voice)
        if mime != "audio/mpeg":
            raise ValueError("tts_stream_format_unavailable")
        started = time.monotonic()
        bounded = client.with_options(max_retries=0, timeout=20)
        context = bounded.audio.speech.with_streaming_response.create(**kwargs)
        response = context.__enter__()
        return SpeechStream(response, context, started)


_PROVIDERS = {"openai": _OpenAITTS}
_active = None


def _get():
    global _active
    if _active is None:
        key = os.getenv("APEX_TTS_PROVIDER", "openai").strip().lower()
        _active = _PROVIDERS.get(key, _OpenAITTS)()
    return _active


def provider_name() -> str:
    return _get().name


def synthesize(text, lang="en", client=None, voice=None):
    """text → (audio_bytes, mimetype). Raises on failure; the caller decides the HTTP status."""
    return _get().synthesize(text, lang, client, voice=voice)


def stream_supported():
    return isinstance(_get(), _OpenAITTS) and _get().fmt == "mp3"


def stream(text, lang="en", client=None, voice=None):
    return _get().stream(text, lang, client, voice=voice)
