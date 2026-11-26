"""Comprehensive PySide6 Desktop UI, Responsiveness, Approval & Backend Integration Tests."""

from __future__ import annotations

import gc
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, QThreadPool, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import settings
from core.agent import JarvisAgent
from desktop.components.chat_message import ChatMessageWidget
from desktop.components.confirmation_dialog import ConfirmationDialog
from desktop.components.voice_visualizer import VoiceVisualizerWidget
from desktop.main_window import JarvisMainWindow
from desktop.resources.icons.icon_factory import create_jarvis_icon, ensure_app_ico
from desktop.services.backend_adapter import BackendAdapter
from desktop.services.ui_state import HealthSnapshot, VoiceState
from main import register_tools
from memory.database import DatabaseManager
from providers.base import BaseProvider, FunctionCall, ModelResponse
from tools.registry import ToolRegistry
from voice.voice_controller import VoiceController


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.closeAllWindows()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    QThreadPool.globalInstance().waitForDone(2000)
    gc.collect()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


class _DummyProvider(BaseProvider):
    """Deterministic local stub provider implementing BaseProvider cleanly."""

    def __init__(self, reply: str = "Local response ready.", delay: float = 0.0, connected: bool = True):
        self._reply = reply
        self._delay = delay
        self._connected = connected
        self._tool_call_once: FunctionCall | None = None

    def connect(self) -> bool:
        return self._connected

    def is_connected(self) -> bool:
        return self._connected

    def get_model_name(self) -> str:
        return "qwen3.5:4b"

    def get_provider_name(self) -> str:
        return "Ollama"

    def generate(self, messages, system_instruction=None, stream_callback=None) -> ModelResponse:
        if self._delay > 0:
            time.sleep(self._delay)
        if stream_callback is not None:
            for chunk in self._reply.split(" "):
                stream_callback(chunk + " ")
        return ModelResponse(text=self._reply, provider="Ollama", model="qwen3.5:4b")

    def generate_with_tools(
        self,
        messages,
        tool_declarations,
        system_instruction=None,
        stream_callback=None,
    ) -> ModelResponse:
        if self._delay > 0:
            time.sleep(self._delay)
        if self._tool_call_once is not None:
            fc = self._tool_call_once
            self._tool_call_once = None
            return ModelResponse(text=None, function_calls=[fc], provider="Ollama", model="qwen3.5:4b")
        if stream_callback is not None:
            for chunk in self._reply.split(" "):
                stream_callback(chunk + " ")
        return ModelResponse(text=self._reply, function_calls=[], provider="Ollama", model="qwen3.5:4b")

    def send_function_results(
        self,
        messages,
        function_calls,
        function_responses,
        tool_declarations,
        system_instruction=None,
        stream_callback=None,
    ) -> ModelResponse:
        if stream_callback is not None:
            stream_callback(self._reply)
        return ModelResponse(text=self._reply, function_calls=[], provider="Ollama", model="qwen3.5:4b")


def _make_adapter(tmp_path: Path, provider: BaseProvider | None = None) -> BackendAdapter:
    db = DatabaseManager(tmp_path / "jarvis_ui_test.db")
    db.initialize()
    registry = ToolRegistry()
    register_tools(registry)
    prov = provider or _DummyProvider()
    agent = JarvisAgent(provider=prov, registry=registry, db=db)
    agent._connected = prov.connect()
    agent._conversation_history.start_session()

    mock_stt = MagicMock()
    mock_stt.is_available.return_value = False
    mock_stt.engine_name = "Faster-Whisper"
    mock_tts = MagicMock()
    mock_tts.is_available.return_value = False
    mock_tts.engine_name = "Piper"

    vc = VoiceController(
        agent=agent,
        stt_engine=mock_stt,
        tts_engine=mock_tts,
    )
    hf = MagicMock()
    hf.is_monitoring = False
    hf.get_status.return_value = {
        "wake_detection_enabled": False,
        "wake_word_available": True,
        "wake_word_phrase": "hey_jarvis",
        "mic_monitoring": False,
        "mic_device": "Test Mic",
        "conversation_timeout_seconds": 25.0,
        "last_error": "",
    }
    return BackendAdapter(
        agent=agent,
        registry=registry,
        db=db,
        voice_controller=vc,
        hands_free=hf,
    )


def _process_until(condition, timeout_ms: int = 3000) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        QTest.qWait(15)
    return bool(condition())


