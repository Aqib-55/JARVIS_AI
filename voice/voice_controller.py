"""
Voice Controller for JARVIS AI.

Coordinates the complete voice pipeline:
Microphone Input -> STT -> Voice Commands / JarvisAgent -> Response Synthesis -> TTS
Manages AudioState transitions, Push-to-Talk and Continuous modes,
and clean fallback to text mode upon hardware errors.
"""

import logging
import threading
from enum import Enum
from typing import Any, Callable

from core.agent import JarvisAgent
from voice.speech_to_text import BaseSTTEngine, get_stt_engine
from voice.text_to_speech import BaseTTSEngine, get_tts_engine

logger = logging.getLogger(__name__)


class AudioState(str, Enum):
    """Current audio subsystem operational state."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    ERROR = "error"


class VoiceMode(str, Enum):
    """Operational mode for JARVIS interaction."""
    TEXT = "text"
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"


class VoiceController:
    """
    Orchestrates speech input, voice commands, agent execution,
    and voice output without duplicating core agent logic.
    """

    def __init__(
        self,
        agent: JarvisAgent,
        stt_engine: BaseSTTEngine | None = None,
        tts_engine: BaseTTSEngine | None = None,
        mode: VoiceMode = VoiceMode.PUSH_TO_TALK,
        on_state_change: Callable[[AudioState], None] | None = None,
        on_transcription: Callable[[str], None] | None = None,
    ) -> None:
        self._agent = agent
        self._stt = stt_engine or get_stt_engine()
        self._tts = tts_engine or get_tts_engine()
        self._mode = mode
        self._state = AudioState.IDLE

        self._on_state_change = on_state_change
        self._on_transcription = on_transcription

        self._stop_listening_event = threading.Event()
        self._interrupt_speech_event = threading.Event()
        self._last_response: str = ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    #  State & Mode Management
    # ------------------------------------------------------------------

    @property
    def state(self) -> AudioState:
        return self._state

    @property
    def mode(self) -> VoiceMode:
        return self._mode

    def set_mode(self, mode: VoiceMode) -> None:
        """Switch conversation mode."""
        self._mode = mode
        logger.info("VoiceController mode changed to: %s", mode.value)

    def _set_state(self, state: AudioState) -> None:
        """Internal helper to update state and trigger notification callback."""
        self._state = state
        logger.debug("VoiceController state: %s", state.value)
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception as e:
                logger.error("State change callback error: %s", e)

    # ------------------------------------------------------------------
    #  Voice Command Interception
    # ------------------------------------------------------------------

    def _handle_voice_command(self, text: str) -> tuple[bool, str]:
        """
        Check if the recognized text is a meta voice control command.
        Returns: (is_handled, response_message)
        """
        clean = text.lower().strip().strip(".?!")

        # Strip wake-prefix if present
        if clean.startswith("jarvis "):
            clean = clean[7:].strip()
        elif clean.startswith("jarvis,"):
            clean = clean[7:].strip()

        if clean in ("stop speaking", "be quiet", "shut up", "silence"):
            self.stop_speaking()
            return True, "Stopped speaking."

        if clean in ("stop listening", "go to sleep", "stand down"):
            self._stop_listening_event.set()
            self._set_state(AudioState.IDLE)
            return True, "Continuous listening stopped."

        if clean in ("start listening", "wake up"):
            self.set_mode(VoiceMode.CONTINUOUS)
            return True, "Continuous voice mode activated."

        if clean in ("switch to text mode", "text mode"):
            self.set_mode(VoiceMode.TEXT)
            return True, "Switched to text mode."

        if clean in ("switch to voice mode", "voice mode"):
            self.set_mode(VoiceMode.PUSH_TO_TALK)
            return True, "Switched to voice mode."

        if clean in ("repeat that", "what did you say", "repeat"):
            if self._last_response:
                return True, self._last_response
            return True, "I haven't said anything yet."

        if clean in ("what can you do", "help", "list capabilities"):
            overview = (
                "I can manage files and folders, monitor system CPU and RAM, "
                "manage notes and reminders, evaluate calculations, write Python code, "
                "and execute approved computer tasks."
            )
            return True, overview

        return False, ""

    # ------------------------------------------------------------------
    #  Execution Cycle (Push-to-Talk)
    # ------------------------------------------------------------------

    def listen_and_process(self, timeout: float = 6.0) -> str:
        """
        Execute a single push-to-talk voice turn:
        Listen -> Transcribe -> Process via Agent -> Speak response.
        """
        if self._mode == VoiceMode.TEXT:
            return ""

        self._interrupt_speech_event.clear()
        self._set_state(AudioState.LISTENING)

        # 1. Speech Recognition
        try:
            transcription = self._stt.listen_and_transcribe(
                timeout=timeout,
                cancel_event=self._stop_listening_event,
            )
        except Exception as e:
            logger.error("Microphone listening error: %s", e)
            self._set_state(AudioState.ERROR)
            return f"Microphone error: {e}"

        if not transcription:
            self._set_state(AudioState.IDLE)
            return ""

        logger.info("Recognized voice input: '%s'", transcription)
        if self._on_transcription:
            self._on_transcription(transcription)

        # 2. Check Meta Voice Commands
        is_cmd, cmd_resp = self._handle_voice_command(transcription)
        if is_cmd:
            self.speak_response(cmd_resp)
            self._set_state(AudioState.IDLE)
            return cmd_resp

        # 3. Process via Agent
        self._set_state(AudioState.PROCESSING)
        try:
            agent_response = self._agent.process_message(transcription)
            self._last_response = agent_response
        except Exception as e:
            logger.error("Agent execution error from voice: %s", e)
            self._set_state(AudioState.ERROR)
            agent_response = f"An error occurred while executing your request: {e}"

        # 4. Spoken Output
        self.speak_response(agent_response)
        self._set_state(AudioState.IDLE)
        return agent_response

    # ------------------------------------------------------------------
    #  Continuous Conversation Mode
    # ------------------------------------------------------------------

    def run_continuous_listening(
        self,
        max_silence_cycles: int = 5,
        on_turn_complete: Callable[[str, str], None] | None = None,
    ) -> None:
        """
        Continuously listen for consecutive user questions until interrupted
        or explicit stop command is given.
        """
        self.set_mode(VoiceMode.CONTINUOUS)
        self._stop_listening_event.clear()
        consecutive_silence = 0

        logger.info("Starting continuous voice interaction loop.")

        while not self._stop_listening_event.is_set():
            if self._agent.is_emergency_stopped:
                logger.warning("Emergency stop triggered. Halting continuous voice mode.")
                self.speak_response("Emergency stop active. Voice mode halted.")
                break

            response = self.listen_and_process(timeout=5.0)

            if response:
                consecutive_silence = 0
                if on_turn_complete:
                    on_turn_complete("voice_input", response)
            else:
                consecutive_silence += 1
                if consecutive_silence >= max_silence_cycles:
                    logger.info("Exiting continuous listening due to prolonged silence.")
                    break

        self._set_state(AudioState.IDLE)

    # ------------------------------------------------------------------
    #  Voice Playback & Interruption
    # ------------------------------------------------------------------

    def speak_response(self, text: str) -> bool:
        """
        Convert text response to speech safely.
        """
        if not text:
            return True

        self._set_state(AudioState.SPEAKING)
        success = self._tts.speak(text, interrupt_event=self._interrupt_speech_event)
        self._set_state(AudioState.IDLE)
        return success

    def stop_speaking(self) -> None:
        """Interrupt active TTS playback immediately."""
        self._interrupt_speech_event.set()
        self._tts.stop()
        self._set_state(AudioState.IDLE)
        logger.info("Voice output halted by user request.")

    def cancel_listening(self) -> None:
        """Cancel active microphone recording."""
        self._stop_listening_event.set()
        self._set_state(AudioState.IDLE)
        logger.info("Voice listening cancelled.")

    # ------------------------------------------------------------------
    #  Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> dict[str, Any]:
        """Check availability and status of audio subsystems."""
        return {
            "mode": self._mode.value,
            "state": self._state.value,
            "stt_available": self._stt.is_available(),
            "tts_available": self._tts.is_available(),
            "stt_engine": type(self._stt).__name__,
            "tts_engine": type(self._tts).__name__,
        }
