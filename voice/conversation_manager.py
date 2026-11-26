"""
Hands-Free Voice Conversation Manager & Wake-Word State Machine.

Coordinates:
  - Continuous local wake-word listening (openWakeWord "Hey JARVIS")
  - Speech endpoint detection (Silero VAD ONNX)
  - Speech-to-Text (Faster-Whisper, reused once)
  - Thread-safe serialized execution with JarvisAgent (Ollama / Qwen 3.5 4B)
  - Text-to-Speech (Piper TTS, pausing wake detection during playback)
  - Multi-turn follow-up conversation window with configurable timeout
"""

from __future__ import annotations

import logging
import re
import threading
import time
from enum import Enum
from typing import Any, Callable

import numpy as np

from config.settings import settings
from core.agent import JarvisAgent
from voice.speech_to_text import FasterWhisperEngine
from voice.text_to_speech import PiperEngine
from voice.voice_controller import AudioState, VoiceController, VoiceMode
from voice.wake_word import (
    MicrophoneCapture,
    OpenWakeWordDetector,
    SileroSpeechEndpointDetector,
    verify_wakeword_model_files,
)

logger = logging.getLogger(__name__)

_GOODBYE_PHRASES = {
    "goodbye jarvis",
    "goodbye",
    "bye jarvis",
    "bye",
    "go to sleep",
    "stand down",
    "stop listening",
    "that's all jarvis",
    "that is all jarvis",
    "thanks jarvis goodbye",
    "thank you jarvis goodbye",
}


