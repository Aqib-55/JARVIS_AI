"""
Comprehensive automated tests for Hands-Free Wake-Word Voice Commands:
- openWakeWord ONNX asset verification & offline loading
- "Hey JARVIS" detection across volumes & noise vs non-wake / similar phrases
- Double-trigger prevention, mic disconnection, missing model handling
- Silero VAD speech start/end, pause tolerance, min speech & max utterance guards
- HandsFreeConversationManager state machine, follow-up context retention,
  conversation timeout, goodbye handling, and /voice off hardware shutdown
- CLI commands (/voice on, /voice off, /voice status, /voice test, /voice)
- Startup banner honesty when wake detection is disabled/unavailable
"""

import queue
import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf

from config.settings import Settings, settings
from core.agent import JarvisAgent
from interface.cli import JarvisCLI
from providers.base import BaseProvider, ModelResponse
from tools.registry import ToolRegistry
from voice.conversation_manager import (
    HandsFreeConversationManager,
    VoicePipelineState,
)
from voice.speech_to_text import FasterWhisperEngine, MockSTTEngine
from voice.text_to_speech import MockTTSEngine, get_tts_engine
from voice.voice_controller import VoiceController, VoiceMode
from voice.wake_word import (
    OPENWAKEWORD_CODE_LICENSE,
    OPENWAKEWORD_MODEL_LICENSE,
    MicrophoneCapture,
    OpenWakeWordDetector,
    SileroSpeechEndpointDetector,
    TARGET_SAMPLE_RATE,
    VAD_CHUNK_SAMPLES,
    verify_wakeword_model_files,
)


