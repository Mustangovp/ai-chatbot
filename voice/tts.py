"""
APEX Voice Layer — Text-to-Speech adapter (provider-independent).

One narrow interface:

    synthesize(text, lang="en", client=None) -> (audio_bytes, mimetype)

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

_MIME = {"mp3": "audio/mpeg", "opus": "audio/ogg", "aac": "audio/aac", "wav": "audio/wav", "flac": "audio/flac"}

# The delivery style APEX should keep in its voice — calm, measured, warm but not
# theatrical. This mirrors the Personality Core WITHOUT importing it: it steers
# only the audio delivery of text the Personality Engine already produced.
_STYLE = ("Speak in a calm, grounded, quietly confident voice — an elite coach, "
          "not a hype announcer. Measured pace, warm but never theatrical. "
          "No exclamations.")


class _OpenAITTS:
    name = "openai"

    def __init__(self):
        self.model = os.getenv("APEX_TTS_MODEL", "gpt-4o-mini-tts")
        self.voice = os.getenv("APEX_TTS_VOICE", "alloy")
        self.fmt = os.getenv("APEX_TTS_FORMAT", "mp3").lower()

    def synthesize(self, text, lang, client):
        if client is None:
            raise RuntimeError("openai client not provided to TTS adapter")
        fmt = self.fmt if self.fmt in _MIME else "mp3"
        # `instructions` (voice steering) is only honoured by the gpt-4o*-tts family;
        # fall back cleanly for classic tts-1 models or older SDKs.
        kwargs = dict(model=self.model, voice=self.voice, input=text, response_format=fmt)
        try:
            resp = client.audio.speech.create(instructions=_STYLE, **kwargs)
        except TypeError:
            resp = client.audio.speech.create(**kwargs)
        except Exception:
            # Some SDK/model combos reject `instructions` at the API layer, not as TypeError.
            resp = client.audio.speech.create(**kwargs)
        audio = resp.read() if hasattr(resp, "read") else getattr(resp, "content", None)
        if not audio:
            raise RuntimeError("TTS provider returned no audio")
        return audio, _MIME[fmt]


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


def synthesize(text, lang="en", client=None):
    """text → (audio_bytes, mimetype). Raises on failure; the caller decides the HTTP status."""
    return _get().synthesize(text, lang, client)
