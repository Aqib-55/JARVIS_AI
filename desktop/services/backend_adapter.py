"""
Backend Adapter connecting the PySide6 Desktop UI to existing JARVIS services.

Reuses directly without duplicating or rebuilding:
  - providers.factory.get_provider (OllamaProvider)
  - main.register_tools + tools.registry.ToolRegistry (26 tools)
  - core.agent.JarvisAgent (planner, executor, 4-tier permissions)
  - memory.* (DatabaseManager, MemoryManager, TaskHistoryManager, ConversationHistoryManager)
  - voice.* (VoiceController, HandsFreeConversationManager, MicrophoneCapture, OpenWakeWordDetector)
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal

from config.settings import settings
from core.agent import JarvisAgent
from core.permissions import PermissionCheck
from core.planner import TaskStep
from desktop.services.ui_state import (
    HealthSnapshot,
    ToolApprovalRequest,
    VoiceState,
)
from desktop.services.workers import CallableWorker, GuiApprovalBridge
from main import register_tools
from memory.conversation_history import ConversationHistoryManager
from memory.database import DatabaseManager
from memory.task_history import TaskHistoryManager
from providers.factory import get_provider
from tools import ToolDefinition
from tools.registry import ToolRegistry
from voice.conversation_manager import (
    HandsFreeConversationManager,
    VoicePipelineState,
)
from voice.voice_controller import AudioState, VoiceController, VoiceMode
from voice.wake_word import (
    MicrophoneCapture,
    OpenWakeWordDetector,
    list_input_devices,
)

logger = logging.getLogger(__name__)

_PIPELINE_TO_VOICE_STATE: dict[VoicePipelineState, VoiceState] = {
    VoicePipelineState.STARTING: VoiceState.IDLE,
    VoicePipelineState.IDLE_WAKE_LISTENING: VoiceState.IDLE,
    VoicePipelineState.WAKE_DETECTED: VoiceState.WAKE_DETECTED,
    VoicePipelineState.AWAITING_COMMAND: VoiceState.LISTENING,
    VoicePipelineState.CAPTURING_COMMAND: VoiceState.LISTENING,
    VoicePipelineState.TRANSCRIBING: VoiceState.TRANSCRIBING,
    VoicePipelineState.PROCESSING_WITH_QWEN: VoiceState.THINKING,
    VoicePipelineState.SPEAKING_WITH_PIPER: VoiceState.SPEAKING,
    VoicePipelineState.CONVERSATION_ACTIVE: VoiceState.LISTENING,
    VoicePipelineState.DISABLED: VoiceState.IDLE,
    VoicePipelineState.ERROR: VoiceState.ERROR,
}

_AUDIO_TO_VOICE_STATE: dict[AudioState, VoiceState] = {
    AudioState.IDLE: VoiceState.IDLE,
    AudioState.LISTENING: VoiceState.LISTENING,
    AudioState.PROCESSING: VoiceState.THINKING,
    AudioState.SPEAKING: VoiceState.SPEAKING,
    AudioState.WAITING_FOR_APPROVAL: VoiceState.EXECUTING_TOOL,
    AudioState.ERROR: VoiceState.ERROR,
}

_SENSITIVE_KEY_TOKENS = ("key", "token", "secret", "password", "credential")


class BackendAdapter(QObject):
    """Thin, thread-safe Qt adapter around existing JARVIS backend services."""

    # Signals emitted safely to the GUI thread
    health_updated = Signal(object)            # HealthSnapshot
    voice_state_changed = Signal(object)       # VoiceState
    audio_level_updated = Signal(float)        # normalized 0.0 .. 1.0 (real mic RMS)
    stream_chunk_received = Signal(str)        # incremental assistant text delta
    chat_response_ready = Signal(str, bool)    # (text, is_error)
    user_transcription_received = Signal(str)  # recognized spoken user text
    voice_assistant_reply = Signal(str)        # assistant reply from voice turn
    wake_word_triggered = Signal(str)          # acknowledgment message
    tool_status_event = Signal(object)         # dict from agent tool hook
    speech_unavailable = Signal(str)           # reason when TTS fails
    diagnostics_ready = Signal(object)         # dict from run_self_test
    busy_changed = Signal(bool)                # True while chat/PTT request active

    def __init__(
        self,
        agent: JarvisAgent | None = None,
        registry: ToolRegistry | None = None,
        db: DatabaseManager | None = None,
        voice_controller: VoiceController | None = None,
        hands_free: HandsFreeConversationManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._agent_lock = threading.RLock()
        self._request_lock = threading.Lock()
        self._workers_lock = threading.Lock()
        self._active_workers: set[CallableWorker] = set()
        self._shutting_down = False
        self._busy = False
        self._initialized = False
        self._voice_state = VoiceState.IDLE

        self.approval_bridge = GuiApprovalBridge(self)

        # Construct or reuse injected backend objects (enables deterministic testing)
        self._registry = registry or ToolRegistry()
        if len(self._registry.list_tools()) == 0:
            register_tools(self._registry)

        self._db = db or DatabaseManager()
        self._provider = None
        if agent is None:
            self._provider = get_provider(settings.AI_PROVIDER)
            self._agent = JarvisAgent(
                provider=self._provider,
                registry=self._registry,
                db=self._db,
                approval_callback=self._on_tool_approval_needed,
            )
        else:
            self._agent = agent
            self._agent._approval_callback = self._on_tool_approval_needed

        self._agent.set_tool_event_callback(self._on_agent_tool_event)

        self._task_history = self._agent._task_history
        self._conversation_history = self._agent._conversation_history

        self._mic = MicrophoneCapture(on_audio_level=self._on_mic_rms)
        self._wake_detector = OpenWakeWordDetector()

        if voice_controller is not None:
            self._voice = voice_controller
        elif settings.VOICE_ENABLED:
            try:
                vc_mode = (
                    VoiceMode.CONTINUOUS
                    if settings.VOICE_MODE in ("hands_free", "continuous")
                    else VoiceMode.PUSH_TO_TALK
                )
                self._voice = VoiceController(
                    agent=self._agent,
                    mode=vc_mode,
                    on_state_change=self._on_vc_state_change,
                    on_transcription=self._on_vc_transcription,
                    on_speech_unavailable=self._on_speech_unavailable,
                )
            except Exception as e:
                logger.warning("VoiceController init failed: %s", e)
                self._voice = None
        else:
            self._voice = None

        if hands_free is not None:
            self._hands_free: HandsFreeConversationManager | None = hands_free
        elif self._voice is not None:
            self._hands_free = HandsFreeConversationManager(
                agent=self._agent,
                voice_controller=self._voice,
                agent_lock=self._agent_lock,
                wake_detector=self._wake_detector,
                mic_capture=self._mic,
                on_output=lambda _msg: None,  # Desktop renders structured events
                on_state_change=self._on_pipeline_state_change,
                on_ui_event=self._on_hands_free_event,
            )
        else:
            self._hands_free = None

        if self._voice is not None:
            self._agent.set_voice_diagnostics_provider(self._combined_voice_diagnostics)

    # ------------------------------------------------------------------
    #  Initialization & Shutdown
    # ------------------------------------------------------------------

    def _start_worker(
        self,
        fn: Any,
        on_finished: Any = None,
        on_error: Any = None,
    ) -> None:
        """Schedule a CallableWorker while retaining Python lifetime until completion."""
        if self._shutting_down:
            return
        worker = CallableWorker(fn)
        worker.setAutoDelete(False)
        with self._workers_lock:
            self._active_workers.add(worker)

        def _release() -> None:
            with self._workers_lock:
                self._active_workers.discard(worker)

        def _handle_finished(res: Any) -> None:
            _release()
            if not self._shutting_down and on_finished is not None:
                on_finished(res)

        def _handle_error(err: str) -> None:
            _release()
            if not self._shutting_down and on_error is not None:
                on_error(err)

        worker.signals.finished.connect(_handle_finished)
        worker.signals.error.connect(_handle_error)
        self._pool.start(worker)

    def initialize_async(self, auto_start_voice: bool = True) -> None:
        """Connect Ollama, initialize SQLite, and optionally start wake listening off UI thread."""
        self._start_worker(
            lambda: self.initialize_sync(auto_start_voice),
            on_finished=lambda snap: self.health_updated.emit(snap),
            on_error=lambda err: logger.error("Backend init error: %s", err),
        )

    def initialize_sync(self, auto_start_voice: bool = True) -> HealthSnapshot:
        """Initialize backend synchronously (called by worker thread or tests)."""
        self._agent.initialize()
        self._initialized = True
        if (
            auto_start_voice
            and self._hands_free is not None
            and settings.VOICE_INPUT_ENABLED
            and settings.WAKE_WORD_ENABLED
            and settings.VOICE_MODE != "text"
        ):
            self._hands_free.start()
        return self.get_health_snapshot()

    def shutdown(self) -> None:
        """Stop active audio streams, workers, approval waits, and close agent session cleanly."""
        self._shutting_down = True
        self.approval_bridge.cancel_all()
        if self._hands_free is not None:
            try:
                self._hands_free.stop()
            except Exception as e:
                logger.debug("Hands-free stop error: %s", e)
        if self._voice is not None:
            try:
                self._voice.stop_speaking()
                self._voice.cancel_listening()
            except Exception as e:
                logger.debug("VoiceController cleanup error: %s", e)
        self._pool.waitForDone(3000)
        with self._workers_lock:
            self._active_workers.clear()
        try:
            self._agent.shutdown()
        except Exception as e:
            logger.debug("Agent shutdown error: %s", e)

    # ------------------------------------------------------------------
    #  Internal Event Translators (Worker Thread -> Qt Signals)
    # ------------------------------------------------------------------

    def _on_tool_approval_needed(self, step: TaskStep, check: PermissionCheck) -> bool:
        defn = self._registry.get_definition(step.tool_name)
        req = ToolApprovalRequest(
            tool_name=step.tool_name,
            arguments=dict(step.arguments or {}),
            risk_level=check.risk_level.value,
            reason=check.reason,
            description=defn.description if defn else "",
        )
        self._set_voice_state(VoiceState.EXECUTING_TOOL)
        return self.approval_bridge.request_approval(req)

    def _on_agent_tool_event(self, payload: dict[str, Any]) -> None:
        ev = payload.get("event")
        if ev == "tool_started":
            self._set_voice_state(VoiceState.EXECUTING_TOOL)
        self.tool_status_event.emit(payload)

    def _on_vc_state_change(self, state: AudioState) -> None:
        mapped = _AUDIO_TO_VOICE_STATE.get(state, VoiceState.IDLE)
        if mapped == VoiceState.IDLE and self._hands_free and self._hands_free.is_monitoring:
            mapped = _PIPELINE_TO_VOICE_STATE.get(self._hands_free.state, VoiceState.IDLE)
        self._set_voice_state(mapped)

    def _on_pipeline_state_change(self, state: VoicePipelineState) -> None:
        mapped = _PIPELINE_TO_VOICE_STATE.get(state, VoiceState.IDLE)
        self._set_voice_state(mapped)
        self.health_updated.emit(self.get_health_snapshot())

    def _on_vc_transcription(self, text: str) -> None:
        self.user_transcription_received.emit(text)

    def _on_speech_unavailable(self, reason: str) -> None:
        self.speech_unavailable.emit(reason)

    def _on_mic_rms(self, level: float) -> None:
        # Only forward live mic amplitude when listening/monitoring
        if self._voice_state in (VoiceState.IDLE, VoiceState.LISTENING, VoiceState.WAKE_DETECTED):
            if self._hands_free and self._hands_free.is_monitoring:
                self.audio_level_updated.emit(level)
            elif self._voice_state == VoiceState.LISTENING:
                self.audio_level_updated.emit(level)

    def _on_hands_free_event(self, payload: dict[str, Any]) -> None:
        kind = payload.get("type")
        if kind == "wake_detected":
            self.wake_word_triggered.emit(payload.get("ack", "Yes, I'm listening."))
        elif kind == "transcription":
            self.user_transcription_received.emit(payload.get("text", ""))
        elif kind == "assistant_reply":
            self.voice_assistant_reply.emit(payload.get("text", ""))

    def _set_voice_state(self, state: VoiceState) -> None:
        if self._voice_state == state:
            return
        self._voice_state = state
        if state not in (VoiceState.LISTENING, VoiceState.IDLE):
            self.audio_level_updated.emit(0.0)
        self.voice_state_changed.emit(state)

    # ------------------------------------------------------------------
    #  Health & Diagnostics
    # ------------------------------------------------------------------

    def _combined_voice_diagnostics(self) -> dict[str, Any]:
        diag = self._voice.get_diagnostics() if self._voice else {}
        if self._hands_free is not None:
            hf = self._hands_free.get_status()
            diag.update(
                {
                    "wake_detection_enabled": hf.get("wake_detection_enabled", False),
                    "wake_word_phrase": hf.get("wake_word_phrase"),
                    "mic_monitoring": hf.get("mic_monitoring", False),
                    "pipeline_state": hf.get("pipeline_state"),
                }
            )
        return diag

    def get_health_snapshot(self) -> HealthSnapshot:
        """Assemble real health status from active backend components (never hardcoded)."""
        s = self._agent.get_status()
        vd = self._voice.get_diagnostics() if self._voice else {}
        hf = self._hands_free.get_status() if self._hands_free else {}

        return HealthSnapshot(
            ai_connected=bool(s.get("connected", False)),
            ai_provider=str(s.get("provider", settings.AI_PROVIDER)),
            ai_model=str(s.get("model", settings.OLLAMA_MODEL)),
            local_ai_only=settings.LOCAL_AI_ONLY,
            ollama_url=settings.OLLAMA_BASE_URL,
            stt_engine=str(vd.get("stt_engine", settings.STT_ENGINE)),
            stt_available=bool(vd.get("stt_available", False)),
            whisper_model=settings.WHISPER_MODEL_SIZE,
            tts_engine=str(vd.get("tts_engine", settings.TTS_ENGINE)),
            tts_available=bool(vd.get("tts_available", False)),
            piper_voice=settings.PIPER_VOICE,
            wake_word_phrase=str(hf.get("wake_word_phrase", settings.WAKE_WORD_PHRASE)),
            wake_word_available=bool(hf.get("wake_word_available", self._wake_detector.is_available())),
            wake_detection_active=bool(hf.get("wake_detection_enabled", False)),
            mic_monitoring=bool(hf.get("mic_monitoring", False)),
            mic_device=str(hf.get("mic_device", self._mic.selected_device_name or "default")),
            memory_enabled=(s.get("memory") == "enabled"),
            tools_count=int(s.get("tools", len(self._registry.list_tools()))),
            emergency_stopped=bool(s.get("emergency_stopped", False)),
            conversation_timeout_seconds=float(
                hf.get("conversation_timeout_seconds", settings.CONVERSATION_TIMEOUT_SECONDS)
            ),
            last_error=str(hf.get("last_error", "")),
        )

    def refresh_health_async(self) -> None:
        self._start_worker(
            self.get_health_snapshot,
            on_finished=lambda snap: self.health_updated.emit(snap),
        )

    # ------------------------------------------------------------------
    #  Chat Execution (Serialized, Non-Blocking, Streaming)
    # ------------------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        return self._busy

    def send_chat_message(self, text: str, speak_reply: bool = True) -> bool:
        """
        Submit a typed user message asynchronously on QThreadPool.
        Prevents overlapping concurrent requests cleanly.
        """
        clean = text.strip()
        if not clean:
            return False

        with self._request_lock:
            if self._busy:
                return False
            self._busy = True

        self.busy_changed.emit(True)
        self._set_voice_state(VoiceState.THINKING)

        def _task() -> tuple[str, bool]:
            try:
                with self._agent_lock:
                    cb = (
                        (lambda delta: self.stream_chunk_received.emit(delta))
                        if settings.OLLAMA_STREAM
                        else None
                    )
                    reply = self._agent.process_message(clean, stream_callback=cb)

                if speak_reply and self._voice and settings.VOICE_OUTPUT_ENABLED and self._voice.mode != VoiceMode.TEXT:
                    if self._hands_free is not None and self._hands_free.is_monitoring:
                        self._hands_free._speak_safe(reply)
                        self._hands_free._set_state(VoicePipelineState.IDLE_WAKE_LISTENING)
                    else:
                        self._voice.speak_response(reply)
                return reply, reply.startswith("⚠️")
            finally:
                with self._request_lock:
                    self._busy = False
                if not self._shutting_down:
                    try:
                        self.busy_changed.emit(False)
                        if not (self._hands_free and self._hands_free.is_monitoring):
                            self._set_voice_state(VoiceState.IDLE)
                    except RuntimeError:
                        pass

        self._start_worker(
            _task,
            on_finished=lambda res: self.chat_response_ready.emit(res[0], res[1]),
            on_error=lambda err: self.chat_response_ready.emit(err, True),
        )
        return True

    def clear_conversation(self) -> None:
        with self._agent_lock:
            self._agent.clear_conversation()
        self.health_updated.emit(self.get_health_snapshot())

    # ------------------------------------------------------------------
    #  Voice Controls (Wake-Word & Push-to-Talk)
    # ------------------------------------------------------------------

    def start_wake_word_mode(self) -> None:
        def _start() -> HealthSnapshot:
            if self._hands_free is not None:
                self._hands_free.start()
            return self.get_health_snapshot()

        self._start_worker(
            _start,
            on_finished=lambda snap: self.health_updated.emit(snap),
        )

    def stop_voice_monitoring(self) -> None:
        """Stop hands-free wake listening and close hardware microphone completely."""
        def _stop() -> HealthSnapshot:
            if self._hands_free is not None:
                self._hands_free.stop()
            if self._voice is not None:
                self._voice.stop_speaking()
                self._voice.cancel_listening()
                self._voice.set_mode(VoiceMode.TEXT)
            self._set_voice_state(VoiceState.IDLE)
            self.audio_level_updated.emit(0.0)
            return self.get_health_snapshot()

        self._start_worker(
            _stop,
            on_finished=lambda snap: self.health_updated.emit(snap),
        )

    def trigger_push_to_talk(self) -> bool:
        """Run one push-to-talk capture/transcribe/respond/speak cycle off UI thread."""
        if self._voice is None:
            self.speech_unavailable.emit("Voice subsystem is disabled.")
            return False

        with self._request_lock:
            if self._busy:
                return False
            self._busy = True

        self.busy_changed.emit(True)

        def _ptt() -> HealthSnapshot:
            try:
                if self._hands_free is not None:
                    self._hands_free.trigger_push_to_talk()
                else:
                    with self._agent_lock:
                        self._voice.set_mode(VoiceMode.PUSH_TO_TALK)
                        self._voice.listen_and_process()
                return self.get_health_snapshot()
            finally:
                with self._request_lock:
                    self._busy = False
                self.busy_changed.emit(False)

        self._start_worker(
            _ptt,
            on_finished=lambda snap: self.health_updated.emit(snap),
            on_error=lambda err: self.speech_unavailable.emit(err),
        )
        return True

    def stop_speaking_or_listening(self) -> None:
        if self._voice is not None:
            self._voice.stop_speaking()
            self._voice.cancel_listening()
        self._set_voice_state(VoiceState.IDLE)

    def run_diagnostics_async(self) -> None:
        def _diag() -> dict[str, Any]:
            res: dict[str, Any] = {}
            if self._hands_free is not None:
                res = self._hands_free.run_self_test()
            res["health"] = self.get_health_snapshot()
            return res

        self._start_worker(
            _diag,
            on_finished=lambda data: self.diagnostics_ready.emit(data),
            on_error=lambda err: self.diagnostics_ready.emit({"error": err}),
        )

    # ------------------------------------------------------------------
    #  Tools & Safety
    # ------------------------------------------------------------------

    def get_registered_tools(self) -> list[ToolDefinition]:
        return self._registry.list_tools()

    def trigger_emergency_stop(self) -> HealthSnapshot:
        self.stop_voice_monitoring()
        self._agent.trigger_emergency_stop("Emergency stop triggered from Desktop UI.")
        snap = self.get_health_snapshot()
        self.health_updated.emit(snap)
        return snap

    def clear_emergency_stop(self) -> HealthSnapshot:
        self._agent.clear_emergency_stop()
        snap = self.get_health_snapshot()
        self.health_updated.emit(snap)
        return snap

    # ------------------------------------------------------------------
    #  Memory Access (SQLite via Existing Managers — Safe Subset Only)
    # ------------------------------------------------------------------

    def get_memory_overview(self) -> dict[str, Any]:
        prefs_raw = self._agent.memory_manager.get_all_preferences()
        safe_prefs = {
            k: v
            for k, v in prefs_raw.items()
            if not any(tok in k.lower() for tok in _SENSITIVE_KEY_TOKENS)
        }
        return {
            "facts": self._agent.memory_manager.get_facts(limit=100),
            "preferences": safe_prefs,
            "tasks": self._task_history.get_recent_tasks(limit=30),
            "session_messages": self._conversation_history.get_session_messages(limit=100),
            "tool_metrics": self._agent.memory_manager.get_frequently_used_tools(limit=15),
        }

    def search_memory(self, query: str) -> dict[str, list[dict[str, Any]]]:
        return self._agent.memory_manager.search_memory(query, limit=25)

    def delete_fact(self, fact_id: int) -> bool:
        return self._agent.memory_manager.delete_fact(fact_id)

    def delete_preference(self, key: str) -> bool:
        return self._agent.memory_manager.delete_preference(key)

    def list_microphones(self) -> list[dict[str, Any]]:
        return list_input_devices()

    # ------------------------------------------------------------------
    #  Safe Runtime Settings
    # ------------------------------------------------------------------

    def apply_runtime_settings(
        self,
        wake_threshold: float | None = None,
        conversation_timeout: float | None = None,
        mic_index: int | None = None,
        voice_output_enabled: bool | None = None,
    ) -> HealthSnapshot:
        """Apply safe live settings in memory without overwriting .env or touching secrets."""
        if wake_threshold is not None and 0.0 < wake_threshold <= 1.0:
            settings.WAKE_WORD_THRESHOLD = float(wake_threshold)
            self._wake_detector.threshold = float(wake_threshold)
        if conversation_timeout is not None and conversation_timeout >= 1.0:
            settings.CONVERSATION_TIMEOUT_SECONDS = float(conversation_timeout)
            if self._hands_free is not None:
                self._hands_free.conversation_timeout_seconds = float(conversation_timeout)
        if mic_index != self._mic.device_index:
            was_monitoring = bool(self._hands_free and self._hands_free.is_monitoring)
            if was_monitoring:
                self._hands_free.stop()
            settings.VOICE_MICROPHONE_INDEX = mic_index
            self._mic.device_index = mic_index
            if was_monitoring:
                self._hands_free.start()
        if voice_output_enabled is not None:
            settings.VOICE_OUTPUT_ENABLED = bool(voice_output_enabled)

        snap = self.get_health_snapshot()
        self.health_updated.emit(snap)
        return snap
