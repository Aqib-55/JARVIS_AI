"""
Text-to-Speech (TTS) module for JARVIS AI — Local Mode.

Converts AI text responses into natural audible speech.

Engines:
  - PiperEngine     (default, local neural TTS — required in local-only mode)
  - Pyttsx3Engine   (Windows SAPI5 offline fallback, available when LOCAL_AI_ONLY=false)
  - EdgeTTSEngine   (online Microsoft Edge TTS — PROHIBITED in local-only mode)
  - MockTTSEngine   (testing)

Cloud fallback is PROHIBITED in local-only mode.
"""

import json
import logging
import os
import re
import tempfile
import threading
import time
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from config.settings import settings

logger = logging.getLogger(__name__)


def verify_piper_model_files(
    model_dir: Path,
    voice_name: str,
) -> tuple[bool, Path | None, list[str]]:
    """
    Verify that both the Piper .onnx model and .onnx.json config exist for
    the configured voice inside model_dir.

    Returns:
        (is_valid, onnx_path_or_None, missing_or_invalid_descriptions)
    """
    if not model_dir.exists() or not model_dir.is_dir():
        return False, None, [f"directory not found: {model_dir}"]

    # Candidate layouts: direct (<dir>/<voice>.onnx) or nested (<dir>/<voice>/<voice>.onnx)
    candidate_bases = [
        model_dir / f"{voice_name}.onnx",
        model_dir / voice_name / f"{voice_name}.onnx",
    ]

    selected_onnx = candidate_bases[0]
    for candidate in candidate_bases:
        if candidate.is_file():
            selected_onnx = candidate
            break

    selected_json = Path(f"{selected_onnx}.json")
    issues: list[str] = []

    if not selected_onnx.is_file() or selected_onnx.stat().st_size == 0:
        issues.append(f"{selected_onnx.name}")

    if not selected_json.is_file() or selected_json.stat().st_size == 0:
        issues.append(f"{selected_json.name}")
    else:
        try:
            json.loads(selected_json.read_text(encoding="utf-8"))
        except Exception:
            issues.append(f"{selected_json.name} (invalid JSON)")

    if issues:
        return False, None, issues
    return True, selected_onnx, []


# ---------------------------------------------------------------------------
#  Text sanitizer (shared across engines)
# ---------------------------------------------------------------------------

def clean_text_for_speech(text: str) -> str:
    """
    Sanitize text before speech synthesis.
    Removes Markdown, code blocks, URLs, emojis and symbols
    so that speech sounds natural and clear.
    """
    if not text:
        return ""
    cleaned = text

    # Multi-line code blocks → brief note
    cleaned = re.sub(r"```[\w\-]*\n[\s\S]*?```", " Code snippet omitted. ", cleaned)
    # Inline code backticks
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Markdown links → title only
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Standalone URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Markdown headers
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    # Bold/italics
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    # List bullets and blockquotes
    cleaned = re.sub(r"^[•\*\-\+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^>\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\d+\.\s+", "", cleaned, flags=re.MULTILINE)
    # Emojis and uncommon symbols
    cleaned = re.sub(r"[^\w\s.,!?'\"():;\-]", "", cleaned)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ---------------------------------------------------------------------------
#  Abstract base
# ---------------------------------------------------------------------------

