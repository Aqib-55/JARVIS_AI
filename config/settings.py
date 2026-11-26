"""
Centralized application settings for JARVIS AI — Local Mode.

Loads configuration from environment variables and the .env file.
Provides validated, typed settings for all JARVIS components.

AI Provider: Ollama (local only)
STT: Faster-Whisper (local only)
TTS: Piper (local only)
"""

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

# Source project root (development mode)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Permitted loopback addresses for LOCAL_AI_ONLY mode
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_packaged_app() -> bool:
    """Return True when running from a compiled bundle (e.g., Nuitka / PyInstaller)."""
    if getattr(sys, "frozen", False):
        return True
    if "__compiled__" in globals():
        return True
    main_mod = sys.modules.get("__main__")
    if main_mod is not None and hasattr(main_mod, "__compiled__"):
        return True
    return False


def resolve_runtime_roots() -> tuple[Path, Path, bool]:
    """
    Resolve persistent writable app data root vs. static resource root.

    Returns:
        (app_data_root, resource_root, isolated_mode)
    """
    packaged = is_packaged_app()
    jarvis_home = os.getenv("JARVIS_HOME", "").strip()

    if packaged:
        resource_root = Path(sys.executable).resolve().parent
    else:
        resource_root = _PROJECT_ROOT

    if jarvis_home:
        app_data_root = Path(jarvis_home).expanduser().resolve()
    elif packaged:
        if os.name == "nt" or sys.platform == "win32":
            local_app_data = Path(
                os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
            )
            app_data_root = local_app_data / "JARVIS_AI"
        else:
            app_data_root = Path.home() / ".local" / "share" / "JARVIS_AI"
    else:
        app_data_root = _PROJECT_ROOT

    return app_data_root, resource_root, (packaged or bool(jarvis_home))


def _ensure_first_run_template(
    app_data_root: Path,
    resource_root: Path,
    create_env_from_template: bool,
) -> Path:
    """Ensure persistent runtime directories exist and optionally seed missing .env."""
    env_file = app_data_root / ".env"
    if create_env_from_template:
        app_data_root.mkdir(parents=True, exist_ok=True)
        for sub in (
            "data",
            "logs",
            "workspace",
            "recordings",
            "models/stt",
            "models/tts",
            "models/wakeword",
        ):
            (app_data_root / sub).mkdir(parents=True, exist_ok=True)
        if not env_file.exists():
            for candidate_root in (resource_root, _PROJECT_ROOT):
                template = candidate_root / ".env.example"
                if template.is_file():
                    shutil.copy2(template, env_file)
                    break
    return env_file


def _resolve_relative_path(raw: str, base_dir: Path, default_rel: str) -> Path:
    val = raw.strip() if raw else ""
    target = Path(val) if val else Path(default_rel)
    return target if target.is_absolute() else (base_dir / target)


# Perform initial environment load before importing/initializing settings singleton
_INIT_APP_ROOT, _INIT_RES_ROOT, _INIT_ISOLATED = resolve_runtime_roots()
_INIT_ENV_FILE = _ensure_first_run_template(_INIT_APP_ROOT, _INIT_RES_ROOT, _INIT_ISOLATED)
load_dotenv(_INIT_ENV_FILE, override=False)


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self) -> None:
        app_data_root, resource_root, isolated = resolve_runtime_roots()
        env_file = _ensure_first_run_template(app_data_root, resource_root, isolated)
        if env_file != _INIT_ENV_FILE:
            load_dotenv(env_file, override=False)

        # ---- Paths ----
        self.IS_PACKAGED: bool = is_packaged_app()
        self.RESOURCE_ROOT: Path = resource_root
        self.APP_DATA_DIR: Path = app_data_root
        self.PROJECT_ROOT: Path = resource_root
        self.ENV_FILE: Path = env_file
        self.WORKSPACE_DIR: Path = app_data_root / "workspace"
        self.DATA_DIR: Path = app_data_root / "data"
        self.LOG_DIR: Path = app_data_root / "logs"
        self.RECORDINGS_DIR: Path = app_data_root / "recordings"
        self.MODELS_DIR: Path = app_data_root / "models"
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
        self.OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "180"))
        self.OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
        self.OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        self.OLLAMA_STREAM: bool = os.getenv("OLLAMA_STREAM", "true").lower() in ("true", "1", "yes")
        self.OLLAMA_MAX_TOOL_CALLS: int = int(os.getenv("OLLAMA_MAX_TOOL_CALLS", "5"))

        # ---- Application Limits ----
        self.MAX_CONVERSATION_HISTORY: int = int(
            os.getenv("MAX_CONVERSATION_HISTORY", "12")
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
        raw_mic_idx = os.getenv("VOICE_MICROPHONE_INDEX", "").strip()
        self.VOICE_MICROPHONE_INDEX: int | None = int(raw_mic_idx) if raw_mic_idx else None

        # Local STT model storage directory and verified local model path
        self.WHISPER_MODEL_DIR: Path = self.MODELS_DIR / "stt"
        raw_whisper_path = os.getenv("WHISPER_MODEL_PATH", "").strip()
        if raw_whisper_path:
            self.WHISPER_MODEL_PATH: Path = _resolve_relative_path(
                raw_whisper_path, app_data_root, f"models/stt/faster-whisper-{self.WHISPER_MODEL_SIZE}"
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
        self.WAKE_WORD_MODEL_DIR: Path = _resolve_relative_path(
            os.getenv("WAKE_WORD_MODEL_DIR", "models/wakeword"),
            app_data_root,
            "models/wakeword",
        )
        self.CONVERSATION_TIMEOUT_SECONDS: float = float(
            os.getenv("CONVERSATION_TIMEOUT_SECONDS", "25")
        )

        # ---- Voice — TTS (Text-to-Speech) ----
        self.TTS_ENGINE: str = os.getenv("VOICE_TTS_PROVIDER", os.getenv("TTS_ENGINE", "piper"))
        self.TTS_VOLUME: float = float(os.getenv("TTS_VOLUME", "1.0"))
        self.TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.0"))
        self.VOICE_MODE: str = os.getenv("VOICE_MODE", "hands_free")
        self.VOICE_OUTPUT_ENABLED: bool = os.getenv("VOICE_OUTPUT_ENABLED", "true").lower() in ("true", "1", "yes")

        # Piper TTS configuration
        self.PIPER_MODEL_PATH: Path = _resolve_relative_path(
            os.getenv("PIPER_MODEL_PATH", "models/tts"),
            app_data_root,
            "models/tts",
        )
        self.PIPER_VOICE: str = os.getenv("PIPER_VOICE", "en_GB-alan-medium")

        # Ensure required directories exist
        self._create_directories()

    def _create_directories(self) -> None:
        """Create required writable application directories if they don't exist."""
        for directory in [
            self.WORKSPACE_DIR,
            self.DATA_DIR,
            self.LOG_DIR,
            self.RECORDINGS_DIR,
            self.WHISPER_MODEL_DIR,
            self.PIPER_MODEL_PATH,
            self.WAKE_WORD_MODEL_DIR,
        ]:
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
