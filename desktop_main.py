r"""
JARVIS AI — Native Windows Desktop Application Entry Point (PySide6 / Qt 6).

Run:
    .\.venv\Scripts\python.exe desktop_main.py

Verify packaged bundle without Ollama/audio hardware:
    .\.venv\Scripts\python.exe desktop_main.py --packaging-smoke-test

Existing CLI entry point remains preserved:
    .\.venv\Scripts\python.exe main.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def run_packaging_smoke_test() -> int:
    """
    Verify compiled Qt GUI, backend imports, and writable persistent app-data paths
    under QT_QPA_PLATFORM=offscreen without starting Ollama, models, or microphone.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QWidget

        app = QApplication.instance() or QApplication(["jarvis_smoke"])
        probe_widget = QWidget()
        _ = probe_widget.sizeHint()

        # Import desktop UI, icons & adapter
        from config.settings import settings
        from desktop.main_window import JarvisMainWindow
        from desktop.resources.icons.icon_factory import create_jarvis_icon
        from desktop.services.backend_adapter import BackendAdapter

        # Import existing agent, provider, memory, and voice subsystems
        from core.agent import JarvisAgent
        from memory.database import DatabaseManager
        from memory.memory_manager import MemoryManager
        from providers.factory import get_provider
        from providers.ollama import OllamaProvider
        from voice.conversation_manager import HandsFreeConversationManager
        from voice.speech_to_text import FasterWhisperEngine
        from voice.text_to_speech import PiperEngine
        from voice.voice_controller import VoiceController

        # Confirm key symbols are bound cleanly (never optimized away)
        _ = (
            Qt,
            JarvisMainWindow,
            BackendAdapter,
            JarvisAgent,
            DatabaseManager,
            MemoryManager,
            get_provider,
            OllamaProvider,
            HandsFreeConversationManager,
            FasterWhisperEngine,
            PiperEngine,
            VoiceController,
        )

        icon = create_jarvis_icon()
        if icon.isNull():
            raise RuntimeError("create_jarvis_icon() returned null QIcon")

        # Verify persistent app data root and write capability without disturbing user data
        for required_dir in (
            settings.APP_DATA_DIR,
            settings.DATA_DIR,
            settings.LOG_DIR,
            settings.WORKSPACE_DIR,
            settings.WHISPER_MODEL_DIR,
            settings.PIPER_MODEL_PATH,
            settings.WAKE_WORD_MODEL_DIR,
        ):
            required_dir.mkdir(parents=True, exist_ok=True)

        probe_file = settings.DATA_DIR / ".packaging_smoke_probe"
        probe_file.write_text("ok", encoding="utf-8")
        if probe_file.read_text(encoding="utf-8") != "ok":
            raise RuntimeError(f"Writable data verification failed at {probe_file}")
        probe_file.unlink(missing_ok=True)

        probe_widget.deleteLater()
        app.processEvents()

        print(
            "PASS: Packaging smoke test succeeded | "
            f"packaged={settings.IS_PACKAGED} | "
            f"app_data_dir={settings.APP_DATA_DIR} | "
            f"resource_root={settings.RESOURCE_ROOT}"
        )
        return 0
    except Exception as exc:
        print(f"FAIL: Packaging smoke test failed: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS AI Desktop Application")
    parser.add_argument(
        "--packaging-smoke-test",
        action="store_true",
        help="Verify Qt runtime, packaged imports, and persistent data directory cleanly.",
    )
    args, remaining = parser.parse_known_args(argv)

    if args.packaging_smoke_test:
        return run_packaging_smoke_test()

    from desktop.app import run_desktop_app

    return run_desktop_app([sys.argv[0], *remaining])


if __name__ == "__main__":
    sys.exit(main())
