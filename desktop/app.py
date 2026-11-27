"""PySide6 application lifecycle, single-instance guard, and theme bootstrapping."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import settings
from desktop import APP_NAME, APP_VERSION
from desktop.main_window import JarvisMainWindow
from desktop.resources.icons.icon_factory import create_jarvis_icon
from desktop.services.backend_adapter import BackendAdapter
from desktop.theme import build_stylesheet

_INSTANCE_KEY = "jarvis_ai_desktop_single_instance_v2"


def setup_desktop_logging() -> None:
    log_file = settings.LOG_DIR / "jarvis_desktop.log"
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _acquire_single_instance() -> QLocalServer | None:
    """Prevent duplicate desktop instances using a local socket lock."""
    probe = QLocalSocket()
    probe.connectToServer(_INSTANCE_KEY)
    if probe.waitForConnected(250):
        probe.disconnectFromServer()
        return None

    QLocalServer.removeServer(_INSTANCE_KEY)
    server = QLocalServer()
    if not server.listen(_INSTANCE_KEY):
        return None
    return server


def run_desktop_app(argv: list[str] | None = None) -> int:
    setup_desktop_logging()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    bundled_ico = settings.RESOURCE_ROOT / "desktop" / "resources" / "icons" / "jarvis.ico"
    if not bundled_ico.exists():
        bundled_ico = Path(__file__).resolve().parent / "resources" / "icons" / "jarvis.ico"
    if bundled_ico.exists():
        app.setWindowIcon(QIcon(str(bundled_ico)))
    else:
        app.setWindowIcon(create_jarvis_icon())
    app.setStyleSheet(build_stylesheet())

    instance_server = _acquire_single_instance()
    if instance_server is None:
        QMessageBox.information(
            None,
            APP_NAME,
            "JARVIS AI Desktop is already running.",
        )
        return 0

    backend = BackendAdapter()
    window = JarvisMainWindow(backend=backend, auto_start_backend=True, auto_start_voice=True)
    app.aboutToQuit.connect(backend.shutdown)
    window.show()

    exit_code = app.exec()
    instance_server.close()
    return exit_code
