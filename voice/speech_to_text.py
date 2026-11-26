"""
Speech-to-Text (STT) module for JARVIS AI — Local Mode.

Converts microphone audio into text using:
  - Faster-Whisper (default, local CPU INT8 inference)
  - MockSTTEngine (testing)

Cloud STT services (such as Google SpeechRecognition) are removed/prohibited.
"""

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
        """
        Capture a single spoken utterance via local sounddevice + Silero VAD
        and transcribe it locally with Faster-Whisper (used for standalone /voice PTT).
        """
        if not self._package_installed():
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            )
        self._validate_model_files()

        from voice.wake_word import MicrophoneCapture, SileroSpeechEndpointDetector

        mic = MicrophoneCapture()
        if not mic.start():
            logger.error("Microphone unavailable: %s", mic.last_error)
            return ""

        vad = SileroSpeechEndpointDetector(max_utterance_seconds=phrase_time_limit)
        try:
            audio_f32 = vad.capture_utterance(
                read_chunk_fn=mic.read_frame,
                await_speech_timeout=timeout,
                cancel_event=cancel_event,
            )
        finally:
            mic.stop()

        if audio_f32 is None or len(audio_f32) == 0:
            logger.info("No speech detected before timeout.")
            return ""

        try:
            transcription, _ = self.transcribe_audio(audio_f32)
            return transcription
        except RuntimeError as e:
            logger.error("Faster-Whisper error: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected STT error: %s", e)
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
    Factory function to retrieve or instantiate a local STT engine.

    Only 'faster_whisper' and 'mock' are permitted. Cloud/legacy engines are blocked.
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
        raise RuntimeError(
            "Cloud/legacy SpeechRecognition STT is removed and prohibited when LOCAL_AI_ONLY=true. "
            "Use 'faster_whisper' for local speech recognition."
        )

    if settings.LOCAL_AI_ONLY:
        raise RuntimeError(
            f"Unknown STT engine '{engine_name}' requested in LOCAL_AI_ONLY mode. "
            "Set VOICE_STT_PROVIDER=faster_whisper in .env."
        )
    raise ValueError(f"Unsupported STT engine '{engine_name}'. Use 'faster_whisper'.")
