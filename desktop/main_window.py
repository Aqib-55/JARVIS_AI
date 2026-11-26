"""Main desktop window coordinating Sidebar, Topbar, Pages, and BackendAdapter."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import settings
from desktop import APP_NAME
from desktop.components.confirmation_dialog import ConfirmationDialog
from desktop.components.sidebar import SidebarWidget
from desktop.components.topbar import TopbarWidget
from desktop.pages.chat import ChatPage
from desktop.pages.dashboard import DashboardPage
from desktop.pages.memory import MemoryPage
from desktop.pages.settings import SettingsPage
from desktop.pages.tools import ToolsPage
from desktop.resources.icons.icon_factory import create_jarvis_icon
from desktop.services.backend_adapter import BackendAdapter
from desktop.services.ui_state import HealthSnapshot, ToolApprovalRequest, VoiceState


class JarvisMainWindow(QMainWindow):
    """Responsive 1440x900 native Windows desktop window for JARVIS AI."""

    def __init__(
        self,
        backend: BackendAdapter,
        auto_start_backend: bool = True,
        auto_start_voice: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self.setWindowTitle(f"{APP_NAME} — Local Personal AI Assistant")
        self.setWindowIcon(create_jarvis_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1000, 650)

        self._build_layout()
        self._wire_signals()

        # Populate initial static registry/memory/settings views cleanly
        self._load_tools_page()
        self._load_memory_page()
        self._settings_page.populate_microphones(
            self._backend.list_microphones(),
            settings.VOICE_MICROPHONE_INDEX,
        )
        self._apply_health(self._backend.get_health_snapshot())

        if auto_start_backend:
            self._backend.initialize_async(auto_start_voice=auto_start_voice)

    def _build_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Region 1: Persistent Sidebar
        self._sidebar = SidebarWidget()
        root.addWidget(self._sidebar)

        # Region 2 & 3: Topbar + Page Stack
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        self._topbar = TopbarWidget()
        right_col.addWidget(self._topbar)

        self._stack = QStackedWidget()
        self._dashboard_page = DashboardPage()
        self._chat_page = ChatPage()
        self._tools_page = ToolsPage()
        self._memory_page = MemoryPage()
        self._settings_page = SettingsPage()

        self._pages: dict[str, tuple[int, str]] = {
            "overview": (self._stack.addWidget(self._dashboard_page), "Overview"),
            "chat": (self._stack.addWidget(self._chat_page), "Chat"),
            "tools": (self._stack.addWidget(self._tools_page), "Tools"),
            "memory": (self._stack.addWidget(self._memory_page), "Memory"),
            "settings": (self._stack.addWidget(self._settings_page), "Settings"),
        }
        right_col.addWidget(self._stack, stretch=1)
        root.addLayout(right_col, stretch=1)

        # Default to Chat view on launch
        self.navigate_to("chat")

    def _wire_signals(self) -> None:
        # Navigation
        self._sidebar.page_selected.connect(self.navigate_to)

        # Topbar emergency stop / resume
        self._topbar.emergency_toggle_clicked.connect(self._on_emergency_toggle)

        # Dashboard quick actions
        self._dashboard_page.open_chat_requested.connect(lambda: self.navigate_to("chat"))
        self._dashboard_page.open_tools_requested.connect(lambda: self.navigate_to("tools"))
        self._dashboard_page.start_voice_requested.connect(self._backend.start_wake_word_mode)
        self._dashboard_page.stop_voice_requested.connect(self._backend.stop_voice_monitoring)
        self._dashboard_page.run_diagnostics_requested.connect(self._backend.run_diagnostics_async)

        # Chat page actions
        self._chat_page.send_message_requested.connect(self._on_send_chat)
        self._chat_page.clear_chat_requested.connect(self._backend.clear_conversation)
        self._chat_page.ptt_requested.connect(self._backend.trigger_push_to_talk)
        self._chat_page.stop_voice_requested.connect(self._backend.stop_speaking_or_listening)
        self._chat_page.enable_hands_free_requested.connect(self._backend.start_wake_word_mode)
        self._chat_page.disable_hands_free_requested.connect(self._backend.stop_voice_monitoring)

        # Tools page -> Chat
        self._tools_page.ask_in_chat_requested.connect(self._on_ask_tool_in_chat)

        # Memory page
        self._memory_page.refresh_requested.connect(self._load_memory_page)
        self._memory_page.search_requested.connect(self._on_memory_search)
        self._memory_page.delete_fact_requested.connect(self._on_delete_fact)
        self._memory_page.delete_pref_requested.connect(self._on_delete_pref)

        # Settings page
        self._settings_page.apply_settings_requested.connect(self._on_apply_settings)
        self._settings_page.diagnostics_requested.connect(self._backend.run_diagnostics_async)

        # BackendAdapter -> GUI Thread
        self._backend.health_updated.connect(self._apply_health)
        self._backend.voice_state_changed.connect(self._on_voice_state_changed)
        self._backend.audio_level_updated.connect(self._chat_page.set_audio_level)
        self._backend.stream_chunk_received.connect(self._chat_page.append_stream_chunk)
        self._backend.chat_response_ready.connect(self._on_chat_response_ready)
        self._backend.user_transcription_received.connect(self._on_voice_transcription)
        self._backend.voice_assistant_reply.connect(self._on_voice_assistant_reply)
        self._backend.wake_word_triggered.connect(self._on_wake_triggered)
        self._backend.tool_status_event.connect(self._chat_page.handle_tool_event)
        self._backend.speech_unavailable.connect(
            lambda reason: self._chat_page.add_message("error", f"Speech output unavailable: {reason}")
        )
        self._backend.diagnostics_ready.connect(self._on_diagnostics_ready)
        self._backend.busy_changed.connect(self._chat_page.set_busy)

        # Approval dialog modal bridge
        self._backend.approval_bridge.approval_requested.connect(
            self._on_approval_requested, Qt.ConnectionType.QueuedConnection
        )

    # ------------------------------------------------------------------
    #  Navigation & Page Refresh
    # ------------------------------------------------------------------

    def navigate_to(self, page_key: str) -> None:
        if page_key not in self._pages:
            return
        idx, title = self._pages[page_key]
        self._stack.setCurrentIndex(idx)
        self._sidebar.set_active_page(page_key)
        self._topbar.set_page_title(title)

        if page_key == "memory":
            self._load_memory_page()
        elif page_key == "tools":
            self._load_tools_page()
        elif page_key == "overview":
            self._backend.refresh_health_async()

    def _load_tools_page(self) -> None:
        snap = self._backend.get_health_snapshot()
        self._tools_page.set_tools(
            self._backend.get_registered_tools(),
            emergency_stopped=snap.emergency_stopped,
        )

    def _load_memory_page(self) -> None:
        snap = self._backend.get_health_snapshot()
        data = self._backend.get_memory_overview()
        self._memory_page.update_overview(data, db_enabled=snap.memory_enabled)

    # ------------------------------------------------------------------
    #  Slot Handlers
    # ------------------------------------------------------------------

    def _apply_health(self, snap: HealthSnapshot) -> None:
        self._sidebar.update_health(snap)
        self._topbar.update_health(snap)
        self._dashboard_page.update_health(snap)
        self._chat_page.update_health(snap)
        self._settings_page.update_health(
            snap,
            wake_threshold=settings.WAKE_WORD_THRESHOLD,
            voice_out=settings.VOICE_OUTPUT_ENABLED,
        )

    def _on_voice_state_changed(self, state: VoiceState) -> None:
        self._topbar.update_voice_state(state)
        self._chat_page.set_voice_state(state)

    def _on_send_chat(self, text: str) -> None:
        started = self._backend.send_chat_message(text)
        if not started:
            self._chat_page.finalize_assistant_response(
                "Please wait for the active request to complete.", is_error=True
            )

    def _on_chat_response_ready(self, text: str, is_error: bool) -> None:
        self._chat_page.finalize_assistant_response(text, is_error=is_error)
        self._load_memory_page()

    def _on_wake_triggered(self, ack: str) -> None:
        self._chat_page.add_message("tool", f"Hey JARVIS detected — {ack}")

    def _on_voice_transcription(self, text: str) -> None:
        if text.strip():
            self._chat_page.add_message("user", text)

    def _on_voice_assistant_reply(self, text: str) -> None:
        if text.strip():
            self._chat_page.add_message("assistant", text)
            self._load_memory_page()

    def _on_ask_tool_in_chat(self, prompt_text: str) -> None:
        self.navigate_to("chat")
        self._chat_page.composer().input_box().setPlainText(prompt_text)
        self._chat_page.composer().input_box().setFocus()

    def _on_memory_search(self, query: str) -> None:
        hits = self._backend.search_memory(query)
        self._memory_page.update_search_results(hits)

    def _on_delete_fact(self, fact_id: int) -> None:
        if self._backend.delete_fact(fact_id):
            self._load_memory_page()

    def _on_delete_pref(self, key: str) -> None:
        if self._backend.delete_preference(key):
            self._load_memory_page()

    def _on_apply_settings(self, threshold: float, timeout: float, mic_idx: object, voice_out: bool) -> None:
        self._backend.apply_runtime_settings(
            wake_threshold=threshold,
            conversation_timeout=timeout,
            mic_index=mic_idx if isinstance(mic_idx, int) else None,
            voice_output_enabled=voice_out,
        )

    def _on_diagnostics_ready(self, data: dict) -> None:
        self._dashboard_page.show_diagnostics_result(data)
        self._settings_page.show_diagnostics(data)
        if "health" in data and isinstance(data["health"], HealthSnapshot):
            self._apply_health(data["health"])

    def _on_emergency_toggle(self, currently_stopped: bool) -> None:
        if currently_stopped:
            self._backend.clear_emergency_stop()
        else:
            self._backend.trigger_emergency_stop()
        self._load_tools_page()

    def _on_approval_requested(self, req_id: str, req: ToolApprovalRequest) -> None:
        dlg = ConfirmationDialog(req, parent=self)
        approved = dlg.exec() == ConfirmationDialog.DialogCode.Accepted
        self._backend.approval_bridge.resolve(req_id, approved)

    # ------------------------------------------------------------------
    #  Clean Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._dashboard_page._clock_timer.stop()
        self._chat_page._visualizer._orb._timer.stop()
        self._backend.shutdown()
        super().closeEvent(event)