class VoicePipelineState(str, Enum):
    """Explicit hands-free wake-word & conversation pipeline states."""
    STARTING = "STARTING"
    IDLE_WAKE_LISTENING = "IDLE_WAKE_LISTENING"
    WAKE_DETECTED = "WAKE_DETECTED"
    AWAITING_COMMAND = "AWAITING_COMMAND"
    CAPTURING_COMMAND = "CAPTURING_COMMAND"
    TRANSCRIBING = "TRANSCRIBING"
    PROCESSING_WITH_QWEN = "PROCESSING_WITH_QWEN"
    SPEAKING_WITH_PIPER = "SPEAKING_WITH_PIPER"
    CONVERSATION_ACTIVE = "CONVERSATION_ACTIVE"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class HandsFreeConversationManager:
    """
    Manages hands-free Alexa/Siri-style voice interaction around the existing
    JarvisAgent, VoiceController, FasterWhisperEngine, and PiperEngine.
    """

    def __init__(
        self,
        agent: JarvisAgent,
        voice_controller: VoiceController,
        agent_lock: threading.RLock | None = None,
        wake_detector: OpenWakeWordDetector | None = None,
        mic_capture: MicrophoneCapture | None = None,
        vad_detector: SileroSpeechEndpointDetector | None = None,
        conversation_timeout_seconds: float | None = None,
        on_output: Callable[[str], None] | None = None,
        on_state_change: Callable[[VoicePipelineState], None] | None = None,
    ) -> None:
        self._agent = agent
        self._voice = voice_controller
        self._agent_lock = agent_lock or threading.RLock()

        self._wake_detector = wake_detector or OpenWakeWordDetector()
        self._mic = mic_capture or MicrophoneCapture()
        self._vad = vad_detector or SileroSpeechEndpointDetector()

        self.conversation_timeout_seconds = float(
            conversation_timeout_seconds
            if conversation_timeout_seconds is not None
            else settings.CONVERSATION_TIMEOUT_SECONDS
        )
        self._on_output = on_output or print
        self._on_state_change = on_state_change

        self._state = VoicePipelineState.DISABLED
        self._state_lock = threading.Lock()
        self._turn_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._manual_wake_event = threading.Event()
        self._speaking_active = threading.Event()
        self._worker_thread: threading.Thread | None = None

        self.last_error: str = ""
        self.wake_detection_ready: bool = False

    # ------------------------------------------------------------------
    #  Properties & State Transitions
    # ------------------------------------------------------------------

    @property
    def state(self) -> VoicePipelineState:
        return self._state

    @property
    def is_monitoring(self) -> bool:
        return (
            not self._stop_event.is_set()
            and self._worker_thread is not None
            and self._worker_thread.is_alive()
            and self._mic.is_active
        )

    def _set_state(self, new_state: VoicePipelineState) -> None:
        with self._state_lock:
            if self._state == new_state:
                return
            prev = self._state
            self._state = new_state
        logger.info("Voice pipeline state: %s -> %s", prev.value, new_state.value)
        if self._on_state_change:
            try:
                self._on_state_change(new_state)
            except Exception as e:
                logger.error("Pipeline state callback error: %s", e)

    def _emit(self, message: str) -> None:
        try:
            self._on_output(message)
        except Exception:
            pass

    # ------------------------------------------------------------------
    #  Startup, Enable & Disable (/voice on, /voice off)
    # ------------------------------------------------------------------

    def check_readiness(self) -> tuple[bool, str]:
        """
        Verify wake-word package, local model files, and microphone hardware
        without opening competing streams or downloading anything.
        """
        if not settings.VOICE_ENABLED or not settings.VOICE_INPUT_ENABLED:
            return False, "Voice input disabled by configuration (VOICE_INPUT_ENABLED=false)."
        if not settings.WAKE_WORD_ENABLED:
            return False, "Wake-word detection disabled by configuration (WAKE_WORD_ENABLED=false)."
        if not self._wake_detector.package_installed():
            return False, "openwakeword/onnxruntime package is not installed."
        ok_files, _, missing = verify_wakeword_model_files(
            self._wake_detector.model_dir, self._wake_detector.phrase
        )
        if not ok_files:
            return (
                False,
                f"Wake-word model files missing in '{self._wake_detector.model_dir}': {', '.join(missing)}. "
                "Run 'python setup_local_models.py' first.",
            )
        ok_mic, mic_detail = self._mic.check_device_available()
        if not ok_mic:
            return False, mic_detail
        return True, f"Ready (mic: {mic_detail})"

    def start(self) -> bool:
        """
        Start continuous local wake-word monitoring in a background thread.
        Returns True only if model load and single microphone stream start succeed.
        """
        if self.is_monitoring:
            return True

        self._set_state(VoicePipelineState.STARTING)
        ready, detail = self.check_readiness()
        if not ready:
            self.last_error = detail
            self.wake_detection_ready = False
            if "disabled by configuration" in detail.lower():
                self._set_state(VoicePipelineState.DISABLED)
            else:
                self._set_state(VoicePipelineState.ERROR)
            logger.warning("Hands-free wake listener not started: %s", detail)
            return False

        try:
            self._wake_detector.load()
            self._wake_detector.reset()
        except Exception as e:
            self.last_error = f"Wake-word model load failed: {e}"
            self.wake_detection_ready = False
            self._set_state(VoicePipelineState.ERROR)
            logger.error(self.last_error)
            return False

        if not self._mic.start():
            self.last_error = self._mic.last_error or "Failed to open microphone stream."
            self.wake_detection_ready = False
            self._set_state(VoicePipelineState.ERROR)
            return False

        self.last_error = ""
        self.wake_detection_ready = True
        self._stop_event.clear()
        self._manual_wake_event.clear()
        self._voice.set_mode(VoiceMode.CONTINUOUS)

        self._worker_thread = threading.Thread(
            target=self._run_loop,
            name="jarvis-wakeword-listener",
            daemon=True,
        )
        self._worker_thread.start()
        return True

    def stop(self) -> None:
        """
        Immediately stop wake-word monitoring and close microphone access (/voice off).
        """
        self._stop_event.set()
        self._voice.stop_speaking()
        self._mic.stop()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            if threading.current_thread() is not self._worker_thread:
                self._worker_thread.join(timeout=2.0)
        self._worker_thread = None
        self.wake_detection_ready = False
        self._set_state(VoicePipelineState.DISABLED)
        logger.info("Hands-free voice listener stopped; microphone closed.")

    # ------------------------------------------------------------------
    #  Main Background Loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        self._set_state(VoicePipelineState.IDLE_WAKE_LISTENING)

        while not self._stop_event.is_set():
            if not self._mic.is_active:
                self.last_error = self._mic.last_error or "Microphone stream became inactive."
                self.wake_detection_ready = False
                self._set_state(VoicePipelineState.ERROR)
                self._emit(f"\n[JARVIS] ⚠️ {self.last_error} Text mode remains active.")
                break

            # Allow manual /voice PTT trigger to share the active stream cleanly
            if self._manual_wake_event.is_set():
                self._manual_wake_event.clear()
                self._handle_conversation_session(triggered_by_wake=False)
                if not self._stop_event.is_set() and self._mic.is_active:
                    self._wake_detector.reset()
                    self._mic.drain()
                    self._set_state(VoicePipelineState.IDLE_WAKE_LISTENING)
                continue

            frame = self._mic.read_frame(timeout=0.1)
            if frame is None:
                continue

            # Ignore microphone frames while Piper is speaking aloud from CLI/voice
            if self._speaking_active.is_set():
                continue

            try:
                triggered, _ = self._wake_detector.process_pcm(frame)
            except Exception as e:
                self.last_error = f"Wake-word scoring error: {e}"
                logger.error(self.last_error)
                self._set_state(VoicePipelineState.ERROR)
                break

            if triggered and not self._stop_event.is_set():
                self._handle_conversation_session(triggered_by_wake=True)
                if not self._stop_event.is_set() and self._mic.is_active:
                    self._wake_detector.reset()
                    self._mic.drain()
                    self._set_state(VoicePipelineState.IDLE_WAKE_LISTENING)

    # ------------------------------------------------------------------
    #  Wake Activation + Follow-Up Conversation Continuity
    # ------------------------------------------------------------------

    def _speak_safe(self, text: str) -> bool:
        """
        Speak via Piper while pausing wake-word detection and draining any speaker
        bleed from the microphone queue immediately afterward.
        """
        if not text or not settings.VOICE_OUTPUT_ENABLED:
            return True
        self._speaking_active.set()
        try:
            self._set_state(VoicePipelineState.SPEAKING_WITH_PIPER)
            ok = self._voice.speak_response(text)
            # Small settle window so trailing speaker echo enters queue and gets drained
            time.sleep(0.15)
            self._mic.drain()
            self._wake_detector.reset()
            return ok
        finally:
            self._speaking_active.clear()

    @staticmethod
    def _is_goodbye(transcript: str) -> bool:
        cleaned = re.sub(r"[^\w\s']", "", transcript.lower()).strip()
        return cleaned in _GOODBYE_PHRASES or cleaned.startswith("goodbye jarvis")

    def _handle_conversation_session(self, triggered_by_wake: bool = True) -> None:
        with self._turn_lock:
            if triggered_by_wake:
                self._set_state(VoicePipelineState.WAKE_DETECTED)
                self._emit("\n[WAKE] Hey JARVIS detected.")
                self._emit("[JARVIS] Yes, I'm listening.")
                self._speak_safe("Yes, I'm listening.")
                if self._stop_event.is_set():
                    return

            self._set_state(VoicePipelineState.AWAITING_COMMAND)
            await_timeout = min(10.0, self.conversation_timeout_seconds)
            first_turn = True

            while not self._stop_event.is_set():
                if self._agent.is_emergency_stopped:
                    self._emit("[JARVIS] 🛑 Emergency stop active. Returning to idle.")
                    break

                timeout_s = await_timeout if first_turn else self.conversation_timeout_seconds
                first_turn = False

                self._set_state(VoicePipelineState.CAPTURING_COMMAND)
                audio_f32 = self._vad.capture_utterance(
                    read_chunk_fn=self._mic.read_frame,
                    await_speech_timeout=timeout_s,
                    cancel_event=self._stop_event,
                )

                if self._stop_event.is_set():
                    break

                if audio_f32 is None:
                    # Either initial silence timeout or conversation window expired
                    self._emit("[JARVIS] Conversation timed out. Listening for 'Hey JARVIS'.")
                    break

                keep_active = self.process_captured_audio(audio_f32)
                if not keep_active or self._stop_event.is_set():
                    break

                self._set_state(VoicePipelineState.CONVERSATION_ACTIVE)

    def process_captured_audio(self, audio_f32: np.ndarray) -> bool:
        """
        Transcribe a captured command utterance, route through JarvisAgent under
        the shared agent lock, speak the reply via Piper, and return True if the
        conversation should remain active (False on goodbye/exit).
        """
        self._set_state(VoicePipelineState.TRANSCRIBING)
        try:
            stt = self._voice._stt
            if isinstance(stt, FasterWhisperEngine):
                transcript, _ = stt.transcribe_audio(audio_f32, language=None)
            else:
                transcript = stt.listen_and_transcribe()
        except Exception as e:
            logger.error("Hands-free transcription error: %s", e)
            self._emit(f"[JARVIS] ⚠️ Transcription error: {e}")
            return True

        if not transcript or not transcript.strip():
            return True

        self._emit(f"\n[VOICE] Recognized: {transcript}")

        if self._is_goodbye(transcript):
            goodbye_reply = "Certainly. I'll be here when you need me."
            self._emit(f"Jarvis: {goodbye_reply}")
            self._speak_safe(goodbye_reply)
            return False

        # Handle meta voice controls ("stop speaking", "what can you do", etc.)
        is_meta, meta_reply = self._voice._handle_voice_command(transcript)
        if is_meta:
            self._emit(f"Jarvis: {meta_reply}")
            if self._voice.mode == VoiceMode.TEXT:
                self._speak_safe(meta_reply)
                return False
            self._speak_safe(meta_reply)
            return True

        self._emit("[JARVIS] Processing...")
        self._set_state(VoicePipelineState.PROCESSING_WITH_QWEN)

        with self._agent_lock:
            reply = self._agent.process_message(transcript)

        self._emit(f"\nJarvis: {reply}\n")
        self._speak_safe(reply)
        return True

    # ------------------------------------------------------------------
    #  Manual PTT & Diagnostics (/voice, /voice status, /voice test)
    # ------------------------------------------------------------------

    def trigger_push_to_talk(self) -> str:
        """
        Execute a single push-to-talk command without opening a competing mic stream.
        If hands-free listener is active, captures on the active stream directly.
        """
        if self.is_monitoring:
            with self._turn_lock:
                self._set_state(VoicePipelineState.CAPTURING_COMMAND)
                self._mic.drain()
                audio_f32 = self._vad.capture_utterance(
                    read_chunk_fn=self._mic.read_frame,
                    await_speech_timeout=8.0,
                    cancel_event=self._stop_event,
                )
                if audio_f32 is None:
                    self._set_state(VoicePipelineState.IDLE_WAKE_LISTENING)
                    return ""
                self.process_captured_audio(audio_f32)
                self._wake_detector.reset()
                self._mic.drain()
                self._set_state(VoicePipelineState.IDLE_WAKE_LISTENING)
                return self._voice._last_response or ""

        # Mic stream is currently stopped (/voice off): use VoiceController directly under agent_lock
        with self._agent_lock:
            prev_mode = self._voice.mode
            if prev_mode == VoiceMode.TEXT:
                self._voice.set_mode(VoiceMode.PUSH_TO_TALK)
            return self._voice.listen_and_process()

    def get_status(self) -> dict[str, Any]:
        """Return real runtime diagnostics for /voice status and startup banner."""
        voice_diag = self._voice.get_diagnostics()
        return {
            "pipeline_state": self._state.value,
            "wake_word_phrase": self._wake_detector.phrase,
            "wake_word_engine": settings.WAKE_WORD_ENGINE,
            "wake_word_available": self._wake_detector.is_available(),
            "wake_detection_enabled": self.wake_detection_ready and self.is_monitoring,
            "mic_monitoring": self.is_monitoring,
            "mic_device": self._mic.selected_device_name or "default",
            "stt_engine": voice_diag.get("stt_engine"),
            "stt_available": voice_diag.get("stt_available", False),
            "tts_engine": voice_diag.get("tts_engine"),
            "tts_available": voice_diag.get("tts_available", False),
            "conversation_timeout_seconds": self.conversation_timeout_seconds,
            "last_error": self.last_error,
        }

    def run_self_test(self) -> dict[str, Any]:
        """
        Test microphone capture, openWakeWord ONNX model, Faster-Whisper STT,
        and Piper TTS playback (/voice test).
        """
        results: dict[str, Any] = {}

        # 1. Microphone check (+ 0.3s sample test)
        was_running = self.is_monitoring
        if was_running:
            frame = self._mic.read_frame(timeout=0.5)
            results["microphone"] = {
                "ok": frame is not None,
                "device": self._mic.selected_device_name or "default",
                "samples": int(len(frame)) if frame is not None else 0,
            }
        else:
            ok_mic, detail = self._mic.check_device_available()
            started = self._mic.start() if ok_mic else False
            frame = self._mic.read_frame(timeout=0.6) if started else None
            if started:
                self._mic.stop()
            results["microphone"] = {
                "ok": bool(started and frame is not None),
                "device": detail,
                "samples": int(len(frame)) if frame is not None else 0,
            }

        # 2. Wake-word model test
        try:
            self._wake_detector.load()
            silence = np.zeros(1280, dtype=np.int16)
            _, score = self._wake_detector.process_pcm(silence)
            self._wake_detector.reset()
            results["wake_word"] = {
                "ok": True,
                "phrase": self._wake_detector.phrase,
                "silence_score": round(float(score), 6),
            }
        except Exception as e:
            results["wake_word"] = {"ok": False, "error": str(e)}

        # 3. Faster-Whisper STT test
        stt = self._voice._stt
        try:
            stt_ok = stt.is_available()
            if stt_ok and isinstance(stt, FasterWhisperEngine):
                stt._get_model()
            results["stt"] = {"ok": stt_ok, "engine": type(stt).__name__}
        except Exception as e:
            results["stt"] = {"ok": False, "engine": type(stt).__name__, "error": str(e)}

        # 4. Piper TTS test
        tts = self._voice._tts
        try:
            tts_ok = tts.is_available()
            spoke = self._speak_safe("Voice subsystems operational.") if tts_ok else False
            results["tts"] = {
                "ok": bool(tts_ok and spoke),
                "engine": type(tts).__name__,
                "error": getattr(tts, "last_error", ""),
            }
        except Exception as e:
            results["tts"] = {"ok": False, "engine": type(tts).__name__, "error": str(e)}

        return results
