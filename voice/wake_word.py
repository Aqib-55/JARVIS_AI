"""
Local Wake-Word Detection, Microphone Stream Ownership & Silero VAD Endpointing.

Uses:
  - openWakeWord (Apache 2.0 code; pretrained models CC BY-NC-SA 4.0) via ONNX Runtime
  - Silero VAD v6 (bundled ONNX via faster_whisper.vad) for speech start/end detection
  - sounddevice.InputStream as the single shared mono 16 kHz PCM audio source

Privacy & Local-Only Guarantees:
  - All audio processing is 100% local on CPU.
  - Idle audio is never written to disk, never sent to Whisper, and never sent to Ollama.
  - Only one InputStream is opened while monitoring is enabled; /voice off closes it completely.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

import numpy as np

from config.settings import settings

logger = logging.getLogger(__name__)

# Licensing metadata (required documentation & audit tracking)
OPENWAKEWORD_CODE_LICENSE = "Apache-2.0"
OPENWAKEWORD_MODEL_LICENSE = "CC-BY-NC-SA-4.0"
OPENWAKEWORD_LICENSE_NOTE = (
    "openWakeWord Python library is Apache-2.0, while pretrained release models "
    "(including hey_jarvis_v0.1.onnx) are licensed under CC BY-NC-SA 4.0 "
    "(non-commercial use only unless replaced with a commercially licensed model)."
)

# Standard audio format required by openWakeWord & Silero VAD
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
WAKEWORD_FRAME_SAMPLES = 1280  # 80 ms @ 16 kHz
VAD_CHUNK_SAMPLES = 512        # 32 ms @ 16 kHz

# Official pretrained ONNX filenames stored under models/wakeword/
_WAKEWORD_MODEL_FILES = {
    "hey jarvis": "hey_jarvis_v0.1.onnx",
    "hey_jarvis": "hey_jarvis_v0.1.onnx",
}
_SHARED_FEATURE_FILES = (
    "melspectrogram.onnx",
    "embedding_model.onnx",
)


def resolve_wakeword_filename(phrase: str = "hey jarvis") -> str:
    """Map configured wake phrase to its pretrained ONNX filename."""
    norm = phrase.lower().strip()
    if norm in _WAKEWORD_MODEL_FILES:
        return _WAKEWORD_MODEL_FILES[norm]
    if norm.endswith(".onnx"):
        return norm
    return f"{norm.replace(' ', '_')}_v0.1.onnx"


def verify_wakeword_model_files(
    model_dir: Path,
    phrase: str = "hey jarvis",
) -> tuple[bool, dict[str, Path], list[str]]:
    """
    Verify that local openWakeWord ONNX files exist in model_dir.
    Never triggers any network download.

    Returns:
        (is_valid, resolved_paths_dict, missing_descriptions)
    """
    if not model_dir.exists() or not model_dir.is_dir():
        return False, {}, [f"directory not found: {model_dir}"]

    ww_filename = resolve_wakeword_filename(phrase)
    expected = {
        "wakeword": model_dir / ww_filename,
        "melspectrogram": model_dir / "melspectrogram.onnx",
        "embedding": model_dir / "embedding_model.onnx",
    }

    missing: list[str] = []
    for key, path in expected.items():
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(path.name)

    if missing:
        return False, {}, missing
    return True, expected, []


class OpenWakeWordDetector:
    """
    Local openWakeWord detector loaded strictly from models/wakeword/ ONNX files.
    Keeps ONNX Runtime sessions cached in memory to avoid repeated loads.
    """

    def __init__(
        self,
        model_dir: Path | None = None,
        phrase: str | None = None,
        threshold: float | None = None,
        cooldown_seconds: float = 1.5,
    ) -> None:
        self.model_dir = Path(model_dir) if model_dir is not None else settings.WAKE_WORD_MODEL_DIR
        self.phrase = (phrase or settings.WAKE_WORD_PHRASE).strip()
        self.threshold = float(threshold if threshold is not None else settings.WAKE_WORD_THRESHOLD)
        self.cooldown_seconds = cooldown_seconds

        self._model = None
        self._model_key: str = ""
        self._lock = threading.Lock()
        self._pcm_remainder = np.zeros(0, dtype=np.int16)
        self._last_trigger_ts: float = 0.0
        self.last_error: str = ""

    @staticmethod
    def package_installed() -> bool:
        try:
            import openwakeword  # noqa: F401
            import onnxruntime  # noqa: F401
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        if not self.package_installed():
            return False
        ok, _, _ = verify_wakeword_model_files(self.model_dir, self.phrase)
        return ok

    def validate_files(self) -> dict[str, Path]:
        ok, paths, missing = verify_wakeword_model_files(self.model_dir, self.phrase)
        if not ok:
            raise RuntimeError(
                f"Wake-word ONNX model files missing in '{self.model_dir}': {', '.join(missing)}. "
                "Automatic runtime download is disabled. "
                "Run 'python setup_local_models.py' once to download local wake-word assets."
            )
        return paths

    def load(self) -> None:
        """Load the openWakeWord ONNX model once into memory."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if not self.package_installed():
                raise RuntimeError(
                    "openwakeword (or onnxruntime) is not installed. Run: pip install openwakeword"
                )
            paths = self.validate_files()
            from openwakeword.model import Model

            logger.info("Loading local openWakeWord ONNX model from %s ...", self.model_dir)
            self._model = Model(
                wakeword_models=[str(paths["wakeword"])],
                inference_framework="onnx",
                melspec_model_path=str(paths["melspectrogram"]),
                embedding_model_path=str(paths["embedding"]),
            )
            keys = list(self._model.models.keys())
            self._model_key = keys[0] if keys else paths["wakeword"].stem
            self._flush_silence_locked()
            self.last_error = ""
            logger.info("openWakeWord model '%s' loaded locally on ONNX Runtime.", self._model_key)

    def _flush_silence_locked(self) -> None:
        """
        Flush the full 4-second AudioFeatures buffer with deterministic zeros
        after openwakeword.Model init/reset, preventing random-noise spillover
        from triggering false positives on phonetically similar phrases.
        """
        if self._model is None:
            return
        self._model.preprocessor(np.zeros(TARGET_SAMPLE_RATE * 4, dtype=np.int16))
        for key in self._model.models:
            self._model.prediction_buffer[key].clear()
            self._model.prediction_buffer[key].extend([0.0] * 5)

    def reset(self) -> None:
        """Clear buffered audio features & prediction history to prevent re-triggering."""
        with self._lock:
            self._pcm_remainder = np.zeros(0, dtype=np.int16)
            if self._model is not None:
                self._model.reset()
                self._flush_silence_locked()

    def process_pcm(self, pcm_int16: np.ndarray) -> tuple[bool, float]:
        """
        Feed mono 16 kHz int16 PCM samples into the wake-word model.

        Returns:
            (triggered, max_score)
        """
        if self._model is None:
            self.load()

        if pcm_int16.dtype != np.int16:
            pcm_int16 = pcm_int16.astype(np.int16)
        if pcm_int16.ndim > 1:
            pcm_int16 = pcm_int16[:, 0]

        with self._lock:
            if len(self._pcm_remainder) > 0:
                buf = np.concatenate([self._pcm_remainder, pcm_int16])
            else:
                buf = pcm_int16

            max_score = 0.0
            triggered = False
            offset = 0
            while offset + WAKEWORD_FRAME_SAMPLES <= len(buf):
                frame = buf[offset : offset + WAKEWORD_FRAME_SAMPLES]
                offset += WAKEWORD_FRAME_SAMPLES
                scores = self._model.predict(frame)
                score = float(scores.get(self._model_key, max(scores.values(), default=0.0)))
                if score > max_score:
                    max_score = score

                now = time.monotonic()
                if score >= self.threshold and (now - self._last_trigger_ts) >= self.cooldown_seconds:
                    self._last_trigger_ts = now
                    triggered = True
                    # Reset model state immediately so remaining frames cannot double-trigger
                    self._model.reset()
                    self._flush_silence_locked()
                    self._pcm_remainder = np.zeros(0, dtype=np.int16)
                    return True, max_score

            self._pcm_remainder = buf[offset:].copy()
            return triggered, max_score