class BaseTTSEngine(ABC):
    """Abstract base class for all Text-to-Speech engines."""

    @abstractmethod
    def speak(
        self,
        text: str,
        interrupt_event: threading.Event | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> bool:
        """
        Speak the provided text aloud.
        Returns True if completed, False if interrupted or failed.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Immediately halt any active speech playback."""
        ...

    @abstractmethod
    def set_rate(self, rate: int) -> None:
        """Set speech speed (words per minute or relative rate)."""
        ...

    @abstractmethod
    def set_volume(self, volume: float) -> None:
        """Set speech volume (0.0 to 1.0)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Verify whether this TTS engine is operational on the host system."""
        ...


# ---------------------------------------------------------------------------
#  Piper TTS — Local Neural Voice
# ---------------------------------------------------------------------------

class PiperEngine(BaseTTSEngine):
    """
    Offline neural Text-to-Speech using Piper TTS.

    Uses the piper-tts Python package (GPL-licensed).
    Voice model files (.onnx + .onnx.json) must exist in PIPER_MODEL_PATH.
    Never downloads models automatically during application startup or runtime.
    """

    def __init__(
        self,
        voice: str | None = None,
        model_path: str | Path | None = None,
        volume: float | None = None,
        speed: float | None = None,
    ) -> None:
        self._voice_name = voice or settings.PIPER_VOICE
        self._model_dir = Path(model_path) if model_path is not None else settings.PIPER_MODEL_PATH
        self._volume = volume if volume is not None else settings.TTS_VOLUME
        self._speed = speed if speed is not None else settings.TTS_SPEED
        self._piper_voice = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._is_speaking = False
        self.last_error: str = ""

    @staticmethod
    def _package_installed() -> bool:
        try:
            import piper  # noqa: F401
            return True
        except ImportError:
            return False

    def _find_model_file(self) -> str | None:
        """Locate and validate both .onnx and .onnx.json files for the configured voice."""
        ok, onnx_path, _ = verify_piper_model_files(self._model_dir, self._voice_name)
        return str(onnx_path) if ok and onnx_path is not None else None

    def _validate_model_files(self) -> Path:
        """Ensure both .onnx and .onnx.json files exist; never download at runtime."""
        ok, onnx_path, issues = verify_piper_model_files(self._model_dir, self._voice_name)
        if not ok or onnx_path is None:
            raise RuntimeError(
                f"Piper voice model '{self._voice_name}' is missing or incomplete in '{self._model_dir}'. "
                f"Expected: {self._voice_name}.onnx and {self._voice_name}.onnx.json "
                f"(missing/invalid: {', '.join(issues)}). "
                "Automatic download at runtime is disabled. "
                "Run 'python setup_local_models.py' once to download the Piper voice model."
            )
        return onnx_path

    def _get_voice(self):
        """Load Piper voice once and cache it. Thread-safe."""
        if self._piper_voice is None:
            with self._lock:
                if self._piper_voice is None:
                    if not self._package_installed():
                        raise RuntimeError(
                            "piper-tts is not installed. Install it with: pip install piper-tts"
                        )
                    onnx_path = self._validate_model_files()
                    config_path = Path(f"{onnx_path}.json")
                    from piper import PiperVoice
                    logger.info("Loading Piper voice from: %s", onnx_path)
                    self._piper_voice = PiperVoice.load(
                        str(onnx_path),
                        config_path=str(config_path),
                    )
                    logger.info("Piper voice loaded.")
        return self._piper_voice

    def is_available(self) -> bool:
        """Return True only when piper-tts is installed AND both model files exist."""
        if not self._package_installed():
            return False
        ok, _, _ = verify_piper_model_files(self._model_dir, self._voice_name)
        return ok

    def set_rate(self, rate: int) -> None:
        # Piper uses speed multiplier; map WPM-like rate to multiplier
        self._speed = max(0.5, min(2.0, rate / 175.0))

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))

    def stop(self) -> None:
        """Signal active speech to immediately stop."""
        self._stop_event.set()
        self._is_speaking = False

    def synthesize_to_wav(self, text: str, output_wav_path: str | Path) -> Path:
        """
        Synthesize text into a WAV file on disk using the installed Piper Python API.
        """
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            raise ValueError("Cannot synthesize empty text.")

        voice = self._get_voice()
        from piper.config import SynthesisConfig

        syn_cfg = SynthesisConfig(
            length_scale=1.0 / max(0.5, min(2.0, self._speed)),
            volume=max(0.0, min(1.0, self._volume)),
        )
        out_path = Path(output_wav_path)
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(cleaned, wav_file, syn_config=syn_cfg)

        if not out_path.is_file() or out_path.stat().st_size <= 44:
            raise RuntimeError("Piper synthesis produced an empty WAV file.")
        return out_path

    def speak(
        self,
        text: str,
        interrupt_event: threading.Event | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> bool:
        """
        Synthesize text with Piper and play through the system speaker.
        Calls on_playback_start ONLY after WAV generation succeeds and playback starts.
        """
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            return True

        self.last_error = ""
        self._stop_event.clear()
        self._is_speaking = False
        tmp_path = ""

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name

            self.synthesize_to_wav(cleaned, tmp_path)

            if self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()):
                return False

            if on_playback_start is not None:
                on_playback_start()

            self._is_speaking = True
            played = self._play_wav(tmp_path, interrupt_event)
            if not played:
                if not self.last_error:
                    self.last_error = "Audio playback failed."
                return False

        except RuntimeError as e:
            self.last_error = str(e)
            logger.error("Piper voice error: %s", e)
            return False
        except Exception as e:
            self.last_error = str(e)
            logger.error("Piper synthesis error: %s", e)
            return False
        finally:
            self._is_speaking = False
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        return not (self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()))

    def _play_wav(self, wav_path: str, interrupt_event: threading.Event | None) -> bool:
        """Play a WAV file; check stop events during playback. Returns True if played."""
        try:
            import sounddevice as sd
            import soundfile as sf
            data, samplerate = sf.read(wav_path)
            sd.play(data, samplerate)
            # Poll for stop events during playback
            while sd.get_stream().active:
                if self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()):
                    sd.stop()
                    return False
                time.sleep(0.05)
            sd.wait()
            return True
        except Exception as sd_err:
            logger.debug("sounddevice playback unavailable (%s); trying winsound.", sd_err)
            try:
                import winsound
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                return True
            except Exception as e:
                self.last_error = f"Audio playback failed: {e}"
                logger.error("WAV playback failed: %s", e)
                return False


