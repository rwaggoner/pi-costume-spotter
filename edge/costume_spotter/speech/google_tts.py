"""Google Cloud TTS engine: the optional premium voice (ADR-005).

Needs the ``gcp`` extra and application-default credentials. Note the request
asks for LINEAR16 (WAV) explicitly — Google defaults to MP3, and the TtsEngine
contract promises WAV so players stay engine-agnostic.
"""

from costume_spotter.speech.base import TtsEngine


class GoogleTtsEngine(TtsEngine):
    """Text → WAV via Google Cloud Text-to-Speech (Neural2 voice)."""

    name = "google"

    def __init__(self, voice_name: str = "en-US-Neural2-J", language_code: str = "en-US") -> None:
        try:
            from google.cloud import texttospeech
        except ImportError as exc:
            raise RuntimeError(
                "TTS_ENGINE=google needs the gcp extra: pip install -e \".[gcp]\""
            ) from exc
        self._tts = texttospeech
        self._client = texttospeech.TextToSpeechClient()
        self._voice = texttospeech.VoiceSelectionParams(
            language_code=language_code, name=voice_name
        )
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16  # WAV, per the port contract
        )

    def synthesize(self, text: str) -> bytes:
        response = self._client.synthesize_speech(
            input=self._tts.SynthesisInput(text=text),
            voice=self._voice,
            audio_config=self._audio_config,
        )
        return response.audio_content
