"""
Speech-to-Text (STT) module for JARVIS AI.

Converts microphone audio into text with:
- Ambient noise calibration and dynamic energy thresholding
- Silence and pause detection
- Recording cancellation
- Robust microphone error handling
- Modular engine architecture (SpeechRecognition, Faster-Whisper, and Mock)
"""

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


class BaseSTTEngine(ABC):
    """Abstract base class for all Speech-to-Text engines."""

    @abstractmethod
    def listen_and_transcribe(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 12.0,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """
        Record audio from the microphone and transcribe it into text.

        Args:
            timeout: Maximum seconds to wait for speech to begin.
            phrase_time_limit: Maximum duration of speech to capture.
            cancel_event: Event to cancel active listening.

        Returns:
            Transcribed text string, or empty string if no speech or cancelled.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Verify whether microphone and recognition dependencies are operational."""
        ...


class SpeechRecognitionEngine(BaseSTTEngine):
    """
    Speech recognition engine utilizing the SpeechRecognition library.
    Provides ambient noise adaptation, energy threshold calibration,
    and automatic silence detection.
    """

    def __init__(
        self,
        language: str | None = None,
        energy_threshold: int | None = None,
        pause_threshold: float = 1.2,
    ) -> None:
        self.language = language or settings.STT_LANGUAGE
        self.energy_threshold = energy_threshold or settings.ENERGY_THRESHOLD
        self.pause_threshold = pause_threshold

    def is_available(self) -> bool:
        try:
            import speech_recognition as sr
            mics = sr.Microphone.list_microphone_names()
            return len(mics) > 0
        except Exception as e:
            logger.warning("Microphone inspection failed: %s", e)
            return False

    def listen_and_transcribe(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 12.0,
        cancel_event: threading.Event | None = None,
    ) -> str:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self.energy_threshold
        recognizer.pause_threshold = self.pause_threshold
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                logger.info("Calibrating for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=0.6)

                if cancel_event and cancel_event.is_set():
                    return ""

                logger.info("Listening for speech (timeout=%.1fs)...", timeout)
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

                if cancel_event and cancel_event.is_set():
                    return ""

            logger.info("Transcribing captured audio...")
            text = recognizer.recognize_google(audio, language=self.language)
            logger.info("Transcription result: '%s'", text)
            return text.strip()

        except sr.WaitTimeoutError:
            logger.info("No speech detected before timeout.")
            return ""
        except sr.UnknownValueError:
            logger.info("Audio received but speech could not be understood.")
            return ""
        except sr.RequestError as e:
            logger.error("Recognition service network error: %s", e)
            return ""
        except (OSError, IOError) as e:
            logger.error("Microphone hardware error: %s", e)
            return ""
        except Exception as e:
            logger.error("Unexpected STT error: %s", e)
            return ""


class FasterWhisperEngine(BaseSTTEngine):
    """
    Offline neural speech recognition using faster-whisper.
    Runs locally on CPU with int8 quantization for high privacy and zero cloud dependencies.
    """

    def __init__(
        self,
        model_size: str | None = None,
        language: str = "en",
    ) -> None:
        self.model_size = model_size or settings.WHISPER_MODEL_SIZE
        self.language = language
        self._model = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            import faster_whisper
            return True
        except ImportError:
            return False

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from faster_whisper import WhisperModel
                    logger.info("Loading local Faster-Whisper model (%s)...", self.model_size)
                    self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def listen_and_transcribe(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 12.0,
        cancel_event: threading.Event | None = None,
    ) -> str:
        import io
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 1.2
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                if cancel_event and cancel_event.is_set():
                    return ""
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                if cancel_event and cancel_event.is_set():
                    return ""

            wav_data = io.BytesIO(audio.get_wav_data())
            model = self._get_model()

            segments, _ = model.transcribe(wav_data, language=self.language, beam_size=2)
            transcription = " ".join(s.text.strip() for s in segments)
            return transcription.strip()

        except Exception as e:
            logger.error("Faster-Whisper error: %s", e)
            return ""


class MockSTTEngine(BaseSTTEngine):
    """
    Mock STT engine for automated testing without audio hardware.
    Populates recognized text from an in-memory queue.
    """

    def __init__(self, queue: list[str] | None = None) -> None:
        self.queue: list[str] = queue or []
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    def enqueue(self, text: str) -> None:
        self.queue.append(text)

    def listen_and_transcribe(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 12.0,
        cancel_event: threading.Event | None = None,
    ) -> str:
        self.call_count += 1
        if cancel_event and cancel_event.is_set():
            return ""
        if self.queue:
            return self.queue.pop(0)
        return ""


def get_stt_engine(name: str = "speech_recognition", **kwargs: Any) -> BaseSTTEngine:
    """
    Factory function to retrieve or instantiate an STT engine.
    """
    clean_name = name.lower().strip()
    if clean_name == "mock":
        return MockSTTEngine(**kwargs)
    elif clean_name == "faster_whisper":
        engine = FasterWhisperEngine(**kwargs)
        if engine.is_available():
            return engine
        logger.warning("faster-whisper unavailable, falling back to speech_recognition.")
        return SpeechRecognitionEngine(**kwargs)
    else:
        # Default SpeechRecognition
        return SpeechRecognitionEngine(**kwargs)