# ---------------------------------------------------------------------------
#  Pyttsx3 — Windows SAPI5 (offline, non-Piper fallback)
# ---------------------------------------------------------------------------

class Pyttsx3Engine(BaseTTSEngine):
    """
    Offline Text-to-Speech engine utilizing Windows SAPI5 via pyttsx3.
    Available when LOCAL_AI_ONLY=false. Not the default in local-AI mode.
    """

    def __init__(
        self,
        rate: int | None = None,
        volume: float | None = None,
        voice_id: str | None = None,
    ) -> None:
        self._rate = rate or settings.TTS_RATE
        self._volume = volume or settings.TTS_VOLUME
        self._voice_id = voice_id or settings.TTS_VOICE
        self._is_speaking = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            return engine is not None
        except Exception:
            return False

    def set_rate(self, rate: int) -> None:
        self._rate = max(100, min(300, rate))

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))

    def stop(self) -> None:
        self._stop_event.set()
        self._is_speaking = False

    def speak(
        self,
        text: str,
        interrupt_event: threading.Event | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> bool:
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            return True

        self._stop_event.clear()
        self._is_speaking = True

        sentence_pattern = re.compile(r'(?<=[.!?])\s+')
        chunks = sentence_pattern.split(cleaned)
        if not chunks:
            chunks = [cleaned]

        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass

        try:
            import pyttsx3
            notified_start = False
            with self._lock:
                for chunk in chunks:
                    if self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()):
                        return False
                    if not chunk.strip():
                        continue
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty("rate", self._rate)
                        engine.setProperty("volume", self._volume)
                        if self._voice_id:
                            engine.setProperty("voice", self._voice_id)
                        if not notified_start and on_playback_start is not None:
                            on_playback_start()
                            notified_start = True
                        engine.say(chunk.strip())
                        engine.runAndWait()
                        engine.stop()
                    except Exception as e:
                        logger.error("pyttsx3 chunk error: %s", e)
            self._is_speaking = False
            return True
        except Exception as e:
            logger.error("pyttsx3 speech error: %s", e)
            self._is_speaking = False
            return False
        finally:
            try:
                import comtypes
                comtypes.CoUninitialize()
            except Exception:
                pass


