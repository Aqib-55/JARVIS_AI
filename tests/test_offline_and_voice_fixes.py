"""
Tests for Piper TTS validation, voice state lifecycle, offline diagnostics
in system instructions, and end-to-end offline enforcement:
- Issue 1: Piper model discovery/validation (.onnx + .onnx.json) and real WAV synthesis
- Issue 2: Runtime diagnostics & truthfulness rules in system instruction
- Issue 3: AudioState.SPEAKING only after audio generation succeeds; no duplicate Ready;
           'Speech output unavailable' callback when Piper fails; text response preserved
- Issue 4: No Gemini / cloud STT / cloud TTS fallback; behavior when external internet is blocked
"""

import io
import socket
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import Settings, settings
from core.agent import JarvisAgent
from providers.base import ModelResponse
from providers.factory import get_provider
from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolResult
from tools.registry import ToolRegistry
from voice.speech_to_text import (
    FasterWhisperEngine,
    MockSTTEngine,
    get_stt_engine,
)
from voice.text_to_speech import (
    MockTTSEngine,
    PiperEngine,
    get_tts_engine,
    verify_piper_model_files,
)
from voice.voice_controller import AudioState, VoiceController, VoiceMode


class CapturingProvider:
    """Mock BaseProvider capturing the system_instruction sent to the LLM."""

    def __init__(self, reply: str = "Local response.") -> None:
        self.reply = reply
        self.last_system_instruction: str | None = None

    def connect(self) -> bool:
        return True

    def generate(self, messages, system_instruction=None) -> ModelResponse:
        self.last_system_instruction = system_instruction
        return ModelResponse(text=self.reply)

    def generate_with_tools(self, messages, tool_declarations, system_instruction=None) -> ModelResponse:
        self.last_system_instruction = system_instruction
        return ModelResponse(text=self.reply)

    def send_function_results(self, messages, function_calls, function_responses, tool_declarations, system_instruction=None) -> ModelResponse:
        self.last_system_instruction = system_instruction
        return ModelResponse(text=self.reply)

    def get_provider_name(self) -> str:
        return "ollama"

    def get_model_name(self) -> str:
        return "qwen3.5:4b"


