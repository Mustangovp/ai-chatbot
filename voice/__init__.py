"""
APEX Voice Layer — provider-independent speech transport.

This package is the ONLY place that knows which vendor turns text into audio.
The Brain, the /chat pipeline, the Personality Engine and the UI never import a
provider directly — they call `synthesize(...)`, so the provider can be replaced
(OpenAI → ElevenLabs → local) by adding one adapter and flipping an env flag,
with zero change to reasoning or interface.
"""
from voice.tts import synthesize, provider_name  # noqa: F401