# ---------------------------------------------------------------------------
#  Edge TTS — PROHIBITED in local-only mode
# ---------------------------------------------------------------------------

class EdgeTTSEngine(BaseTTSEngine):
    """
    Online neural Text-to-Speech using Microsoft Edge TTS.
    PROHIBITED when LOCAL_AI_ONLY=true.
    """

    def __init__(self, voice: str = "en-US-GuyNeural") -> None:
        if settings.LOCAL_AI_ONLY:
            raise RuntimeError(
                "EdgeTTSEngine is prohibited when LOCAL_AI_ONLY=true. "
                "Use PiperEngine for local speech synthesis."
            )
        self._voice = voice
        self._stop_event = threading.Event()
        self._is_speaking = False

    def is_available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def set_rate(self, rate: int) -> None:
        pass

    def set_volume(self, volume: float) -> None:
        pass

    def stop(self) -> None:
        self._stop_event.set()

    def speak(
        self,
        text: str,
        interrupt_event: threading.Event | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> bool:
        raise RuntimeError("EdgeTTSEngine not permitted in local-only mode.")


# ---------------------------------------------------------------------------
#  Mock TTS — Testing
# ---------------------------------------------------------------------------

class MockTTSEngine(BaseTTSEngine):
    """
    Mock TTS engine for testing. Records spoken text without audio device dependencies.
    """

    def __init__(self) -> None:
        self.spoken_texts: list[str] = []
        self._rate = 175
        self._volume = 1.0
        self._is_speaking = False

    def is_available(self) -> bool:
        return True

    def set_rate(self, rate: int) -> None:
        self._rate = rate

    def set_volume(self, volume: float) -> None:
        self._volume = volume

    def stop(self) -> None:
        self._is_speaking = False

    def speak(
        self,
        text: str,
        interrupt_event: threading.Event | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> bool:
        cleaned = clean_text_for_speech(text)
        if interrupt_event and interrupt_event.is_set():
            return False
        if on_playback_start is not None:
            on_playback_start()
        self.spoken_texts.append(cleaned)
        return True


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------

def get_tts_engine(name: str | None = None, **kwargs: Any) -> BaseTTSEngine:
    """
    Factory function to retrieve or instantiate a TTS engine.

    In LOCAL_AI_ONLY=true mode, only 'piper' and 'mock' are permitted.
    'edge_tts' and cloud engines are blocked.
    """
    engine_name = (name or settings.TTS_ENGINE).lower().strip()

    if engine_name == "mock":
        return MockTTSEngine()

    if engine_name == "piper":
        engine = PiperEngine(**kwargs)
        if not engine._package_installed():
            if settings.LOCAL_AI_ONLY:
                raise RuntimeError(
                    "piper-tts is not installed and LOCAL_AI_ONLY=true. "
                    "Install it with: pip install piper-tts"
                )
            logger.warning("piper-tts not available, falling back to pyttsx3.")
            return Pyttsx3Engine()
        if not engine.is_available():
            logger.warning(
                "Piper voice '%s' files missing in '%s'. "
                "Run 'python setup_local_models.py' to download them. "
                "Automatic runtime download is disabled.",
                engine._voice_name,
                engine._model_dir,
            )
        return engine

    if engine_name in ("edge_tts", "edge-tts"):
        # This constructor raises RuntimeError if LOCAL_AI_ONLY=true
        return EdgeTTSEngine(**kwargs)

    if engine_name == "pyttsx3":
        return Pyttsx3Engine(**kwargs)

    # Unknown engine
    if settings.LOCAL_AI_ONLY:
        raise RuntimeError(
            f"Unknown TTS engine '{engine_name}' in LOCAL_AI_ONLY mode. "
            "Set VOICE_TTS_PROVIDER=piper in .env."
        )

    logger.warning("Unknown TTS engine '%s', defaulting to Piper.", engine_name)
    return PiperEngine(**kwargs)
