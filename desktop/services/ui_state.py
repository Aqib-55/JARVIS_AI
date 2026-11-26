"""Shared UI state enums and lightweight immutable DTOs for the desktop frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class VoiceState(str, Enum):
    """GUI-facing voice & assistant state."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    WAKE_DETECTED = "WAKE_DETECTED"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


VOICE_STATE_CAPTIONS: dict[VoiceState, str] = {
    VoiceState.IDLE: 'SAY "HEY JARVIS"',
    VoiceState.LISTENING: "LISTENING FOR YOUR COMMAND",
    VoiceState.WAKE_DETECTED: "HEY JARVIS DETECTED",
    VoiceState.TRANSCRIBING: "TRANSCRIBING SPEECH",
    VoiceState.THINKING: "JARVIS IS THINKING",
    VoiceState.EXECUTING_TOOL: "EXECUTING APPROVED TOOL",
    VoiceState.SPEAKING: "JARVIS IS SPEAKING",
    VoiceState.ERROR: "AUDIO / BACKEND ATTENTION NEEDED",
}


@dataclass(frozen=True)
class HealthSnapshot:
    """Actual backend subsystem health snapshot."""
    ai_connected: bool
    ai_provider: str
    ai_model: str
    local_ai_only: bool
    ollama_url: str
    stt_engine: str
    stt_available: bool
    whisper_model: str
    tts_engine: str
    tts_available: bool
    piper_voice: str
    wake_word_phrase: str
    wake_word_available: bool
    wake_detection_active: bool
    mic_monitoring: bool
    mic_device: str
    memory_enabled: bool
    tools_count: int
    emergency_stopped: bool
    conversation_timeout_seconds: float
    last_error: str = ""


@dataclass
class ToolApprovalRequest:
    """Represents a pending Level 2/3 tool approval from TaskExecutor."""
    tool_name: str
    arguments: dict[str, Any]
    risk_level: str
    reason: str
    description: str = ""


@dataclass
class ChatMessageItem:
    """Display model for a chat timeline entry."""
    role: str  # "user" | "assistant" | "tool" | "error"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    tool_status: str = ""
