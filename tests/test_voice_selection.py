import types

import app as appmod
from voice import tts


class _SpeechClient:
    def __init__(self):
        self.calls = []
        self.audio = types.SimpleNamespace(
            speech=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(read=lambda: b"audio")


def test_openai_tts_passes_ash_and_alloy_per_request(monkeypatch):
    monkeypatch.setenv("APEX_TTS_VOICE", "default-voice")
    provider = tts._OpenAITTS()
    client = _SpeechClient()

    provider.synthesize("first", "en", client, voice="ash")
    provider.synthesize("second", "en", client, voice="alloy")

    assert [call["voice"] for call in client.calls] == ["ash", "alloy"]
    assert provider.voice == "default-voice"


def test_openai_tts_uses_the_configured_default_when_voice_is_missing(monkeypatch):
    monkeypatch.setenv("APEX_TTS_VOICE", "default-voice")
    provider = tts._OpenAITTS()
    client = _SpeechClient()

    provider.synthesize("hello", "en", client)

    assert client.calls[0]["voice"] == "default-voice"


def test_speak_allows_only_selector_voice_ids(monkeypatch):
    calls = []

    def synthesize(*_args, **kwargs):
        calls.append(kwargs.get("voice"))
        return b"audio", "audio/mpeg"

    monkeypatch.setattr(appmod.apex_voice, "synthesize", synthesize)
    client = appmod.app.test_client()

    assert client.post("/speak", json={"text": "one", "voice": "ash"}).status_code == 200
    assert client.post("/speak", json={"text": "two", "voice": "alloy"}).status_code == 200
    assert client.post("/speak", json={"text": "three"}).status_code == 200
    invalid = client.post("/speak", json={"text": "four", "voice": "arbitrary"})
    invalid_type = client.post("/speak", json={"text": "five", "voice": ["ash"]})

    assert calls == ["ash", "alloy", None]
    assert invalid.status_code == 400
    assert invalid.get_json() == {"error": "invalid_voice"}
    assert invalid_type.status_code == 400
    assert invalid_type.get_json() == {"error": "invalid_voice"}
