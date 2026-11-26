"""Central circular voice state & real-amplitude waveform visualizer."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from desktop.services.ui_state import VOICE_STATE_CAPTIONS, VoiceState
from desktop.theme import COLORS


class _OrbCanvas(QWidget):
    """Minimal circular cyan ring with centered equalizer bars driven by real audio level."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(164, 164)
        self._state = VoiceState.IDLE
        self._audio_level = 0.0
        self._smoothed_level = 0.0
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: VoiceState) -> None:
        self._state = state
        if state in (
            VoiceState.LISTENING,
            VoiceState.WAKE_DETECTED,
            VoiceState.TRANSCRIBING,
            VoiceState.THINKING,
            VoiceState.EXECUTING_TOOL,
            VoiceState.SPEAKING,
        ):
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._audio_level = 0.0
            self._smoothed_level = 0.0
            self._timer.stop()
        self.update()

    def set_audio_level(self, level: float) -> None:
        # Clamp actual normalized RMS amplitude; never invent activity when idle/off
        self._audio_level = max(0.0, min(1.0, float(level)))
        if self._audio_level > 0.01 and not self._timer.isActive():
            self._timer.start()
        self.update()

    def _tick(self) -> None:
        self._phase += 0.22
        # Smooth decay toward latest real amplitude
        self._smoothed_level = (self._smoothed_level * 0.6) + (self._audio_level * 0.4)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        ring_colors = {
            VoiceState.IDLE: QColor(COLORS["accent_cyan"]),
            VoiceState.LISTENING: QColor(COLORS["accent_cyan"]),
            VoiceState.WAKE_DETECTED: QColor(COLORS["success"]),
            VoiceState.TRANSCRIBING: QColor(COLORS["accent_blue"]),
            VoiceState.THINKING: QColor(COLORS["accent_blue"]),
            VoiceState.EXECUTING_TOOL: QColor(COLORS["warning"]),
            VoiceState.SPEAKING: QColor(COLORS["success"]),
            VoiceState.ERROR: QColor(COLORS["error"]),
        }
        ring_col = ring_colors.get(self._state, QColor(COLORS["accent_cyan"]))

        # Subtle outer halo when active
        if self._state != VoiceState.IDLE:
            halo_col = QColor(ring_col)
            halo_col.setAlpha(int(35 + 45 * self._smoothed_level))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(halo_col, 7.0))
            m_halo = 10.0 - (3.0 * self._smoothed_level)
            painter.drawEllipse(QRectF(m_halo, m_halo, w - 2 * m_halo, h - 2 * m_halo))

        # Main outer cyan/status ring + dark center
        margin = 16.0
        painter.setBrush(QColor(COLORS["bg_main"]))
        painter.setPen(QPen(ring_col, 2.6))
        painter.drawEllipse(QRectF(margin, margin, w - 2 * margin, h - 2 * margin))

        # Inner thin accent circle
        inner_m = 26.0
        inner_col = QColor(ring_col)
        inner_col.setAlpha(90)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(inner_col, 1.0))
        painter.drawEllipse(QRectF(inner_m, inner_m, w - 2 * inner_m, h - 2 * inner_m))

        # 7 waveform bars inside the dark core
        num_bars = 7
        spacing = 10.0
        bar_pen = QPen(ring_col, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(bar_pen)

        for idx in range(num_bars):
            x = cx + (idx - (num_bars - 1) / 2.0) * spacing
            dist_factor = 1.0 - abs(idx - 3) * 0.18
            if self._state == VoiceState.IDLE:
                # Flat/resting minimal bar line when idle (no fake mic animation)
                amp = 4.0 + (18.0 * self._smoothed_level * dist_factor)
            elif self._state == VoiceState.LISTENING:
                # Directly tracks real microphone RMS amplitude
                amp = 6.0 + (44.0 * self._smoothed_level * dist_factor)
            elif self._state in (VoiceState.SPEAKING, VoiceState.THINKING, VoiceState.TRANSCRIBING, VoiceState.EXECUTING_TOOL):
                wave_val = 0.5 + 0.5 * math.sin(self._phase + idx * 0.85)
                amp = 10.0 + (26.0 * wave_val * dist_factor)
            elif self._state == VoiceState.WAKE_DETECTED:
                amp = 28.0 * dist_factor
            else:
                amp = 8.0

            half_h = amp / 2.0
            painter.drawLine(QPointF(x, cy - half_h), QPointF(x, cy + half_h))

        painter.end()


class VoiceVisualizerWidget(QWidget):
    """Circular voice indicator + live VoiceState caption widget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._orb = _OrbCanvas()
        layout.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._state_badge = QLabel("IDLE")
        self._state_badge.setObjectName("Badge")
        self._state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._state_badge, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._caption_lbl = QLabel(VOICE_STATE_CAPTIONS[VoiceState.IDLE])
        self._caption_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; letter-spacing: 1px; color: {COLORS['accent_cyan']};"
        )
        layout.addWidget(self._caption_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

    def set_voice_state(self, state: VoiceState) -> None:
        self._orb.set_state(state)
        self._state_badge.setText(state.value)
        self._caption_lbl.setText(VOICE_STATE_CAPTIONS.get(state, state.value))

        cap_col = COLORS["error"] if state == VoiceState.ERROR else COLORS["accent_cyan"]
        self._caption_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; letter-spacing: 1px; color: {cap_col};"
        )

    def set_audio_level(self, level: float) -> None:
        self._orb.set_audio_level(level)

    def current_caption(self) -> str:
        return self._caption_lbl.text()
