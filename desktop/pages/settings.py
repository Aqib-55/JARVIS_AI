"""Settings page displaying honest AI, Voice, and Application runtime state."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop import APP_VERSION
from desktop.services.ui_state import HealthSnapshot
from desktop.theme import COLORS


class SettingsPage(QWidget):
    """Displays real AI & Voice configuration and applies safe runtime-only adjustments."""

    apply_settings_requested = Signal(float, float, object, bool)  # threshold, timeout, mic_idx, voice_out
    diagnostics_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)

        # 1. AI Settings (Read-only honest state; never exposes credentials or external hosts)
        ai_card = QFrame()
        ai_card.setObjectName("Card")
        ail = QVBoxLayout(ai_card)
        ail.setContentsMargins(18, 16, 18, 16)
        ail.setSpacing(10)
        ai_hdr = QLabel("AI ENGINE CONFIGURATION")
        ai_hdr.setStyleSheet(f"font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {COLORS['accent_cyan']};")
        ail.addWidget(ai_hdr)

        ai_form = QFormLayout()
        ai_form.setSpacing(8)
        self._provider_lbl = QLabel("Ollama")
        self._model_lbl = QLabel("qwen3.5:4b")
        self._local_lbl = QLabel("Enabled (Loopback Only)")
        self._conn_lbl = QLabel("Checking…")
        ai_form.addRow("Provider:", self._provider_lbl)
        ai_form.addRow("Model:", self._model_lbl)
        ai_form.addRow("Local-Only Mode:", self._local_lbl)
        ai_form.addRow("Ollama Status:", self._conn_lbl)
        ail.addLayout(ai_form)
        layout.addWidget(ai_card)

        # 2. Voice Settings
        voice_card = QFrame()
        voice_card.setObjectName("Card")
        vl = QVBoxLayout(voice_card)
        vl.setContentsMargins(18, 16, 18, 16)
        vl.setSpacing(10)
        v_hdr = QLabel("VOICE & WAKE-WORD SETTINGS")
        v_hdr.setStyleSheet(f"font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {COLORS['accent_cyan']};")
        vl.addWidget(v_hdr)

        v_form = QFormLayout()
        v_form.setSpacing(8)
        self._stt_lbl = QLabel("Faster-Whisper")
        self._whisper_lbl = QLabel("base (CPU INT8)")
        self._tts_lbl = QLabel("Piper TTS")
        self._piper_lbl = QLabel("en_GB-alan-medium")
        self._wake_lbl = QLabel("Standby")

        self._thresh_spin = QDoubleSpinBox()
        self._thresh_spin.setRange(0.10, 0.95)
        self._thresh_spin.setSingleStep(0.05)
        self._thresh_spin.setValue(0.50)

        self._timeout_spin = QDoubleSpinBox()
        self._timeout_spin.setRange(5.0, 120.0)
        self._timeout_spin.setSingleStep(5.0)
        self._timeout_spin.setSuffix(" s")
        self._timeout_spin.setValue(25.0)

        self._mic_combo = QComboBox()
        self._mic_combo.addItem("System Default Input", None)

        self._voice_out_chk = QCheckBox("Enable Piper spoken responses")
        self._voice_out_chk.setChecked(True)

        v_form.addRow("STT Engine:", self._stt_lbl)
        v_form.addRow("Whisper Model:", self._whisper_lbl)
        v_form.addRow("TTS Engine:", self._tts_lbl)
        v_form.addRow("Piper Voice:", self._piper_lbl)
        v_form.addRow("Wake-Word State:", self._wake_lbl)
        v_form.addRow("Wake Threshold:", self._thresh_spin)
        v_form.addRow("Conversation Timeout:", self._timeout_spin)
        v_form.addRow("Microphone Device:", self._mic_combo)
        v_form.addRow("Voice Output:", self._voice_out_chk)
        vl.addLayout(v_form)

        apply_row = QHBoxLayout()
        self._apply_lbl = QLabel("Changes apply to the running session (.env is never overwritten automatically).")
        self._apply_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        apply_btn = QPushButton("Apply Voice Settings")
        apply_btn.setObjectName("PrimaryButton")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(self._on_apply)
        apply_row.addWidget(self._apply_lbl)
        apply_row.addStretch(1)
        apply_row.addWidget(apply_btn)
        vl.addLayout(apply_row)
        layout.addWidget(voice_card)

        # 3. Application Settings
        app_card = QFrame()
        app_card.setObjectName("Card")
        apl = QVBoxLayout(app_card)
        apl.setContentsMargins(18, 16, 18, 16)
        apl.setSpacing(10)
        a_hdr = QLabel("APPLICATION & DIAGNOSTICS")
        a_hdr.setStyleSheet(f"font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {COLORS['accent_cyan']};")
        apl.addWidget(a_hdr)

        a_form = QFormLayout()
        a_form.addRow("Theme:", QLabel("Dark Futuristic (#090D14 / Cyan #42CBEF)"))
        a_form.addRow("Window Close Behavior:", QLabel("Stops microphone, active audio & backend workers cleanly"))
        a_form.addRow("Application Version:", QLabel(f"JARVIS AI Desktop v{APP_VERSION} (PySide6 / Qt 6)"))
        apl.addLayout(a_form)

        diag_row = QHBoxLayout()
        self._diag_status_lbl = QLabel("")
        self._diag_status_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        diag_btn = QPushButton("Run Diagnostics")
        diag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        diag_btn.clicked.connect(self._on_diag)
        diag_row.addWidget(self._diag_status_lbl, stretch=1)
        diag_row.addWidget(diag_btn)
        apl.addLayout(diag_row)
        layout.addWidget(app_card)
        layout.addStretch(1)

    def populate_microphones(self, devices: list[dict[str, Any]], current_idx: int | None = None) -> None:
        self._mic_combo.blockSignals(True)
        self._mic_combo.clear()
        self._mic_combo.addItem("System Default Input", None)
        sel = 0
        for d in devices:
            idx = d.get("index")
            name = d.get("name", f"Device {idx}")
            self._mic_combo.addItem(f"[{idx}] {name}", idx)
            if current_idx is not None and idx == current_idx:
                sel = self._mic_combo.count() - 1
        self._mic_combo.setCurrentIndex(sel)
        self._mic_combo.blockSignals(False)

    def update_health(self, snap: HealthSnapshot, wake_threshold: float, voice_out: bool) -> None:
        self._provider_lbl.setText(snap.ai_provider.title())
        self._model_lbl.setText(snap.ai_model)
        self._local_lbl.setText("Enabled (Loopback Only)" if snap.local_ai_only else "Disabled")
        self._conn_lbl.setText(f"Connected ({snap.ollama_url})" if snap.ai_connected else "Disconnected")

        self._stt_lbl.setText(f"{snap.stt_engine} ({'Ready' if snap.stt_available else 'Unavailable'})")
        self._whisper_lbl.setText(f"{snap.whisper_model} (CPU INT8)")
        self._tts_lbl.setText(f"{snap.tts_engine} ({'Ready' if snap.tts_available else 'Unavailable'})")
        self._piper_lbl.setText(snap.piper_voice)
        self._wake_lbl.setText(
            f"{snap.wake_word_phrase} — {'Active' if snap.wake_detection_active else 'Stopped'}"
        )
        self._thresh_spin.setValue(wake_threshold)
        self._timeout_spin.setValue(snap.conversation_timeout_seconds)
        self._voice_out_chk.setChecked(voice_out)

    def _on_apply(self) -> None:
        self._apply_lbl.setText("Runtime settings applied.")
        self.apply_settings_requested.emit(
            self._thresh_spin.value(),
            self._timeout_spin.value(),
            self._mic_combo.currentData(),
            self._voice_out_chk.isChecked(),
        )

    def _on_diag(self) -> None:
        self._diag_status_lbl.setText("Running diagnostics…")
        self.diagnostics_requested.emit()

    def show_diagnostics(self, data: dict[str, Any]) -> None:
        if "error" in data:
            self._diag_status_lbl.setText(f"Error: {data['error']}")
            return
        mic = data.get("microphone", {}).get("ok", False)
        ww = data.get("wake_word", {}).get("ok", False)
        stt = data.get("stt", {}).get("ok", False)
        tts = data.get("tts", {}).get("ok", False)
        self._diag_status_lbl.setText(
            f"Mic: {'OK' if mic else 'FAIL'}  •  Wake Word: {'OK' if ww else 'FAIL'}  •  "
            f"STT: {'OK' if stt else 'FAIL'}  •  TTS: {'OK' if tts else 'FAIL'}"
        )
