"""
Tests for local-only Faster-Whisper STT setup, verification, and offline inference:
- Required local model file verification (config.json, model.bin, tokenizer.json, vocabulary)
- Clear setup error when local model files are missing (no silent download)
- Zero Hugging Face / network calls at startup or runtime model loading
- Microphone capture + transcription workflow preservation
- Real local English & Hindi transcription on CPU INT8
"""

import io
import shutil
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import Settings, settings
from voice.speech_to_text import (
    FasterWhisperEngine,
    get_stt_engine,
    verify_whisper_model_files,
)


def _create_dummy_model_dir(base_dir: Path, include: tuple[str, ...] = (
    "config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt",
)) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    for name in include:
        content = "{}" if name.endswith(".json") else "dummy"
        (base_dir / name).write_text(content, encoding="utf-8")
    return base_dir


def _synthesize_wav_bytes(text: str) -> bytes:
    """Generate local WAV audio bytes offline using Piper TTS."""
    import os
    import tempfile
    from voice.text_to_speech import get_tts_engine

    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        tts = get_tts_engine("piper")
        tts.synthesize_to_wav(text, tmp_path)
        return Path(tmp_path).read_bytes()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


class TestLocalWhisperModelVerification:

    def test_settings_default_whisper_model_path(self, monkeypatch):
        monkeypatch.delenv("WHISPER_MODEL_PATH", raising=False)
        monkeypatch.setenv("WHISPER_MODEL", "base")
        s = Settings()
        assert s.WHISPER_MODEL_PATH == s.WHISPER_MODEL_DIR / "faster-whisper-base"
        assert s.WHISPER_DEVICE == "cpu"
        assert s.WHISPER_COMPUTE_TYPE == "int8"

    def test_verify_valid_dummy_directory(self, tmp_path):
        model_dir = _create_dummy_model_dir(tmp_path / "faster-whisper-base")
        ok, missing = verify_whisper_model_files(model_dir)
        assert ok is True
        assert missing == []

    def test_verify_missing_directory(self, tmp_path):
        ok, missing = verify_whisper_model_files(tmp_path / "nonexistent")
        assert ok is False
        assert any("directory not found" in m for m in missing)

    def test_verify_missing_required_file(self, tmp_path):
        model_dir = _create_dummy_model_dir(
            tmp_path / "incomplete",
            include=("config.json", "model.bin", "vocabulary.txt"),
        )
        ok, missing = verify_whisper_model_files(model_dir)
        assert ok is False
        assert "tokenizer.json" in missing

    def test_verify_missing_vocabulary_file(self, tmp_path):
        model_dir = _create_dummy_model_dir(
            tmp_path / "novocab",
            include=("config.json", "model.bin", "tokenizer.json"),
        )
        ok, missing = verify_whisper_model_files(model_dir)
        assert ok is False
        assert any("vocabulary" in m for m in missing)

    def test_missing_local_model_raises_clear_error_without_download(self, tmp_path, monkeypatch):
        missing_dir = tmp_path / "missing-whisper-base"

        def fail_download(*args, **kwargs):
            raise AssertionError("Hugging Face download must not be called at runtime!")

        monkeypatch.setattr("huggingface_hub.snapshot_download", fail_download)
        monkeypatch.setattr("huggingface_hub.hf_hub_download", fail_download)

        engine = FasterWhisperEngine(model_path=missing_dir)
        assert engine.is_available() is False

        with pytest.raises(RuntimeError, match="setup_local_models.py"):
            engine._get_model()

        with pytest.raises(RuntimeError, match="setup_local_models.py"):
            engine.listen_and_transcribe()


class TestLocalWhisperOfflineRuntime:

    def test_downloaded_base_model_files_exist(self):
        model_dir = settings.WHISPER_MODEL_PATH
        ok, missing = verify_whisper_model_files(model_dir)
        assert ok, f"Downloaded model incomplete at {model_dir}: {missing}"
        assert (model_dir / "config.json").is_file()
        assert (model_dir / "model.bin").is_file()
        assert (model_dir / "tokenizer.json").is_file()
        assert (model_dir / "vocabulary.txt").is_file() or (model_dir / "vocabulary.json").is_file()

    def test_startup_and_model_load_without_huggingface_network(self, monkeypatch):
        def block_network(*args, **kwargs):
            raise AssertionError("Network / Hugging Face request attempted during offline startup!")

        monkeypatch.setattr("huggingface_hub.snapshot_download", block_network)
        monkeypatch.setattr("huggingface_hub.hf_hub_download", block_network)
        monkeypatch.setattr("huggingface_hub.file_download.hf_hub_download", block_network)
        monkeypatch.setattr("tokenizers.Tokenizer.from_pretrained", block_network)
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine = get_stt_engine("faster_whisper")
            assert isinstance(engine, FasterWhisperEngine)
            assert engine.model_path == settings.WHISPER_MODEL_PATH
            assert engine.device == "cpu"
            assert engine.compute_type == "int8"

            model = engine._get_model()
            assert model is not None

        warning_texts = [str(w.message) for w in caught]
        assert not any("symlink" in t.lower() for t in warning_texts)
        assert not any("unauthenticated" in t.lower() for t in warning_texts)

    def test_english_and_hindi_transcription_offline(self, monkeypatch):
        def block_network(*args, **kwargs):
            raise AssertionError("Network / Hugging Face request attempted during transcription!")

        monkeypatch.setattr("huggingface_hub.snapshot_download", block_network)
        monkeypatch.setattr("huggingface_hub.hf_hub_download", block_network)
        monkeypatch.setattr("tokenizers.Tokenizer.from_pretrained", block_network)

        eng_wav = _synthesize_wav_bytes("Hello Jarvis, what is today's date?")
        hi_wav = _synthesize_wav_bytes("Namaste Jarvis, mera naam Raqib hai")

        engine = FasterWhisperEngine(language="auto", device="cpu", compute_type="int8")

        text_en, lang_en = engine.transcribe_audio(io.BytesIO(eng_wav))
        assert len(text_en) > 0
        assert "jarvis" in text_en.lower() or "date" in text_en.lower()
        assert lang_en == "en"

        text_hi, lang_hi = engine.transcribe_audio(io.BytesIO(hi_wav), language="hi")
        assert len(text_hi) > 0
        assert lang_hi == "hi"

    def test_microphone_capture_workflow_preserved(self, monkeypatch):
        import numpy as np
        import soundfile as sf

        wav_bytes = _synthesize_wav_bytes("Open calculator please")
        data, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != 16000:
            n = int(round(len(data) * 16000 / sr))
            data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)

        mock_mic = MagicMock()
        mock_mic.start.return_value = True
        mock_vad = MagicMock()
        mock_vad.capture_utterance.return_value = data

        with patch("voice.wake_word.MicrophoneCapture", return_value=mock_mic), \
             patch("voice.wake_word.SileroSpeechEndpointDetector", return_value=mock_vad):
            engine = FasterWhisperEngine(language="en", device="cpu", compute_type="int8")
            result = engine.listen_and_transcribe(timeout=3.0)

        assert len(result) > 0
        assert "calculator" in result.lower() or "open" in result.lower()
        mock_mic.start.assert_called_once()
        mock_mic.stop.assert_called_once()
