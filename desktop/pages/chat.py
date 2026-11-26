"""Primary Chat & Central Voice Experience page."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.components.chat_message import ChatMessageWidget
from desktop.components.message_input import MessageInputWidget
from desktop.components.voice_visualizer import VoiceVisualizerWidget
from desktop.services.ui_state import VOICE_STATE_CAPTIONS, HealthSnapshot, VoiceState
from desktop.theme import COLORS


class ChatPage(QWidget):
    """Conversational interface paired with the central circular voice visualizer."""

    send_message_requested = Signal(str)
    clear_chat_requested = Signal()
    ptt_requested = Signal()
    stop_voice_requested = Signal()
    enable_hands_free_requested = Signal()
    disable_hands_free_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._streaming_bubble: ChatMessageWidget | None = None
        self._pending_tool_bubbles: list[ChatMessageWidget] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        # Left/Center Column: Chat Header + Timeline + Composer
        chat_col = QVBoxLayout()
        chat_col.setSpacing(12)

        # Chat Sub-header
        hdr_card = QFrame()
        hdr_card.setObjectName("Card")
        hl = QHBoxLayout(hdr_card)
        hl.setContentsMargins(16, 10, 16, 10)
        hl.setSpacing(10)

        title = QLabel("JARVIS Conversation")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        hl.addWidget(title)

        self._model_pill = QLabel("Model: qwen3.5:4b")
        self._model_pill.setObjectName("Badge")
        self._local_pill = QLabel("Local AI Only")
        self._local_pill.setObjectName("Badge")
        hl.addWidget(self._model_pill)
        hl.addWidget(self._local_pill)
        hl.addStretch(1)

        clear_btn = QPushButton("Clear Conversation")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._on_clear_clicked)
        hl.addWidget(clear_btn)
        chat_col.addWidget(hdr_card)

        # Scrollable Message Timeline
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._msg_container = QWidget()
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(6, 6, 10, 6)
        self._msg_layout.setSpacing(8)
        self._msg_layout.addStretch(1)
        self._scroll.setWidget(self._msg_container)
        chat_col.addWidget(self._scroll, stretch=1)

        # Initial greeting message
        self.add_message(
            "assistant",
            'JARVIS Desktop initialized. Type a request below or say **"Hey JARVIS"** for hands-free voice.',
        )

        # Bottom Message Input Composer
        self._composer = MessageInputWidget()
        self._composer.send_requested.connect(self._on_send)
        self._composer.mic_requested.connect(self.ptt_requested.emit)
        self._composer.stop_requested.connect(self.stop_voice_requested.emit)
        chat_col.addWidget(self._composer)

        root.addLayout(chat_col, stretch=1)

        # Right Column: Central Voice Panel
        voice_panel = QFrame()
        voice_panel.setObjectName("Card")
        voice_panel.setFixedWidth(268)
        vl = QVBoxLayout(voice_panel)
        vl.setContentsMargins(16, 18, 16, 18)
        vl.setSpacing(12)

        vp_title = QLabel("VOICE INTERFACE")
        vp_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vp_title.setStyleSheet(
            f"font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: {COLORS['text_secondary']};"
        )
        vl.addWidget(vp_title)

        self._visualizer = VoiceVisualizerWidget()
        vl.addWidget(self._visualizer)

        # Mode & Control buttons
        self._hf_btn = QPushButton("Enable Hands-Free")
        self._hf_btn.setObjectName("AccentButton")
        self._hf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hf_btn.setMinimumHeight(36)
        self._hf_btn.clicked.connect(self._toggle_hands_free)
        self._hf_active = False
        vl.addWidget(self._hf_btn)

        ptt_btn = QPushButton("Push-to-Talk")
        ptt_btn.setObjectName("PrimaryButton")
        ptt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ptt_btn.setMinimumHeight(36)
        ptt_btn.clicked.connect(self.ptt_requested.emit)
        vl.addWidget(ptt_btn)

        stop_listening_btn = QPushButton("Stop Audio")
        stop_listening_btn.setObjectName("DangerButton")
        stop_listening_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_listening_btn.setMinimumHeight(34)
        stop_listening_btn.clicked.connect(self.disable_hands_free_requested.emit)
        vl.addWidget(stop_listening_btn)

        vl.addStretch(1)

        # Live Voice Subsystem Readout
        info_card = QFrame()
        info_card.setObjectName("SecondaryCard")
        il = QVBoxLayout(info_card)
        il.setContentsMargins(12, 10, 12, 10)
        il.setSpacing(4)
        self._wake_info_lbl = QLabel("Wake Word: Hey JARVIS")
        self._wake_info_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        self._stt_info_lbl = QLabel("STT: Faster-Whisper")
        self._stt_info_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        self._tts_info_lbl = QLabel("TTS: Piper")
        self._tts_info_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        il.addWidget(self._wake_info_lbl)
        il.addWidget(self._stt_info_lbl)
        il.addWidget(self._tts_info_lbl)
        vl.addWidget(info_card)

        root.addWidget(voice_panel)

    # ------------------------------------------------------------------
    #  Chat Timeline Operations
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> ChatMessageWidget:
        bubble = ChatMessageWidget(role=role, content=content)
        insert_idx = max(0, self._msg_layout.count() - 1)
        self._msg_layout.insertWidget(insert_idx, bubble)
        self._scroll_to_bottom()
        return bubble

    def start_streaming_assistant(self) -> None:
        if self._streaming_bubble is None:
            self._streaming_bubble = self.add_message("assistant", "")

    def append_stream_chunk(self, delta: str) -> None:
        if self._streaming_bubble is None:
            self.start_streaming_assistant()
        if self._streaming_bubble is not None:
            self._streaming_bubble.append_chunk(delta)
            self._scroll_to_bottom()

    def finalize_assistant_response(self, text: str, is_error: bool = False) -> None:
        if is_error:
            if self._streaming_bubble is not None and not self._streaming_bubble.get_content().strip():
                self._streaming_bubble.setParent(None)
                self._streaming_bubble.deleteLater()
            self._streaming_bubble = None
            self.add_message("error", text)
            return

        if self._streaming_bubble is not None:
            self._streaming_bubble.set_content(text)
            self._streaming_bubble = None
        else:
            self.add_message("assistant", text)
        self._scroll_to_bottom()

    def handle_tool_event(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        if kind == "tool_started":
            tools = ", ".join(event.get("tools", []))
            self.add_message("tool", f"Executing tool(s): {tools}…")
        elif kind == "tool_completed":
            steps = event.get("steps", [])
            summary = ", ".join(f"{s['name']} [{s['status']}]" for s in steps)
            if summary:
                self.add_message("tool", f"Tool step result: {summary}")

    def _on_send(self, text: str) -> None:
        self.add_message("user", text)
        self.start_streaming_assistant()
        self.send_message_requested.emit(text)

    def _on_clear_clicked(self) -> None:
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._streaming_bubble = None
        self.clear_chat_requested.emit()
        self.add_message("assistant", "Conversation cleared. Ready for your next request.")

    def _toggle_hands_free(self) -> None:
        if self._hf_active:
            self.disable_hands_free_requested.emit()
        else:
            self.enable_hands_free_requested.emit()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            15,
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ),
        )

    # ------------------------------------------------------------------
    #  State Updates
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        self._composer.set_busy(busy)

    def set_voice_state(self, state: VoiceState) -> None:
        self._visualizer.set_voice_state(state)
        self._composer.set_voice_state(state, VOICE_STATE_CAPTIONS.get(state, state.value))

    def set_audio_level(self, level: float) -> None:
        self._visualizer.set_audio_level(level)

    def update_health(self, snap: HealthSnapshot) -> None:
        self._model_pill.setText(f"Model: {snap.ai_model}")
        self._local_pill.setText("Local AI Only" if snap.local_ai_only else "Hybrid Mode")

        self._hf_active = snap.wake_detection_active
        self._hf_btn.setText("Disable Hands-Free" if self._hf_active else "Enable Hands-Free")

        ww_state = "Active" if snap.wake_detection_active else ("Ready" if snap.wake_word_available else "Missing")
        self._wake_info_lbl.setText(f"Wake Word ({snap.wake_word_phrase}): {ww_state}")
        self._stt_info_lbl.setText(f"STT: {'Ready' if snap.stt_available else 'Unavailable'}")
        self._tts_info_lbl.setText(f"TTS: {'Ready' if snap.tts_available else 'Unavailable'}")

    def composer(self) -> MessageInputWidget:
        return self._composer
