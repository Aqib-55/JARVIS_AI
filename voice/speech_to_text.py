"""
Speech-to-Text (STT) module for JARVIS AI — Local Mode.

Converts microphone audio into text using:
  - Faster-Whisper (default, local CPU inference — required in local-only mode)
  - SpeechRecognition (available only when LOCAL_AI_ONLY=false, explicit opt-in)
  - MockSTTEngine (testing)

Cloud fallback is PROHIBITED in local-only mode.
"""

import io
import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

# Core files required by faster-whisper / ctranslate2 for fully offline loading.
# Note: preprocessor_config.json is optional for Systran/faster-whisper-base in
# faster-whisper 1.2.1 (FeatureExtractor falls back to 80-bin 16kHz defaults),
# while tokenizer.json is required so tokenizers.Tokenizer never hits HF Hub.
_REQUIRED_WHISPER_FILES = (
    "config.json",
    "model.bin",
    "tokenizer.json",
)
_VOCAB_WHISPER_FILES = ("vocabulary.txt", "vocabulary.json")


def verify_whisper_model_files(model_dir: Path) -> tuple[bool, list[str]]:
    """
    Verify that a local Faster-Whisper model directory exists and contains
    all required model files for offline loading.

    Returns:
        (is_valid, missing_descriptions)
    """
    if not model_dir.exists() or not model_dir.is_dir():
        return False, [f"directory not found: {model_dir}"]

    missing: list[str] = []
    for filename in _REQUIRED_WHISPER_FILES:
        file_path = model_dir / filename
        if not file_path.is_file() or file_path.stat().st_size == 0:
            missing.append(filename)

    if not any(
        (model_dir / v).is_file() and (model_dir / v).stat().st_size > 0
        for v in _VOCAB_WHISPER_FILES
    ):
        missing.append("vocabulary.txt (or vocabulary.json)")

    preproc = model_dir / "preprocessor_config.json"
    if preproc.is_file():
        try:
            json.loads(preproc.read_text(encoding="utf-8"))
        except Exception:
            missing.append("preprocessor_config.json (corrupted JSON)")

    return len(missing) == 0, missing


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