def test_window_launch_sizing_and_navigation(qapp, tmp_path: Path):
    adapter = _make_adapter(tmp_path)
    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)

    assert win.width() == 1440
    assert win.height() == 900
    assert win.minimumWidth() == 1000
    assert win.minimumHeight() == 650

    for page_key in ("overview", "chat", "tools", "memory", "settings"):
        win.navigate_to(page_key)
        expected_idx = win._pages[page_key][0]
        assert win._stack.currentIndex() == expected_idx
        assert win._topbar._title_lbl.text() == win._pages[page_key][1]

    win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()


def test_ico_generation_and_icon_factory(qapp, tmp_path: Path):
    icon = create_jarvis_icon()
    assert not icon.isNull()
    ico_path = tmp_path / "jarvis.ico"
    ensure_app_ico(ico_path)
    assert ico_path.exists()
    assert ico_path.stat().st_size > 100


def test_tools_page_shows_real_26_tools_and_categories(qapp, tmp_path: Path):
    adapter = _make_adapter(tmp_path)
    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)
    win.navigate_to("tools")

    tools = adapter.get_registered_tools()
    assert len(tools) == 26
    assert "26 / 26" in win._tools_page._count_lbl.text()

    # Search filter works
    win._tools_page._search_edit.setText("datetime")
    QApplication.processEvents()
    assert "1 / 26" in win._tools_page._count_lbl.text()

    win._tools_page._search_edit.clear()
    QApplication.processEvents()
    assert "26 / 26" in win._tools_page._count_lbl.text()

    # Emergency Stop propagates cleanly to topbar + ToolsPage
    win._on_emergency_toggle(False)
    QApplication.processEvents()
    assert adapter.get_health_snapshot().emergency_stopped is True
    assert win._tools_page._emergency_stopped is True
    win._on_emergency_toggle(True)
    QApplication.processEvents()
    assert adapter.get_health_snapshot().emergency_stopped is False

    win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()


def test_memory_page_real_sqlite_read_search_and_confirmed_delete(qapp, tmp_path: Path):
    adapter = _make_adapter(tmp_path)
    fact_id = adapter._agent.memory_manager.add_fact("technical", "User prefers Python 3.13")
    adapter._agent.memory_manager.set_preference("theme_mode", "dark")

    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)
    win.navigate_to("memory")
    QApplication.processEvents()

    assert win._memory_page._facts_table.rowCount() >= 1
    assert win._memory_page._prefs_table.rowCount() >= 1

    # Search existing SQLite records
    win._memory_page._search_edit.setText("Python 3.13")
    win._memory_page._on_search()
    QApplication.processEvents()
    assert win._memory_page._search_table.rowCount() >= 1

    # Deletion requires confirmation: Reject preserves fact, Approve deletes fact
    win._memory_page._facts_table.selectRow(0)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        win._memory_page._on_delete_fact()
    assert len(adapter._agent.memory_manager.get_facts()) == 1

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        win._memory_page._on_delete_fact()
    assert all(f["id"] != fact_id for f in adapter._agent.memory_manager.get_facts())

    win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()


def test_dashboard_status_cards_reflect_honest_connected_and_disconnected_states(qapp, tmp_path: Path):
    adapter = _make_adapter(tmp_path, provider=_DummyProvider(connected=False))
    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)

    snap_offline = HealthSnapshot(
        ai_connected=False,
        ai_provider="Ollama",
        ai_model="qwen3.5:4b",
        local_ai_only=True,
        ollama_url="http://127.0.0.1:11434",
        stt_engine="Faster-Whisper",
        stt_available=False,
        whisper_model="base",
        tts_engine="Piper",
        tts_available=False,
        piper_voice="en_GB-alan-medium",
        wake_word_phrase="hey_jarvis",
        wake_word_available=False,
        wake_detection_active=False,
        mic_monitoring=False,
        mic_device="None",
        memory_enabled=False,
        tools_count=26,
        emergency_stopped=False,
        conversation_timeout_seconds=25.0,
    )
    win._apply_health(snap_offline)
    assert win._dashboard_page._card_ollama._value_lbl.text() == "Ollama Unavailable"
    assert win._dashboard_page._card_stt._value_lbl.text() == "STT Unavailable"
    assert win._dashboard_page._card_memory._value_lbl.text() == "SQLite Not Initialized"

    snap_online = HealthSnapshot(
        ai_connected=True,
        ai_provider="Ollama",
        ai_model="qwen3.5:4b",
        local_ai_only=True,
        ollama_url="http://127.0.0.1:11434",
        stt_engine="Faster-Whisper",
        stt_available=True,
        whisper_model="base",
        tts_engine="Piper",
        tts_available=True,
        piper_voice="en_GB-alan-medium",
        wake_word_phrase="hey_jarvis",
        wake_word_available=True,
        wake_detection_active=True,
        mic_monitoring=True,
        mic_device="Test Mic",
        memory_enabled=True,
        tools_count=26,
        emergency_stopped=False,
        conversation_timeout_seconds=25.0,
    )
    win._apply_health(snap_online)
    assert win._dashboard_page._card_ollama._value_lbl.text() == "Ollama Connected"
    assert win._dashboard_page._card_stt._value_lbl.text() == "Faster-Whisper Ready"
    assert win._dashboard_page._card_wake._value_lbl.text() == "Hey JARVIS Enabled"
    assert win._dashboard_page._card_memory._value_lbl.text() == "SQLite Connected"

    win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()


