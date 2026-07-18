"""Speech synthesis and transcription, isolated from chat orchestration."""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr  # type: ignore
except Exception as exc:  # noqa: BLE001
    sr = None  # type: ignore[assignment]
    logger.info("speech_recognition is unavailable; transcription disabled (%s)", exc)


class SpeechService:
    """Wraps optional TTS (VOICEVOX) and speech recognition backends."""

    def __init__(self, enable_tts: Optional[bool] = None):
        if enable_tts is None:
            enable_tts = os.getenv('ENABLE_TTS', 'false').lower() in {'1', 'true', 'yes', 'on'}

        self.tts = None
        if enable_tts:
            try:
                from ..text_to_speech import TextToSpeech

                self.tts = TextToSpeech()
            except Exception:
                logger.exception("Failed to initialise text-to-speech")

    @property
    def tts_enabled(self) -> bool:
        return self.tts is not None

    @property
    def transcription_available(self) -> bool:
        return sr is not None

    def synthesize(self, text: str) -> bytes:
        if not text:
            raise ValueError("Text must not be empty")
        if self.tts is None:
            raise RuntimeError("Text-to-speech is not enabled")
        return self.tts.synthesise(text)

    def transcribe(self, audio_data: List[float], sample_rate: int) -> Tuple[str, Optional[float]]:
        """Transcribe PCM samples; returns (transcript, confidence)."""
        if sr is None:
            raise RuntimeError("Speech recognition is not available")
        if sample_rate <= 0:
            raise ValueError("Sample rate must be a positive integer")
        if not audio_data:
            raise ValueError("Audio data is empty")

        audio_array = np.array(audio_data, dtype=np.float32)
        if not np.isfinite(audio_array).all():
            raise ValueError("Audio data contains invalid values")

        recognizer = sr.Recognizer()
        temp_file: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                temp_file = tmp.name
                pcm_audio = np.clip(audio_array, -1.0, 1.0)
                pcm_bytes = (pcm_audio * 32767).astype(np.int16).tobytes()
                with wave.open(tmp.name, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(pcm_bytes)

            with sr.AudioFile(temp_file) as source:
                audio = recognizer.record(source)

            result = recognizer.recognize_google(audio, language='ja-JP', show_all=True)
            transcript = ''
            confidence: Optional[float] = None
            if isinstance(result, dict):
                alternatives = result.get('alternative') or []
                if alternatives:
                    primary = alternatives[0]
                    transcript = primary.get('transcript', '')
                    confidence = primary.get('confidence')
            if not transcript:
                transcript = recognizer.recognize_google(audio, language='ja-JP')
            return transcript, confidence
        except sr.UnknownValueError as exc:
            raise RuntimeError("Speech recognition could not understand the audio input") from exc
        except sr.RequestError as exc:
            raise RuntimeError(f"Speech recognition service request failed: {exc}") from exc
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    logger.debug("Temporary audio file cleanup failed", exc_info=True)