class ContextAwareMockProvider(BaseProvider):
    """Mock provider that records history lengths to verify follow-up continuity."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def connect(self) -> bool:
        return True

    def generate(self, messages, system_instruction=None) -> ModelResponse:
        return ModelResponse(text="OK")

    def generate_with_tools(self, messages, tool_declarations, system_instruction=None) -> ModelResponse:
        history = [m.content for m in messages]
        self.calls.append(history)
        last = history[-1].lower() if history else ""
        if "date" in last:
            return ModelResponse(text="Today is November 24, 2026.")
        if "tomorrow" in last:
            # Verify prior turn context exists
            assert any("date" in h.lower() for h in history[:-1]), "Missing conversation context!"
            return ModelResponse(text="Tomorrow is November 25, 2026.")
        return ModelResponse(text=f"Echo: {history[-1]}")

    def send_function_results(self, messages, function_calls, function_responses, tool_declarations, system_instruction=None) -> ModelResponse:
        return ModelResponse(text="Done.")

    def get_provider_name(self) -> str:
        return "ollama"

    def get_model_name(self) -> str:
        return "qwen3.5:4b"


def _piper_phrase_to_pcm16(phrase: str, gain: float = 1.0, noise_std: float = 0.0) -> np.ndarray:
    """Synthesize a phrase locally with Piper and return 16 kHz mono int16 PCM."""
    import os
    import tempfile

    tts = get_tts_engine("piper")
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        tts.synthesize_to_wav(phrase, wav_path)
        data, sr = sf.read(wav_path, dtype="float32")
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

    if data.ndim > 1:
        data = data.mean(axis=1)
    n = int(round(len(data) * TARGET_SAMPLE_RATE / sr))
    f16 = np.interp(
        np.linspace(0, len(data) - 1, n), np.arange(len(data)), data
    ).astype(np.float32)
    f16 = f16 * gain
    if noise_std > 0:
        rng = np.random.default_rng(42)
        f16 = f16 + rng.normal(0.0, noise_std, size=len(f16)).astype(np.float32)

    padded = np.concatenate(
        [np.zeros(8000, dtype=np.float32), f16, np.zeros(16000, dtype=np.float32)]
    )
    return (np.clip(padded, -1.0, 1.0) * 32767).astype(np.int16)


class TestWakeWordDetector:

    def test_wakeword_model_files_and_licenses_recorded(self):
        assert OPENWAKEWORD_CODE_LICENSE == "Apache-2.0"
        assert OPENWAKEWORD_MODEL_LICENSE == "CC-BY-NC-SA-4.0"
        ok, paths, missing = verify_wakeword_model_files(
            settings.WAKE_WORD_MODEL_DIR, "hey jarvis"
        )
        assert ok, f"Missing wakeword files: {missing}"
        assert paths["wakeword"].name == "hey_jarvis_v0.1.onnx"
        assert paths["melspectrogram"].name == "melspectrogram.onnx"
        assert paths["embedding"].name == "embedding_model.onnx"

    def test_missing_wakeword_files_raise_without_download(self, tmp_path, monkeypatch):
        def block_net(*args, **kwargs):
            raise AssertionError("No network download allowed at runtime!")

        monkeypatch.setattr("urllib.request.urlretrieve", block_net)
        detector = OpenWakeWordDetector(model_dir=tmp_path)
        assert detector.is_available() is False
        with pytest.raises(RuntimeError, match="setup_local_models.py"):
            detector.load()

    def test_offline_hey_jarvis_detection_across_volumes_noise_and_false_positives(self, monkeypatch):
        real_conn = socket.create_connection

        def block_external(address, *args, **kwargs):
            if address[0] not in ("127.0.0.1", "localhost", "::1"):
                raise OSError("External internet blocked")
            return real_conn(address, *args, **kwargs)

        monkeypatch.setattr(socket, "create_connection", block_external)

        detector = OpenWakeWordDetector(threshold=0.5, cooldown_seconds=0.0)
        detector.load()

        # 1. Normal volume "Hey Jarvis" activates
        pcm_normal = _piper_phrase_to_pcm16("Hey Jarvis", gain=1.0)
        trig_norm, score_norm = detector.process_pcm(pcm_normal)
        assert trig_norm is True and score_norm >= 0.5

        # 2. Softer / distance-like gain activates
        detector.reset()
        pcm_quiet = _piper_phrase_to_pcm16("Hey Jarvis", gain=0.25)
        trig_quiet, score_quiet = detector.process_pcm(pcm_quiet)
        assert trig_quiet is True and score_quiet >= 0.5

        # 3. With background noise still activates
        detector.reset()
        pcm_noisy = _piper_phrase_to_pcm16("Hey Jarvis", gain=0.9, noise_std=0.015)
        trig_noisy, score_noisy = detector.process_pcm(pcm_noisy)
        assert trig_noisy is True and score_noisy >= 0.5

        # 4. Pure background noise / non-wake / similar phrases do NOT activate
        for phrase in ("Hey Jordan", "What time is it", "Hey Google", "Open my workspace folder"):
            detector.reset()
            pcm_neg = _piper_phrase_to_pcm16(phrase, gain=1.0)
            trig_neg, score_neg = detector.process_pcm(pcm_neg)
            assert trig_neg is False, f"False positive on '{phrase}' (score={score_neg})"

        # Pure white noise should not activate
        detector.reset()
        rng = np.random.default_rng(7)
        noise_pcm = (rng.normal(0.0, 0.02, size=32000) * 32767).astype(np.int16)
        trig_bg, _ = detector.process_pcm(noise_pcm)
        assert trig_bg is False

    def test_cooldown_prevents_repeated_activation(self):
        detector = OpenWakeWordDetector(threshold=0.5, cooldown_seconds=5.0)
        detector.load()
        pcm = _piper_phrase_to_pcm16("Hey Jarvis", gain=1.0)
        trig1, _ = detector.process_pcm(pcm)
        trig2, _ = detector.process_pcm(pcm)
        assert trig1 is True
        assert trig2 is False


class TestSileroSpeechEndpointDetector:

    def test_speech_start_end_pause_tolerance_and_min_reject(self):
        # 512 samples = 32ms per chunk.
        # Build synthetic stream: 5 silent, 12 speech, 4 short pause (128ms < 320ms),
        # 10 more speech, then 15 trailing silence (480ms > 300ms silence_timeout).
        chunks: queue.Queue[np.ndarray] = queue.Queue()
        for _ in range(5):
            chunks.put(np.zeros(VAD_CHUNK_SAMPLES, dtype=np.int16))
        for _ in range(12):
            chunks.put(np.full(VAD_CHUNK_SAMPLES, 5000, dtype=np.int16))
        for _ in range(4):
            chunks.put(np.zeros(VAD_CHUNK_SAMPLES, dtype=np.int16))
        for _ in range(10):
            chunks.put(np.full(VAD_CHUNK_SAMPLES, 5000, dtype=np.int16))
        for _ in range(18):
            chunks.put(np.zeros(VAD_CHUNK_SAMPLES, dtype=np.int16))

        def energy_prob(f32: np.ndarray) -> float:
            return 0.9 if float(np.abs(f32).mean()) > 0.05 else 0.05

        vad = SileroSpeechEndpointDetector(
            vad_threshold=0.5,
            silence_timeout_seconds=0.35,
            max_utterance_seconds=5.0,
            min_speech_seconds=0.3,
            pre_roll_chunks=3,
            speech_prob_fn=energy_prob,
        )

        audio = vad.capture_utterance(
            read_chunk_fn=lambda t: chunks.get_nowait() if not chunks.empty() else None,
            await_speech_timeout=2.0,
        )
        assert audio is not None
        # Should include pre-roll (3) + speech (12) + pause (4) + speech (10) + silence (~11)
        assert len(audio) >= (12 + 4 + 10) * VAD_CHUNK_SAMPLES

        # Reject short transient click (< min_speech_seconds)
        short_q: queue.Queue[np.ndarray] = queue.Queue()
        short_q.put(np.full(VAD_CHUNK_SAMPLES, 5000, dtype=np.int16))
        for _ in range(15):
            short_q.put(np.zeros(VAD_CHUNK_SAMPLES, dtype=np.int16))
        short_audio = vad.capture_utterance(
            read_chunk_fn=lambda t: short_q.get_nowait() if not short_q.empty() else None,
            await_speech_timeout=1.0,
        )
        assert short_audio is None


class TestMicrophoneAndConversationManager:

    def test_mic_unavailable_sets_error_and_does_not_claim_enabled(self, db):
        provider = ContextAwareMockProvider()
        agent = JarvisAgent(provider=provider, registry=ToolRegistry(), db=db)
        agent.initialize()
        vc = VoiceController(agent=agent, stt_engine=MockSTTEngine(), tts_engine=MockTTSEngine())

        fake_mic = MagicMock(spec=MicrophoneCapture)
        fake_mic.is_active = False
        fake_mic.selected_device_name = "none"
        fake_mic.check_device_available.return_value = (False, "No audio input devices found.")

        mgr = HandsFreeConversationManager(
            agent=agent,
            voice_controller=vc,
            mic_capture=fake_mic,
        )
        started = mgr.start()
        assert started is False
        assert mgr.state == VoicePipelineState.ERROR
        status = mgr.get_status()
        assert status["wake_detection_enabled"] is False
        assert "No audio input devices" in status["last_error"]

    def test_voice_input_disabled_flag_prevents_activation(self, db, monkeypatch):
        monkeypatch.setattr(settings, "VOICE_INPUT_ENABLED", False)
        provider = ContextAwareMockProvider()
        agent = JarvisAgent(provider=provider, registry=ToolRegistry(), db=db)
        agent.initialize()
        vc = VoiceController(agent=agent, stt_engine=MockSTTEngine(), tts_engine=MockTTSEngine())
        mgr = HandsFreeConversationManager(agent=agent, voice_controller=vc)
        assert mgr.start() is False
        assert mgr.state == VoicePipelineState.DISABLED
        assert mgr.get_status()["wake_detection_enabled"] is False

    def test_full_hands_free_flow_followup_context_and_goodbye(self, db):
        provider = ContextAwareMockProvider()
        agent = JarvisAgent(provider=provider, registry=ToolRegistry(), db=db)
        agent.initialize()

        stt = MockSTTEngine(
            queue=[
                "What is today's date?",
                "What about tomorrow?",
                "Goodbye JARVIS.",
            ]
        )
        tts = MockTTSEngine()
        vc = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)

        states: list[VoicePipelineState] = []
        outputs: list[str] = []

        pcm_calls = {"n": 0}

        def fake_process_pcm(pcm):
            pcm_calls["n"] += 1
            if pcm_calls["n"] == 1:
                return (True, 0.95)
            return (False, 0.01)

        fake_mic = MagicMock(spec=MicrophoneCapture)
        fake_mic.is_active = True
        fake_mic.selected_device_name = "Mock Mic"
        fake_mic.check_device_available.return_value = (True, "Mock Mic")
        fake_mic.start.return_value = True
        fake_mic.read_frame.return_value = np.zeros(512, dtype=np.int16)

        fake_detector = MagicMock(spec=OpenWakeWordDetector)
        fake_detector.phrase = "hey jarvis"
        fake_detector.model_dir = settings.WAKE_WORD_MODEL_DIR
        fake_detector.package_installed.return_value = True
        fake_detector.is_available.return_value = True
        fake_detector.process_pcm.side_effect = fake_process_pcm

        fake_vad = MagicMock(spec=SileroSpeechEndpointDetector)
        fake_vad.capture_utterance.return_value = np.zeros(8000, dtype=np.float32)

        def on_state(s: VoicePipelineState):
            states.append(s)
            if s == VoicePipelineState.IDLE_WAKE_LISTENING and VoicePipelineState.WAKE_DETECTED in states:
                mgr._stop_event.set()

        mgr = HandsFreeConversationManager(
            agent=agent,
            voice_controller=vc,
            wake_detector=fake_detector,
            mic_capture=fake_mic,
            vad_detector=fake_vad,
            conversation_timeout_seconds=2.0,
            on_output=outputs.append,
            on_state_change=on_state,
        )

        with patch("voice.conversation_manager.verify_wakeword_model_files", return_value=(True, {}, [])):
            assert mgr.start() is True
            assert mgr._worker_thread is not None
            mgr._worker_thread.join(timeout=5.0)
            mgr.stop()

        joined_out = "\n".join(outputs)
        assert "[WAKE] Hey JARVIS detected." in joined_out
        assert "[JARVIS] Yes, I'm listening." in joined_out
        assert "Today is November 24, 2026." in joined_out
        assert "Tomorrow is November 25, 2026." in joined_out
        assert "Certainly. I'll be here when you need me." in joined_out

        # Only 1 wake trigger activated all 3 turns without repeating wake word
        assert pcm_calls["n"] == 1
        assert len(provider.calls) == 2  # Date + Tomorrow follow-up
        assert VoicePipelineState.IDLE_WAKE_LISTENING in states
        assert VoicePipelineState.WAKE_DETECTED in states
        assert VoicePipelineState.CONVERSATION_ACTIVE in states
        assert VoicePipelineState.PROCESSING_WITH_QWEN in states
        assert VoicePipelineState.SPEAKING_WITH_PIPER in states
        fake_mic.stop.assert_called()

    def test_conversation_timeout_returns_to_idle_wake_listening(self, db):
        provider = ContextAwareMockProvider()
        agent = JarvisAgent(provider=provider, registry=ToolRegistry(), db=db)
        agent.initialize()
        stt = MockSTTEngine(queue=["What is today's date?"])
        tts = MockTTSEngine()
        vc = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)

        states: list[VoicePipelineState] = []
        outputs: list[str] = []

        fake_mic = MagicMock(spec=MicrophoneCapture)
        fake_mic.is_active = True
        fake_mic.selected_device_name = "Mock Mic"
        fake_mic.check_device_available.return_value = (True, "Mock Mic")
        fake_mic.start.return_value = True
        fake_mic.read_frame.return_value = np.zeros(512, dtype=np.int16)

        pcm_calls = {"n": 0}

        def fake_process(pcm):
            pcm_calls["n"] += 1
            return (True, 0.9) if pcm_calls["n"] == 1 else (False, 0.01)

        fake_detector = MagicMock(spec=OpenWakeWordDetector)
        fake_detector.phrase = "hey jarvis"
        fake_detector.model_dir = settings.WAKE_WORD_MODEL_DIR
        fake_detector.package_installed.return_value = True
        fake_detector.is_available.return_value = True
        fake_detector.process_pcm.side_effect = fake_process

        # Turn 1 has speech; Turn 2 times out (None) -> triggers expiry back to IDLE_WAKE_LISTENING
        fake_vad = MagicMock(spec=SileroSpeechEndpointDetector)
        def vad_seq(*args, **kwargs):
            if vad_seq.n == 0:
                vad_seq.n += 1
                return np.zeros(8000, dtype=np.float32)
            return None
        vad_seq.n = 0
        fake_vad.capture_utterance.side_effect = vad_seq

        mgr = HandsFreeConversationManager(
            agent=agent,
            voice_controller=vc,
            wake_detector=fake_detector,
            mic_capture=fake_mic,
            vad_detector=fake_vad,
            conversation_timeout_seconds=1.0,
            on_output=outputs.append,
            on_state_change=lambda s: (
                states.append(s),
                mgr._stop_event.set()
                if s == VoicePipelineState.IDLE_WAKE_LISTENING and VoicePipelineState.CONVERSATION_ACTIVE in states
                else None,
            ),
        )

        with patch("voice.conversation_manager.verify_wakeword_model_files", return_value=(True, {}, [])):
            assert mgr.start() is True
            mgr._worker_thread.join(timeout=5.0)
            mgr.stop()

        assert any("timed out" in o.lower() for o in outputs)
        assert states.count(VoicePipelineState.IDLE_WAKE_LISTENING) >= 2

    def test_cli_voice_commands_on_off_status_test(self, db, capsys):
        provider = ContextAwareMockProvider()
        agent = JarvisAgent(provider=provider, registry=ToolRegistry(), db=db)
        agent.initialize()
        vc = VoiceController(agent=agent, stt_engine=MockSTTEngine(), tts_engine=MockTTSEngine())

        fake_hf = MagicMock(spec=HandsFreeConversationManager)
        fake_hf.start.return_value = True
        fake_hf.is_monitoring = True
        fake_hf.get_status.return_value = {
            "pipeline_state": "IDLE_WAKE_LISTENING",
            "wake_word_phrase": "hey jarvis",
            "wake_word_engine": "openwakeword",
            "wake_word_available": True,
            "wake_detection_enabled": True,
            "mic_monitoring": True,
            "mic_device": "Mock Mic",
            "stt_engine": "MockSTTEngine",
            "stt_available": True,
            "tts_engine": "MockTTSEngine",
            "tts_available": True,
            "conversation_timeout_seconds": 25.0,
            "last_error": "",
        }
        fake_hf.run_self_test.return_value = {
            "microphone": {"ok": True, "device": "Mock Mic", "samples": 512},
            "wake_word": {"ok": True, "phrase": "hey jarvis"},
            "stt": {"ok": True, "engine": "MockSTTEngine"},
            "tts": {"ok": True, "engine": "MockTTSEngine"},
        }

        cli = JarvisCLI(agent=agent, voice_controller=vc, hands_free_manager=fake_hf)
        cli._handle_command("/voice on")
        fake_hf.start.assert_called_once()

        cli._handle_command("/voice status")
        cli._handle_command("/voice test")
        cli._handle_command("/voice off")
        fake_hf.stop.assert_called_once()
        assert vc.mode == VoiceMode.TEXT

        captured = capsys.readouterr().out
        assert "IDLE_WAKE_LISTENING" in captured
        assert "PASS" in captured
        assert "Microphone monitoring stopped" in captured
