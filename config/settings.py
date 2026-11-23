"""
Centralized application settings.

Loads configuration from environment variables and the .env file.
Provides validated, typed settings for all JARVIS components.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is one level up from config/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self) -> None:
        # ---- Paths ----
        self.PROJECT_ROOT: Path = _PROJECT_ROOT
        self.WORKSPACE_DIR: Path = _PROJECT_ROOT / "workspace"
        self.DATA_DIR: Path = _PROJECT_ROOT / "data"
        self.LOG_DIR: Path = _PROJECT_ROOT / "logs"
        self.DB_PATH: Path = self.DATA_DIR / "jarvis.db"

        # ---- API Keys (never log these) ----
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

        # ---- Model Configuration ----
        self.GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.ACTIVE_PROVIDER: str = os.getenv("ACTIVE_PROVIDER", "gemini")
        # ---- Local AI Provider Settings ----
        self.AI_PROVIDER: str = os.getenv("AI_PROVIDER", "ollama")
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")

        # ---- Application Limits ----
        self.MAX_CONVERSATION_HISTORY: int = int(
            os.getenv("MAX_CONVERSATION_HISTORY", "20")
        )
        self.MAX_TOOL_CALLS_PER_TASK: int = int(
            os.getenv("MAX_TOOL_CALLS_PER_TASK", "10")
        )

        # ---- Logging ----
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

        # ---- Voice Configuration ----
        self.VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "true").lower() in ("true", "1", "yes")
        self.STT_ENGINE: str = os.getenv("STT_ENGINE", "speech_recognition")
        self.TTS_ENGINE: str = os.getenv("TTS_ENGINE", "pyttsx3")
        self.STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "en-US")
        self.TTS_LANGUAGE: str = os.getenv("TTS_LANGUAGE", "en")
        self.TTS_RATE: int = int(os.getenv("TTS_RATE", "175"))
        self.TTS_VOLUME: float = float(os.getenv("TTS_VOLUME", "0.9"))
        self.TTS_VOICE: str = os.getenv("TTS_VOICE", "")
        self.VOICE_MODE: str = os.getenv("VOICE_MODE", "push_to_talk")
        self.WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")
        self.SILENCE_TIMEOUT: float = float(os.getenv("SILENCE_TIMEOUT", "2.0"))
        self.ENERGY_THRESHOLD: int = int(os.getenv("ENERGY_THRESHOLD", "300"))

        # Ensure required directories exist
        self._create_directories()

    def _create_directories(self) -> None:
        """Create required application directories if they don't exist."""
        for directory in [self.WORKSPACE_DIR, self.DATA_DIR, self.LOG_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        """
        Validate critical settings.
        Returns a list of error messages (empty if everything is valid).
        """
        errors: list[str] = []
        if not self.GEMINI_API_KEY:
            errors.append(
                "GEMINI_API_KEY is not set. "
                "Please create a .env file in the project root and add: "
                "GEMINI_API_KEY=your_actual_api_key"
            )
        elif self.GEMINI_API_KEY == "your_gemini_api_key_here":
            errors.append(
                "GEMINI_API_KEY is still set to the placeholder value. "
                "Please replace 'your_gemini_api_key_here' in your .env file with your actual Gemini API key."
            )
        elif len(self.GEMINI_API_KEY) < 10:
            errors.append(
                "GEMINI_API_KEY appears too short or malformed. "
                "Please verify the key in your .env file."
            )

        if self.MAX_CONVERSATION_HISTORY < 1:
            errors.append("MAX_CONVERSATION_HISTORY must be at least 1.")
        if self.MAX_TOOL_CALLS_PER_TASK < 1:
            errors.append("MAX_TOOL_CALLS_PER_TASK must be at least 1.")
        return errors


# Singleton instance used throughout the application
settings = Settings()
