"""
Centralized application settings for JARVIS AI — Local Mode.

Loads configuration from environment variables and the .env file.
Provides validated, typed settings for all JARVIS components.

AI Provider: Ollama (local only)
STT: Faster-Whisper (local only)
TTS: Piper (local only)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is one level up from config/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# Permitted loopback addresses for LOCAL_AI_ONLY mode
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self) -> None:
        # ---- Paths ----
        self.PROJECT_ROOT: Path = _PROJECT_ROOT
        self.WORKSPACE_DIR: Path = _PROJECT_ROOT / "workspace"
        self.DATA_DIR: Path = _PROJECT_ROOT / "data"
        self.LOG_DIR: Path = _PROJECT_ROOT / "logs"
        self.DB_PATH: Path = self.DATA_DIR / "jarvis.db"

        # ---- AI Provider (single authoritative setting) ----
        # AI_PROVIDER selects the active provider.
        # Supported values: "ollama"
        self.AI_PROVIDER: str = os.getenv("AI_PROVIDER", "ollama").lower().strip()

        # LOCAL_AI_ONLY enforces that no cloud AI, STT or TTS endpoint is used.
        self.LOCAL_AI_ONLY: bool = os.getenv("LOCAL_AI_ONLY", "true").lower() in ("true", "1", "yes")

        # ---- Ollama Configuration ----
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
        self.OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))
        self.OLLAMA_MAX_TOOL_CALLS: int = int(os.getenv("OLLAMA_MAX_TOOL_CALLS", "5"))

        # ---- Application Limits ----
        self.MAX_CONVERSATION_HISTORY: int = int(
            os.getenv("MAX_CONVERSATION_HISTORY", "20")
        )
        self.MAX_TOOL_CALLS_PER_TASK: int = int(
            os.getenv("MAX_TOOL_CALLS_PER_TASK", "10")
        )

        # ---- Logging ----
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

        # ---- Voice — STT (Speech-to-Text) ----
        self.VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "true").lower() in ("true", "1", "yes")
        self.VOICE_INPUT_ENABLED: bool = (
            self.VOICE_ENABLED
            and os.getenv("VOICE_INPUT_ENABLED", "true").lower() in ("true", "1", "yes")
        )
        self.STT_ENGINE: str = os.getenv("VOICE_STT_PROVIDER", os.getenv("STT_ENGINE", "faster_whisper"))
        self.WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL", os.getenv("WHISPER_MODEL_SIZE", "base"))
        self.WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
        self.WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        self.WHISPER_LANGUAGE: str = os.getenv("WHISPER_LANGUAGE", "auto")
        self.STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "en-US")
        self.VOICE_SAMPLE_RATE: int = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))
        self.VOICE_CHANNELS: int = int(os.getenv("VOICE_CHANNELS", "1"))
        self.VOICE_SILENCE_TIMEOUT_SECONDS: float = float(
            os.getenv("VOICE_SILENCE_TIMEOUT_SECONDS", os.getenv("SILENCE_TIMEOUT", "1.0"))
        )
        self.SILENCE_TIMEOUT: float = self.VOICE_SILENCE_TIMEOUT_SECONDS
        self.VOICE_MAX_UTTERANCE_SECONDS: float = float(
            os.getenv("VOICE_MAX_UTTERANCE_SECONDS", "20")
        )
        self.VOICE_MIN_SPEECH_SECONDS: float = float(
            os.getenv("VOICE_MIN_SPEECH_SECONDS", "0.3")
        )
        self.ENERGY_THRESHOLD: int = int(os.getenv("ENERGY_THRESHOLD", "300"))
        raw_mic_idx = os.getenv("VOICE_MICROPHONE_INDEX", "").strip()
        self.VOICE_MICROPHONE_INDEX: int | None = int(raw_mic_idx) if raw_mic_idx else None

        # Local STT model storage directory and verified local model path
        self.WHISPER_MODEL_DIR: Path = _PROJECT_ROOT / "models" / "stt"
        raw_whisper_path = os.getenv("WHISPER_MODEL_PATH", "").strip()
        if raw_whisper_path:
            candidate = Path(raw_whisper_path)
            self.WHISPER_MODEL_PATH: Path = (
                candidate if candidate.is_absolute() else (_PROJECT_ROOT / candidate)
            )
        else:
            self.WHISPER_MODEL_PATH = (
                self.WHISPER_MODEL_DIR / f"faster-whisper-{self.WHISPER_MODEL_SIZE}"
            )

        # ---- Wake Word & Hands-Free Conversation ----
        self.WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "true").lower() in ("true", "1", "yes")
        self.WAKE_WORD_PHRASE: str = os.getenv("WAKE_WORD_PHRASE", "hey jarvis").strip()
        self.WAKE_WORD_ENGINE: str = os.getenv("WAKE_WORD_ENGINE", "openwakeword").lower().strip()
        self.WAKE_WORD_THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))
        raw_ww_dir = os.getenv("WAKE_WORD_MODEL_DIR", "models/wakeword").strip()
        ww_candidate = Path(raw_ww_dir)
        self.WAKE_WORD_MODEL_DIR: Path = (
            ww_candidate if ww_candidate.is_absolute() else (_PROJECT_ROOT / ww_candidate)
        )
        self.CONVERSATION_TIMEOUT_SECONDS: float = float(
            os.getenv("CONVERSATION_TIMEOUT_SECONDS", "25")
        )

        # ---- Voice — TTS (Text-to-Speech) ----
        self.TTS_ENGINE: str = os.getenv("VOICE_TTS_PROVIDER", os.getenv("TTS_ENGINE", "piper"))
        self.TTS_RATE: int = int(os.getenv("TTS_RATE", "175"))
        self.TTS_VOLUME: float = float(os.getenv("TTS_VOLUME", "1.0"))
        self.TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.0"))
        self.TTS_VOICE: str = os.getenv("TTS_VOICE", "")
        self.VOICE_MODE: str = os.getenv("VOICE_MODE", "hands_free")
        self.VOICE_OUTPUT_ENABLED: bool = os.getenv("VOICE_OUTPUT_ENABLED", "true").lower() in ("true", "1", "yes")

        # Piper TTS configuration
        self.PIPER_MODEL_PATH: Path = _PROJECT_ROOT / os.getenv("PIPER_MODEL_PATH", "models/tts")
        self.PIPER_VOICE: str = os.getenv("PIPER_VOICE", "en_GB-alan-medium")

        # Ensure required directories exist
        self._create_directories()

    def _create_directories(self) -> None:
        """Create required application directories if they don't exist."""
        for directory in [self.WORKSPACE_DIR, self.DATA_DIR, self.LOG_DIR,
                          self.WHISPER_MODEL_DIR, self.PIPER_MODEL_PATH,
                          self.WAKE_WORD_MODEL_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    def _get_ollama_host(self) -> str:
        """Extract the hostname from OLLAMA_BASE_URL."""
        url = self.OLLAMA_BASE_URL.lower()
        # Strip scheme
        for scheme in ("http://", "https://"):
            if url.startswith(scheme):
                url = url[len(scheme):]
        # Strip path and port
        host = url.split("/")[0].split(":")[0]
        return host

    def validate(self) -> list[str]:
        """
        Validate critical settings.
        Returns a list of error messages (empty if everything is valid).
        """
        errors: list[str] = []

        # Provider selection
        if self.AI_PROVIDER != "ollama":
            errors.append(
                f"AI_PROVIDER='{self.AI_PROVIDER}' is not supported. "
                "JARVIS currently supports only 'ollama'. Set AI_PROVIDER=ollama in .env."
            )

        # LOCAL_AI_ONLY: enforce loopback endpoint
        if self.LOCAL_AI_ONLY:
            host = self._get_ollama_host()
            if host not in _LOCAL_HOSTS:
                errors.append(
                    f"LOCAL_AI_ONLY=true but OLLAMA_BASE_URL points to a non-local host "
                    f"('{host}'). Only loopback addresses are permitted (127.0.0.1, localhost)."
                )

        # Ollama model must be set
        if not self.OLLAMA_MODEL:
            errors.append("OLLAMA_MODEL is not set. Example: OLLAMA_MODEL=qwen3.5:4b")

        # Application limits
        if self.MAX_CONVERSATION_HISTORY < 1:
            errors.append("MAX_CONVERSATION_HISTORY must be at least 1.")
        if self.MAX_TOOL_CALLS_PER_TASK < 1:
            errors.append("MAX_TOOL_CALLS_PER_TASK must be at least 1.")
        if self.OLLAMA_TIMEOUT < 10:
            errors.append("OLLAMA_TIMEOUT must be at least 10 seconds.")

        # Wake-word & hands-free settings
        if self.LOCAL_AI_ONLY and self.WAKE_WORD_ENGINE != "openwakeword":
            errors.append(
                f"WAKE_WORD_ENGINE='{self.WAKE_WORD_ENGINE}' is not permitted in LOCAL_AI_ONLY mode. "
                "Only 'openwakeword' is supported."
            )
        if not (0.0 < self.WAKE_WORD_THRESHOLD <= 1.0):
            errors.append("WAKE_WORD_THRESHOLD must be between 0.0 (exclusive) and 1.0 (inclusive).")
        if self.VOICE_SILENCE_TIMEOUT_SECONDS <= 0:
            errors.append("VOICE_SILENCE_TIMEOUT_SECONDS must be positive.")
        if self.VOICE_MAX_UTTERANCE_SECONDS < 1:
            errors.append("VOICE_MAX_UTTERANCE_SECONDS must be at least 1 second.")
        if self.CONVERSATION_TIMEOUT_SECONDS < 1:
            errors.append("CONVERSATION_TIMEOUT_SECONDS must be at least 1 second.")

        return errors


# Singleton instance used throughout the application
settings = Settings()