def test_nonblocking_streaming_chat_copy_button_and_serialized_queue(qapp, tmp_path: Path):
    prov = _DummyProvider(reply="Hello from **local** Qwen!", delay=0.18, connected=True)
    adapter = _make_adapter(tmp_path, provider=prov)
    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)

    # GUI timer must keep ticking while worker sleeps in background thread
    ticks = []
    probe_timer = QTimer()
    probe_timer.setInterval(25)
    probe_timer.timeout.connect(lambda: ticks.append(1))
    probe_timer.start()

    win._chat_page.send_message_requested.emit("Ping JARVIS")
    assert adapter.is_busy is True
    # Concurrent duplicate submit must be ignored cleanly
    assert adapter.send_chat_message("Duplicate request", speak_reply=False) is False

    finished = _process_until(lambda: not adapter.is_busy, timeout_ms=3000)
    probe_timer.stop()

    assert finished is True
    assert len(ticks) >= 3  # UI stayed responsive during 180ms background worker
    assert adapter.is_busy is False

    # Copy button copies message text to QClipboard
    msg_widget = ChatMessageWidget("assistant", "Sample **markdown** text")
    msg_widget._copy_text()
    assert QApplication.clipboard().text() == "Sample **markdown** text"

    win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()


def test_approval_dialog_wired_to_real_executor_approve_and_reject(qapp, tmp_path: Path):
    prov = _DummyProvider(reply="Deletion step processed.", delay=0.0, connected=True)
    adapter = _make_adapter(tmp_path, provider=prov)

    workspace_dir = settings.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True, exist_ok=True)
    probe_name = "_gui_approval_probe.txt"
    safe_file = workspace_dir / probe_name
    safe_file.write_text("Probe content for confirmation dialog", encoding="utf-8")

    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)

    try:
        # 1. User rejects Level 3 delete_file -> file MUST still exist
        prov._tool_call_once = FunctionCall(
            name="delete_file",
            args={"file_name": probe_name, "confirm": True},
        )
        with patch.object(ConfirmationDialog, "exec", return_value=ConfirmationDialog.DialogCode.Rejected):
            win._on_send_chat(f"Delete {probe_name}")
            assert _process_until(lambda: not adapter.is_busy, timeout_ms=4000)
        assert safe_file.exists()

        # 2. User approves Level 3 delete_file -> real TaskExecutor deletes the file
        prov._tool_call_once = FunctionCall(
            name="delete_file",
            args={"file_name": probe_name, "confirm": True},
        )
        with patch.object(ConfirmationDialog, "exec", return_value=ConfirmationDialog.DialogCode.Accepted):
            win._on_send_chat(f"Delete {probe_name}")
            assert _process_until(lambda: not adapter.is_busy, timeout_ms=4000)
        assert not safe_file.exists()
    finally:
        safe_file.unlink(missing_ok=True)
        win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()


def test_voice_visualizer_states_and_privacy_controls(qapp, tmp_path: Path):
    vis = VoiceVisualizerWidget()
    for state in VoiceState:
        vis.set_voice_state(state)
        assert vis._orb._state == state

    vis.set_voice_state(VoiceState.LISTENING)
    vis.set_audio_level(0.75)
    assert vis._orb._audio_level == pytest.approx(0.75)

    # Returning to IDLE zeroes fake/residual bars
    vis.set_voice_state(VoiceState.IDLE)
    assert vis._orb._audio_level == 0.0

    # auto_start_voice=False must NOT call hands_free.start()
    adapter = _make_adapter(tmp_path)
    adapter.initialize_sync(auto_start_voice=False)
    adapter._hands_free.start.assert_not_called()

    # Stopping voice monitoring calls hands_free.stop() asynchronously on QThreadPool
    adapter.stop_voice_monitoring()
    assert _process_until(lambda: adapter._hands_free.stop.called, timeout_ms=2000)

    # Closing main window invokes clean shutdown
    win = JarvisMainWindow(backend=adapter, auto_start_backend=False, auto_start_voice=False)
    win.close()
    win.deleteLater()
    adapter.deleteLater()
    QApplication.processEvents()
    adapter._hands_free.stop.assert_called()
