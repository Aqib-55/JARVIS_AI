"""Left navigation sidebar component."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop import APP_SUBTITLE, APP_VERSION
from desktop.resources.icons.icon_factory import create_jarvis_pixmap
from desktop.services.ui_state import HealthSnapshot
from desktop.theme import COLORS


class SidebarWidget(QFrame):
    """Persistent left navigation sidebar with branding, nav items, and footer status."""

    page_selected = Signal(str)

    _NAV_ITEMS = (
        ("overview", "Overview"),
        ("chat", "Chat"),
        ("tools", "Tools"),
        ("memory", "Memory"),
        ("settings", "Settings"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(240)

        self._buttons: dict[str, QPushButton] = {}
        self._build_ui()
        self.set_active_page("chat")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(10)

        # Brand Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(create_jarvis_pixmap(40))
        logo_lbl.setFixedSize(40, 40)
        brand_row.addWidget(logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("JARVIS")
        title_lbl.setObjectName("SidebarBrandTitle")
        sub_lbl = QLabel(APP_SUBTITLE)
        sub_lbl.setObjectName("SidebarBrandSubtitle")
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        brand_row.addLayout(title_col)
        layout.addLayout(brand_row)

        # Local status pill
        self._local_pill = QLabel("● Checking Local Runtime…")
        self._local_pill.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 11px; padding: 6px 4px 10px 4px;"
        )
        layout.addWidget(self._local_pill)

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLORS['border']}; background-color: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(sep)
        layout.addSpacing(4)

        # Navigation buttons
        for key, label in self._NAV_ITEMS:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self.page_selected.emit(k))
            layout.addWidget(btn)
            self._buttons[key] = btn

        layout.addStretch(1)

        # Footer System Summary Card
        footer = QFrame()
        footer.setObjectName("SecondaryCard")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(12, 12, 12, 12)
        fl.setSpacing(6)

        self._model_lbl = QLabel("Model: —")
        self._model_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLORS['text_primary']};")
        self._ai_mode_lbl = QLabel("Local AI: —")
        self._ai_mode_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        self._voice_lbl = QLabel("Voice: —")
        self._voice_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        ver_lbl = QLabel(f"Desktop v{APP_VERSION}")
        ver_lbl.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; margin-top: 2px;")

        fl.addWidget(self._model_lbl)
        fl.addWidget(self._ai_mode_lbl)
        fl.addWidget(self._voice_lbl)
        fl.addWidget(ver_lbl)
        layout.addWidget(footer)

    def set_active_page(self, page_key: str) -> None:
        for key, btn in self._buttons.items():
            is_active = key == page_key
            btn.setProperty("active", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def update_health(self, snap: HealthSnapshot) -> None:
        if snap.ai_connected:
            self._local_pill.setText("● Local AI Connected")
            self._local_pill.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px; padding: 6px 4px 10px 4px;")
        else:
            self._local_pill.setText("● Ollama Disconnected")
            self._local_pill.setStyleSheet(f"color: {COLORS['error']}; font-size: 11px; padding: 6px 4px 10px 4px;")

        self._model_lbl.setText(f"Model: {snap.ai_model}")
        self._ai_mode_lbl.setText(
            f"Local Only: {'Enabled' if snap.local_ai_only else 'Disabled'}"
        )
        if snap.wake_detection_active:
            self._voice_lbl.setText("Voice: Hands-Free Ready")
            self._voice_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['accent_cyan']};")
        elif snap.stt_available:
            self._voice_lbl.setText("Voice: Push-to-Talk Ready")
            self._voice_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        else:
            self._voice_lbl.setText("Voice: Text / Unavailable")
            self._voice_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['warning']};")
