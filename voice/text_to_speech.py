"""
Text-to-Speech (TTS) module for JARVIS AI.

Converts AI text responses into natural audible speech with:
- Markdown and symbol sanitization
- Sentence chunking for responsive playback
- Immediate stop and interrupt handling
- Offline Windows SAPI5 (`pyttsx3`) engine by default
- Optional high-fidelity neural voices (`edge-tts`)
- Mock engine for automated unit tests
"""

import logging
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


def clean_text_for_speech(text: str) -> str:
    """
    Sanitize text before speech synthesis.
    Removes Markdown syntax, code blocks, URLs, emojis, and symbols
    so that speech sounds natural and clear.
    """
    if not text:
        return ""

    cleaned = text

    # 1. Replace multi-line code blocks with brief note
    cleaned = re.sub(r"```[\w\-]*\n[\s\S]*?```", " Code snippet omitted. ", cleaned)

    # 2. Replace inline code backticks: `variable` -> variable
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # 3. Replace Markdown links: [Title](https://...) -> Title
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)

    # 4. Remove standalone URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)

    # 5. Remove Markdown headers (e.g. ### Header -> Header)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

    # 6. Remove bold/italics: **text**, *text*, __text__, _text_
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)

    # 7. Remove Markdown list bullets and blockquotes
    cleaned = re.sub(r"^[•\*\-\+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^>\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\d+\.\s+", "", cleaned, flags=re.MULTILINE)

    # 8. Remove emojis and uncommon symbols
    cleaned = re.sub(r"[^\w\s.,!?'\"():;\-]", "", cleaned)

    # 9. Normalize multiple spaces and newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


class BaseTTSEngine(ABC):
    """Abstract base class for all Text-to-Speech engines."""

    @abstractmethod
    def speak(self, text: str, interrupt_event: threading.Event | None = None) -> bool:
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
        """Set speech speed (words per minute)."""
        ...

    @abstractmethod
    def set_volume(self, volume: float) -> None:
        """Set speech volume (0.0 to 1.0)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Verify whether this TTS engine is operational on the host system."""
        ...


class Pyttsx3Engine(BaseTTSEngine):
    """
    Offline Text-to-Speech engine utilizing Windows SAPI5 via pyttsx3.
    Operates completely locally with zero network calls and low latency.
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
        """Signal active speech to immediately stop."""
        self._stop_event.set()
        self._is_speaking = False

    def speak(self, text: str, interrupt_event: threading.Event | None = None) -> bool:
        """
        Speak text in sentence chunks, checking for interrupt signals between chunks.
        """
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            return True

        self._stop_event.clear()
        self._is_speaking = True

        # Split text into manageable sentence chunks
        sentence_pattern = re.compile(r'(?<=[.!?])\s+')
        chunks = [s.strip() for s in sentence_pattern.split(cleaned) if s.strip()]
        if not chunks:
            chunks = [cleaned]

        with self._lock:
            try:
                import comtypes
                import pyttsx3
                # Initialize COM for the active thread
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass

                engine = pyttsx3.init()
                engine.setProperty("rate", self._rate)
                engine.setProperty("volume", self._volume)

                if self._voice_id:
                    engine.setProperty("voice", self._voice_id)

                for chunk in chunks:
                    # Check interrupt conditions
                    if self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()):
                        logger.info("TTS playback interrupted by user.")
                        try:
                            engine.stop()
                        except Exception:
                            pass
                        self._is_speaking = False
                        return False

                    engine.say(chunk)
                    engine.runAndWait()

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


class EdgeTTSEngine(BaseTTSEngine):
    """
    Online neural Text-to-Speech using edge-tts.
    Produces human-like voices (e.g. en-US-GuyNeural, en-US-AriaNeural).
    """

    def __init__(self, voice: str = "en-US-GuyNeural") -> None:
        self._voice = voice
        self._rate = "+0%"
        self._volume = "+0%"
        self._is_speaking = False
        self._stop_event = threading.Event()

    def is_available(self) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            return False

    def set_rate(self, rate: int) -> None:
        pct = int(((rate - 175) / 175) * 100)
        sign = "+" if pct >= 0 else ""
        self._rate = f"{sign}{pct}%"

    def set_volume(self, volume: float) -> None:
        pct = int((volume - 1.0) * 100)
        sign = "+" if pct >= 0 else ""
        self._volume = f"{sign}{pct}%"

    def stop(self) -> None:
        self._stop_event.set()
        self._is_speaking = False

    def speak(self, text: str, interrupt_event: threading.Event | None = None) -> bool:
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            return True

        self._stop_event.clear()
        self._is_speaking = True

        import asyncio
        import tempfile
        import edge_tts

        try:
            # Generate speech audio file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_audio = f.name

            async def _synthesize():
                communicate = edge_tts.Communicate(cleaned, self._voice, rate=self._rate, volume=self._volume)
                await communicate.save(temp_audio)

            asyncio.run(_synthesize())

            # Play audio file on Windows
            if self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()):
                os.remove(temp_audio)
                return False

            # Use Windows media command or simple playsound/sounddevice
            import winsound
            # Convert or play
            try:
                # If mp3, can use os.system or winsound if wav
                # Fallback to powershell media player
                import subprocess
                ps_cmd = f"(New-Object Media.SoundPlayer '{temp_audio}').PlaySync()"
                proc = subprocess.Popen(["powershell", "-c", ps_cmd])
                while proc.poll() is None:
                    if self._stop_event.is_set() or (interrupt_event and interrupt_event.is_set()):
                        proc.terminate()
                        break
                    time.sleep(0.1)
            finally:
                if os.path.exists(temp_audio):
                    try:
                        os.remove(temp_audio)
                    except Exception:
                        pass

            self._is_speaking = False
            return True

        except Exception as e:
            logger.error("edge-tts speech error: %s", e)
            self._is_speaking = False
            return False


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

    def speak(self, text: str, interrupt_event: threading.Event | None = None) -> bool:
        cleaned = clean_text_for_speech(text)
        if interrupt_event and interrupt_event.is_set():
            return False
        self.spoken_texts.append(cleaned)
        return True


def get_tts_engine(name: str = "pyttsx3", **kwargs: Any) -> BaseTTSEngine:
    """
    Factory function to retrieve or instantiate a TTS engine.
    """
    clean_name = name.lower().strip()
    if clean_name == "mock":
        return MockTTSEngine()
    elif clean_name == "edge_tts":
        engine = EdgeTTSEngine(**kwargs)
        if engine.is_available():
            return engine
        logger.warning("edge-tts unavailable, falling back to pyttsx3.")
        return Pyttsx3Engine()
    else:
        # Default pyttsx3
        return Pyttsx3Engine(**kwargs)