class FasterWhisperEngine(BaseSTTEngine):
    """
    Offline neural speech recognition using faster-whisper.
    Runs locally on CPU with int8 quantization for high privacy and zero cloud dependencies.

    Model is loaded once from a verified local directory and reused for all
    subsequent transcriptions. Never downloads models at runtime or startup.
    """

    def __init__(
        self,
        model_size: str | None = None,
        language: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        model_path: str | Path | None = None,
    ) -> None:
        self.model_size = model_size or settings.WHISPER_MODEL_SIZE
        if model_path is not None:
            self.model_path = Path(model_path)
        elif model_size is not None:
            candidate = Path(model_size)
            if candidate.is_dir() or os.sep in model_size or "/" in model_size:
                self.model_path = candidate
            else:
                self.model_path = settings.WHISPER_MODEL_DIR / f"faster-whisper-{model_size}"
        else:
            self.model_path = settings.WHISPER_MODEL_PATH

        raw_lang = language or settings.WHISPER_LANGUAGE
        self.language: str | None = None if raw_lang.lower() == "auto" else raw_lang
        self.device = device or settings.WHISPER_DEVICE
        self.compute_type = compute_type or settings.WHISPER_COMPUTE_TYPE
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def _package_installed() -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        """Check that faster-whisper is installed AND local model files are present."""
        if not self._package_installed():
            return False
        ok, _ = verify_whisper_model_files(self.model_path)
        return ok

    def _validate_model_files(self) -> Path:
        """Ensure required local model files exist; never download at runtime."""
        ok, missing = verify_whisper_model_files(self.model_path)
        if not ok:
            raise RuntimeError(
                f"Local Faster-Whisper model not found or incomplete at '{self.model_path}'. "
                f"Missing: {', '.join(missing)}. "
                "Run 'python setup_local_models.py' once to download Systran/faster-whisper-base."
            )
        return self.model_path

    def _get_model(self):
        """Load the verified local Whisper model once and cache it. Thread-safe."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    if not self._package_installed():
                        raise RuntimeError(
                            "faster-whisper is not installed. "
                            "Run: pip install faster-whisper"
                        )
                    model_dir = self._validate_model_files()
                    from faster_whisper import WhisperModel
                    logger.info(
                        "Loading local Faster-Whisper model from '%s' on %s (%s)...",
                        model_dir, self.device, self.compute_type,
                    )
                    self._model = WhisperModel(
                        str(model_dir),
                        device=self.device,
                        compute_type=self.compute_type,
                        local_files_only=True,
                    )
                    logger.info("Local Faster-Whisper model loaded.")
        return self._model

    @staticmethod
    def _audio_to_float32_16k(audio_source: Any):
        """
        Convert audio input (np.ndarray, BytesIO, file path) to a 16 kHz mono float32
        NumPy array so faster-whisper never depends on PyAV's metadata_errors flag.
        """
        import numpy as np

        if isinstance(audio_source, np.ndarray):
            arr = audio_source.astype(np.float32, copy=False)
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            return arr

        import soundfile as sf

        if hasattr(audio_source, "seek"):
            audio_source.seek(0)
        data, sr = sf.read(audio_source, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != 16000 and len(data) > 0:
            target_len = max(1, int(round(len(data) * 16000 / sr)))
            data = np.interp(
                np.linspace(0, len(data) - 1, target_len),
                np.arange(len(data)),
                data,
            ).astype(np.float32)
        return data

    def transcribe_audio(
        self,
        audio_source: Any,
        language: str | None = None,
    ) -> tuple[str, str]:
        """
        Transcribe a NumPy array, WAV BytesIO buffer, or audio file path locally.

        Returns:
            (transcribed_text, detected_language)
        """
        target_lang = self.language if language is None else language
        audio_array = self._audio_to_float32_16k(audio_source)
        model = self._get_model()
        segments, info = model.transcribe(
            audio_array,
            language=target_lang,
            beam_size=2,
            vad_filter=True,
        )
        transcription = " ".join(s.text.strip() for s in segments).strip()
        lang_detected = getattr(info, "language", "unknown")
        logger.info(
            "Whisper transcription [lang=%s]: '%s'", lang_detected, transcription
        )
        return transcription, lang_detected

    def listen_and_transcribe(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 12.0,
        cancel_event: threading.Event | None = None,
    ) -> str:
        # Validate package & local model files BEFORE opening the microphone
        if not self._package_installed():
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            )
        self._validate_model_files()

        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 1.2
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                logger.info("Calibrating for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                if cancel_event and cancel_event.is_set():
                    return ""
                logger.info("Listening (timeout=%.1fs)...", timeout)
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
                if cancel_event and cancel_event.is_set():
                    return ""

            wav_data = io.BytesIO(
                audio.get_wav_data(convert_rate=16000, convert_width=2)
            )
            transcription, _ = self.transcribe_audio(wav_data)
            return transcription

        except sr.WaitTimeoutError:
            logger.info("No speech detected before timeout.")
            return ""
        except (OSError, IOError) as e:
            logger.error("Microphone hardware error: %s", e)
            return ""
        except RuntimeError as e:
            logger.error("Faster-Whisper error: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected STT error: %s", e)
            return ""


class SpeechRecognitionEngine(BaseSTTEngine):
    """
    Cloud-based speech recognition via Google Speech Recognition API.

    WARNING: This engine sends audio to Google servers.
    It is PROHIBITED in LOCAL_AI_ONLY=true mode.
    Available only when LOCAL_AI_ONLY=false and explicitly configured.
    """

    def __init__(
        self,
        language: str | None = None,
        energy_threshold: int | None = None,
        pause_threshold: float = 1.2,
    ) -> None:
        if settings.LOCAL_AI_ONLY:
            raise RuntimeError(
                "SpeechRecognitionEngine (Google STT) is prohibited when LOCAL_AI_ONLY=true. "
                "Use FasterWhisperEngine for local speech recognition."
            )
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
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                if cancel_event and cancel_event.is_set():
                    return ""
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
                if cancel_event and cancel_event.is_set():
                    return ""

            text = recognizer.recognize_google(audio, language=self.language)
            logger.info("Cloud STT result: '%s'", text)
            return text.strip()

        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            logger.error("Cloud STT network error: %s", e)
            return ""
        except (OSError, IOError) as e:
            logger.error("Microphone hardware error: %s", e)
            return ""
        except Exception as e:
            logger.error("Unexpected cloud STT error: %s", e)
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


def get_stt_engine(name: str | None = None, **kwargs: Any) -> BaseSTTEngine:
    """
    Factory function to retrieve or instantiate an STT engine.

    In LOCAL_AI_ONLY=true mode, only 'faster_whisper' and 'mock' are permitted.
    Requesting 'speech_recognition' in local-only mode raises RuntimeError.
    """
    engine_name = (name or settings.STT_ENGINE).lower().strip()

    if engine_name == "mock":
        return MockSTTEngine(**kwargs)

    if engine_name in ("faster_whisper", "faster-whisper"):
        engine = FasterWhisperEngine(**kwargs)
        if not engine._package_installed():
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Install it with: pip install faster-whisper"
            )
        ok, missing = verify_whisper_model_files(engine.model_path)
        if not ok:
            logger.warning(
                "Local Faster-Whisper model not ready at '%s' (missing: %s). "
                "Run 'python setup_local_models.py' to download it. "
                "Automatic runtime download is disabled.",
                engine.model_path,
                ", ".join(missing),
            )
        return engine

    if engine_name in ("speech_recognition", "google"):
        # This will raise RuntimeError if LOCAL_AI_ONLY=true
        return SpeechRecognitionEngine(**kwargs)

    # Fallback
    if settings.LOCAL_AI_ONLY:
        raise RuntimeError(
            f"Unknown STT engine '{engine_name}' requested in LOCAL_AI_ONLY mode. "
            "Set VOICE_STT_PROVIDER=faster_whisper in .env."
        )
    # Non-local-only fallback to Faster-Whisper if available
    logger.warning("Unknown STT engine '%s', using FasterWhisperEngine.", engine_name)
    return FasterWhisperEngine(**kwargs)