class SileroSpeechEndpointDetector:
    """
    Streaming speech start/end detector using Silero VAD v6 ONNX
    (reused directly from installed faster_whisper assets — zero extra dependencies).
    """

    def __init__(
        self,
        vad_threshold: float = 0.45,
        silence_timeout_seconds: float | None = None,
        max_utterance_seconds: float | None = None,
        min_speech_seconds: float | None = None,
        sample_rate: int = TARGET_SAMPLE_RATE,
        pre_roll_chunks: int = 10,
        speech_prob_fn: Callable[[np.ndarray], float] | None = None,
    ) -> None:
        self.vad_threshold = vad_threshold
        self.silence_timeout_seconds = float(
            silence_timeout_seconds
            if silence_timeout_seconds is not None
            else settings.VOICE_SILENCE_TIMEOUT_SECONDS
        )
        self.max_utterance_seconds = float(
            max_utterance_seconds
            if max_utterance_seconds is not None
            else settings.VOICE_MAX_UTTERANCE_SECONDS
        )
        self.min_speech_seconds = float(
            min_speech_seconds
            if min_speech_seconds is not None
            else settings.VOICE_MIN_SPEECH_SECONDS
        )
        self.sample_rate = sample_rate
        self.pre_roll_chunks = pre_roll_chunks
        self._custom_prob_fn = speech_prob_fn

        self._vad_session = None
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._ctx = np.zeros((1, 64), dtype=np.float32)

    def _ensure_vad(self) -> None:
        if self._custom_prob_fn is not None or self._vad_session is not None:
            return
        from faster_whisper.vad import get_vad_model
        vad_model = get_vad_model()
        self._vad_session = vad_model.session

    def reset_state(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._ctx = np.zeros((1, 64), dtype=np.float32)

    def score_chunk(self, chunk_float32: np.ndarray) -> float:
        """Compute speech probability [0.0..1.0] for a 512-sample 16 kHz float32 frame."""
        if self._custom_prob_fn is not None:
            return float(self._custom_prob_fn(chunk_float32))

        self._ensure_vad()
        if len(chunk_float32) < VAD_CHUNK_SAMPLES:
            padded = np.zeros(VAD_CHUNK_SAMPLES, dtype=np.float32)
            padded[: len(chunk_float32)] = chunk_float32
            chunk_float32 = padded
        elif len(chunk_float32) > VAD_CHUNK_SAMPLES:
            chunk_float32 = chunk_float32[:VAD_CHUNK_SAMPLES]

        inp = np.concatenate([self._ctx, chunk_float32.reshape(1, -1)], axis=1)
        out, self._h, self._c = self._vad_session.run(
            None,
            {"input": inp, "h": self._h, "c": self._c},
        )
        self._ctx = chunk_float32[-64:].reshape(1, -1)
        return float(np.asarray(out).reshape(-1)[0])

    def capture_utterance(
        self,
        read_chunk_fn: Callable[[float], np.ndarray | None],
        await_speech_timeout: float = 8.0,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray | None:
        """
        Capture a single spoken command from streaming 512-sample int16 PCM chunks.

        - Waits up to `await_speech_timeout` seconds for speech onset.
        - Prepends pre-roll frames so initial syllables are never clipped.
        - Stops after `silence_timeout_seconds` of trailing silence or `max_utterance_seconds`.
        - Rejects clips with < `min_speech_seconds` of detected speech (returns None).
        """
        self.reset_state()
        pre_roll: deque[np.ndarray] = deque(maxlen=self.pre_roll_chunks)
        captured: list[np.ndarray] = []

        speech_started = False
        speech_samples = 0
        total_captured_samples = 0
        silence_samples = 0

        min_speech_samples = int(self.min_speech_seconds * self.sample_rate)
        silence_limit_samples = int(self.silence_timeout_seconds * self.sample_rate)
        max_utterance_samples = int(self.max_utterance_seconds * self.sample_rate)

        wait_deadline = time.monotonic() + await_speech_timeout
        remainder = np.zeros(0, dtype=np.int16)

        while True:
            if cancel_event and cancel_event.is_set():
                return None

            if not speech_started and time.monotonic() >= wait_deadline:
                return None

            chunk = read_chunk_fn(0.08)
            if chunk is None:
                continue

            if chunk.dtype != np.int16:
                chunk = chunk.astype(np.int16)
            if chunk.ndim > 1:
                chunk = chunk[:, 0]

            if len(remainder) > 0:
                buf = np.concatenate([remainder, chunk])
            else:
                buf = chunk

            offset = 0
            while offset + VAD_CHUNK_SAMPLES <= len(buf):
                sub = buf[offset : offset + VAD_CHUNK_SAMPLES]
                offset += VAD_CHUNK_SAMPLES
                f32 = sub.astype(np.float32) / 32768.0
                prob = self.score_chunk(f32)
                is_speech = prob >= self.vad_threshold

                if not speech_started:
                    pre_roll.append(f32)
                    if is_speech:
                        speech_started = True
                        captured.extend(pre_roll)
                        total_captured_samples = sum(len(c) for c in captured)
                        speech_samples = len(f32)
                        silence_samples = 0
                else:
                    captured.append(f32)
                    total_captured_samples += len(f32)
                    if is_speech:
                        speech_samples += len(f32)
                        silence_samples = 0
                    else:
                        silence_samples += len(f32)

                    if silence_samples >= silence_limit_samples:
                        offset = len(buf)
                        break
                    if total_captured_samples >= max_utterance_samples:
                        offset = len(buf)
                        break

            remainder = buf[offset:].copy()

            if speech_started and (
                silence_samples >= silence_limit_samples
                or total_captured_samples >= max_utterance_samples
            ):
                break

        if not speech_started or speech_samples < min_speech_samples or not captured:
            return None

        return np.concatenate(captured, axis=0).astype(np.float32)


def list_input_devices() -> list[dict[str, Any]]:
    """Return available audio input devices via sounddevice."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        result: list[dict[str, Any]] = []
        for idx, dev in enumerate(devices):
            if int(dev.get("max_input_channels", 0)) > 0:
                result.append(
                    {
                        "index": idx,
                        "name": dev.get("name", f"Device {idx}"),
                        "channels": int(dev.get("max_input_channels", 1)),
                        "default_samplerate": float(dev.get("default_samplerate", 16000)),
                    }
                )
        return result
    except Exception as e:
        logger.warning("Failed to list audio input devices: %s", e)
        return []


class MicrophoneCapture:
    """
    Single-owner continuous mono 16 kHz PCM microphone stream via sounddevice.
    Prevents competing microphone streams across JARVIS subsystems.
    """

    def __init__(
        self,
        device_index: int | None = None,
        sample_rate: int = TARGET_SAMPLE_RATE,
        channels: int = TARGET_CHANNELS,
        blocksize: int = VAD_CHUNK_SAMPLES,
        max_queue_frames: int = 200,
    ) -> None:
        self.device_index = (
            device_index if device_index is not None else settings.VOICE_MICROPHONE_INDEX
        )
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_frames)
        self._stream = None
        self._lock = threading.Lock()
        self._active = False
        self.last_error: str = ""
        self.selected_device_name: str = ""

    @property
    def is_active(self) -> bool:
        return self._active and self._stream is not None

    def check_device_available(self) -> tuple[bool, str]:
        """Verify at least one usable microphone exists without opening a stream."""
        try:
            import sounddevice as sd
            devices = list_input_devices()
            if not devices:
                return False, "No audio input devices found."
            if self.device_index is not None:
                dev = sd.query_devices(self.device_index, kind="input")
                self.selected_device_name = str(dev.get("name", f"Device {self.device_index}"))
                return True, self.selected_device_name
            default_in = sd.default.device[0]
            if default_in is None or default_in < 0:
                self.selected_device_name = devices[0]["name"]
                return True, self.selected_device_name
            dev = sd.query_devices(default_in, kind="input")
            self.selected_device_name = str(dev.get("name", f"Device {default_in}"))
            return True, self.selected_device_name
        except Exception as e:
            return False, f"Microphone check failed: {e}"

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            logger.debug("Audio input status flag: %s", status)
        pcm = np.asarray(indata[:, 0] if indata.ndim > 1 else indata, dtype=np.int16).copy()
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            # Drop oldest idle frame so memory stays bounded and audio never builds up
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(pcm)
            except queue.Empty:
                pass

    def start(self) -> bool:
        """Open and start the single microphone InputStream."""
        with self._lock:
            if self._active and self._stream is not None:
                return True

            ok, detail = self.check_device_available()
            if not ok:
                self.last_error = detail
                logger.error("Cannot start microphone stream: %s", detail)
                return False

            try:
                import sounddevice as sd
                self.drain()
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="int16",
                    blocksize=self.blocksize,
                    device=self.device_index,
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._active = True
                self.last_error = ""
                logger.info(
                    "Microphone stream started (%s, %d Hz mono int16).",
                    self.selected_device_name or "default",
                    self.sample_rate,
                )
                return True
            except Exception as e:
                self.last_error = f"Audio stream error: {e}"
                logger.error("Failed to open microphone stream: %s", e)
                self._cleanup_stream_locked()
                return False

    def _cleanup_stream_locked(self) -> None:
        self._active = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.drain()

    def stop(self) -> None:
        """Stop and close the hardware microphone stream completely."""
        with self._lock:
            was_active = self._active
            self._cleanup_stream_locked()
            if was_active:
                logger.info("Microphone stream stopped and closed.")

    def drain(self) -> None:
        """Discard any buffered audio frames."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def read_frame(self, timeout: float = 0.1) -> np.ndarray | None:
        """Read next PCM int16 frame from queue, detecting unexpected stream closure."""
        if not self._active:
            return None
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            # Verify underlying PortAudio stream hasn't died mid-session
            if self._stream is not None and not getattr(self._stream, "active", True):
                self.last_error = "Microphone disconnected or stream stopped unexpectedly."
                logger.error(self.last_error)
                self.stop()
            return None