class TestPiperModelValidationAndSynthesis:

    def test_verify_missing_piper_files(self, tmp_path):
        ok, onnx_path, issues = verify_piper_model_files(tmp_path, "en_GB-alan-medium")
        assert ok is False
        assert onnx_path is None
        assert any("en_GB-alan-medium.onnx" in i for i in issues)
        assert any("en_GB-alan-medium.onnx.json" in i for i in issues)

    def test_verify_missing_json_config_only(self, tmp_path):
        (tmp_path / "en_GB-alan-medium.onnx").write_bytes(b"onnx")
        ok, onnx_path, issues = verify_piper_model_files(tmp_path, "en_GB-alan-medium")
        assert ok is False
        assert onnx_path is None
        assert issues == ["en_GB-alan-medium.onnx.json"]

    def test_missing_piper_model_does_not_download_at_runtime(self, tmp_path, monkeypatch):
        def block_download(*args, **kwargs):
            raise AssertionError("Automatic runtime download must not happen!")

        monkeypatch.setattr("urllib.request.urlretrieve", block_download)

        engine = PiperEngine(voice="en_GB-alan-medium", model_path=tmp_path)
        assert engine.is_available() is False
        assert engine.speak("Hello Jarvis") is False
        assert "setup_local_models.py" in engine.last_error
        assert "en_GB-alan-medium.onnx" in engine.last_error

    def test_real_piper_model_files_and_wav_generation(self, tmp_path):
        ok, onnx_path, issues = verify_piper_model_files(
            settings.PIPER_MODEL_PATH, settings.PIPER_VOICE
        )
        assert ok, f"Piper voice missing in {settings.PIPER_MODEL_PATH}: {issues}"
        assert onnx_path is not None

        engine = get_tts_engine("piper")
        assert isinstance(engine, PiperEngine)
        assert engine.is_available() is True

        wav_out = tmp_path / "piper_test.wav"
        engine.synthesize_to_wav("Systems check complete.", wav_out)
        assert wav_out.is_file()
        with wave.open(str(wav_out), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getframerate() > 0
            assert w.getnframes() > 0

    def test_real_piper_speak_triggers_playback_start_and_plays(self, monkeypatch):
        engine = get_tts_engine("piper")
        events: list[str] = []

        with patch.object(PiperEngine, "_play_wav", return_value=True) as mock_play:
            ok = engine.speak(
                "Offline voice check.",
                on_playback_start=lambda: events.append("SPEAKING"),
            )

        assert ok is True
        assert events == ["SPEAKING"]
        assert engine.last_error == ""
        mock_play.assert_called_once()


class TestVoiceStateLifecycle:

    def test_missing_piper_never_emits_speaking_or_duplicate_ready(self, db, tmp_path):
        provider = CapturingProvider("Here is your text answer.")
        registry = ToolRegistry()
        agent = JarvisAgent(provider=provider, registry=registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["What is my status?"])
        tts = PiperEngine(voice="en_GB-alan-medium", model_path=tmp_path)

        states: list[AudioState] = []
        unavailable_reasons: list[str] = []

        controller = VoiceController(
            agent=agent,
            stt_engine=stt,
            tts_engine=tts,
            mode=VoiceMode.PUSH_TO_TALK,
            on_state_change=states.append,
            on_speech_unavailable=unavailable_reasons.append,
        )

        reply = controller.listen_and_process()

        # Text response is preserved even when voice output fails
        assert reply == "Here is your text answer."
        # Speaking state must NEVER be emitted when Piper fails
        assert AudioState.SPEAKING not in states
        # Ready (IDLE) must be emitted once, never twice in a row
        assert states.count(AudioState.IDLE) == 1
        assert states[-1] == AudioState.IDLE
        # Unavailable notification must be emitted
        assert len(unavailable_reasons) == 1
        assert "en_GB-alan-medium" in unavailable_reasons[0]

    def test_successful_voice_turn_emits_ready_once(self, db):
        provider = CapturingProvider("Hello Sir.")
        registry = ToolRegistry()
        agent = JarvisAgent(provider=provider, registry=registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["Hello"])
        tts = MockTTSEngine()
        states: list[AudioState] = []

        controller = VoiceController(
            agent=agent,
            stt_engine=stt,
            tts_engine=tts,
            mode=VoiceMode.PUSH_TO_TALK,
            on_state_change=states.append,
        )

        reply = controller.listen_and_process()
        assert reply == "Hello Sir."
        assert states == [
            AudioState.LISTENING,
            AudioState.PROCESSING,
            AudioState.SPEAKING,
            AudioState.IDLE,
        ]
        assert states.count(AudioState.IDLE) == 1

    def test_playback_failure_does_not_claim_success(self, db):
        provider = CapturingProvider("Text stays visible.")
        registry = ToolRegistry()
        agent = JarvisAgent(provider=provider, registry=registry, db=db)
        agent.initialize()

        tts = get_tts_engine("piper")
        unavailable: list[str] = []
        controller = VoiceController(
            agent=agent,
            stt_engine=MockSTTEngine(),
            tts_engine=tts,
            on_speech_unavailable=unavailable.append,
        )

        with patch.object(PiperEngine, "_play_wav", return_value=False):
            ok = controller.speak_response("Test audio failure.")

        assert ok is False
        assert len(unavailable) == 1


class TestOfflinePromptAndNoCloudFallback:

    def test_system_instruction_includes_live_offline_diagnostics(self, db):
        provider = CapturingProvider("Running locally on Ollama.")
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="open_website",
                description="Open website",
                parameters=[],
                permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
                category=ToolCategory.SYSTEM_AUTOMATION,
            ),
            lambda: ToolResult(success=True, result={}),
        )
        agent = JarvisAgent(provider=provider, registry=registry, db=db)
        agent.initialize()
        agent.set_voice_diagnostics_provider(
            lambda: {
                "mode": "push_to_talk",
                "stt_engine": "FasterWhisperEngine",
                "stt_available": True,
                "tts_engine": "PiperEngine",
                "tts_available": True,
            }
        )

        agent.process_message("Are you offline or cloud-connected?")
        sys_prompt = provider.last_system_instruction or ""

        assert "ollama" in sys_prompt.lower()
        assert "qwen3.5:4b" in sys_prompt.lower()
        assert "faster-whisper" in sys_prompt.lower()
        assert "piper" in sys_prompt.lower()
        assert "open_website" in sys_prompt
        assert "[Runtime System Diagnostics]" in sys_prompt
        assert "stt_available" not in sys_prompt  # formatted cleanly
        assert "available: True" in sys_prompt

    def test_no_gemini_or_cloud_stt_tts_fallback(self):
        with pytest.raises(RuntimeError, match="LOCAL_AI_ONLY"):
            get_provider("gemini")
        with pytest.raises(RuntimeError, match="LOCAL_AI_ONLY"):
            get_stt_engine("speech_recognition")
        with pytest.raises(RuntimeError, match="LOCAL_AI_ONLY"):
            get_tts_engine("edge_tts")
        with pytest.raises(RuntimeError, match="LOCAL_AI_ONLY"):
            get_tts_engine("pyttsx3")
        assert "google.genai" not in sys.modules
        assert "providers.gemini" not in sys.modules

    def test_external_internet_blocked_still_allows_local_voice_stack(self, monkeypatch, tmp_path):
        real_create_conn = socket.create_connection

        def block_external_net(address, *args, **kwargs):
            host = address[0]
            if host not in ("127.0.0.1", "localhost", "::1"):
                raise OSError(f"External network blocked in test: {host}")
            return real_create_conn(address, *args, **kwargs)

        monkeypatch.setattr(socket, "create_connection", block_external_net)

        # Piper local synthesis works with external network blocked
        tts = get_tts_engine("piper")
        wav_path = tmp_path / "offline.wav"
        tts.synthesize_to_wav("Offline test successful.", wav_path)
        assert wav_path.is_file() and wav_path.stat().st_size > 44

        # Faster-Whisper local load + transcription works with external network blocked
        stt = get_stt_engine("faster_whisper")
        text, lang = stt.transcribe_audio(wav_path, language="en")
        assert len(text) > 0
        assert lang == "en"
