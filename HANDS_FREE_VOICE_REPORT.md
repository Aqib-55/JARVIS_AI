# JARVIS AI — Hands-Free Wake-Word Voice Implementation Report

## 1. New Modules Created
- `voice/wake_word.py` — Continuous local wake-word listener (`OpenWakeWordDetector`), single-owner 16 kHz mono `int16` PCM stream (`MicrophoneCapture`), Silero VAD v6 endpoint detector (`SileroSpeechEndpointDetector`), and local model asset validator (`verify_wakeword_model_files`).
- `voice/conversation_manager.py` — Explicit state machine (`VoicePipelineState`) and multi-turn hands-free coordinator (`HandsFreeConversationManager`) managing wake activation, speech capture, Faster-Whisper transcription, thread-safe Qwen/Ollama execution, Piper playback, follow-up continuity, timeout expiry, and `/voice test`.
- `tests/test_hands_free_voice.py` — Automated test suite (10 tests) covering wake-word validation, volume/distance/noise/false-positive scoring, Silero VAD endpointing, mic unavailability, follow-up context retention, timeout expiry, goodbye handling, and `/voice on|off|status|test`.
- `HANDS_FREE_VOICE_SETUP.md` — Setup, licensing, microphone configuration, privacy, and troubleshooting guide.
- `HANDS_FREE_VOICE_REPORT.md` — This implementation & verification report.

## 2. Existing Modules Modified
- `requirements.txt` — Added `openwakeword>=0.6.0`.
- `.env.example` — Added wake-word, microphone, VAD endpointing, and conversation timeout settings; set `VOICE_MODE=hands_free`.
- `config/settings.py` — Added typed settings and validation for `VOICE_INPUT_ENABLED`, `WAKE_WORD_*`, `VOICE_MICROPHONE_INDEX`, `VOICE_SAMPLE_RATE`, `VOICE_CHANNELS`, `VOICE_SILENCE_TIMEOUT_SECONDS`, `VOICE_MAX_UTTERANCE_SECONDS`, `VOICE_MIN_SPEECH_SECONDS`, and `CONVERSATION_TIMEOUT_SECONDS`.
- `setup_local_models.py` — Added `download_wakeword_models()` to download and verify `openWakeWord` ONNX assets in `models/wakeword/` during setup only.
- `interface/cli.py` — Updated startup banner with real component health checks, added `/voice on`, `/voice off`, `/voice status`, `/voice test`, shared `self._agent_lock` serialization between typed CLI and voice turns, and thread-safe tool approval routing (`handle_approval_request`).
- `main.py` — Wired `agent._approval_callback = cli.handle_approval_request` so background voice tool confirmations coordinate safely with the CLI prompt.
- `README.md` — Updated architecture diagram, quickstart setup (`setup_local_models.py`, Ollama/local config), and `/voice` commands.

## 3. Wake-Word Model Used
- **Engine:** `openWakeWord` (`0.6.0`) running strictly on `onnxruntime` (`1.32.0`, CPUExecutionProvider).
- **Model Files (stored locally under `models/wakeword/`, excluded via `.gitignore`):**
  - `hey_jarvis_v0.1.onnx` (`1,271,370` bytes)
  - `melspectrogram.onnx` (`1,087,958` bytes)
  - `embedding_model.onnx` (`1,326,578` bytes)
- **Audio Format:** `16,000 Hz`, mono, signed `16-bit` PCM (`int16`), scored in `1280`-sample (`80 ms`) frames.

## 4. Model Licensing
- **`openWakeWord` Python library:** Apache License 2.0 (`Apache-2.0`).
- **Pretrained release models (including `hey_jarvis_v0.1.onnx`):** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (**`CC-BY-NC-SA-4.0`**).
- **Commercial Limitation:** Pretrained openWakeWord models cannot be redistributed or used for commercial products without replacing them with a commercially licensed wake-word model. This restriction is documented in code constants (`voice/wake_word.py`) and `HANDS_FREE_VOICE_SETUP.md`.

## 5. Microphone Configuration
- Single shared `sounddevice.InputStream` owned by `MicrophoneCapture` (`16000 Hz`, `1` channel, `int16`, `blocksize=512`).
- Device index configurable via `VOICE_MICROPHONE_INDEX` (default `None` uses Windows default input: `Microphone Array (Intel® Smart Sound Technology...)`).
- Bounded in-memory queue (`maxsize=200`, drops oldest frames when idle) prevents unbounded memory growth and avoids saving idle audio.
- `/voice off` calls `MicrophoneCapture.stop()`, completely stopping and closing the hardware stream.

## 6. State Machine Implementation
Implemented as `VoicePipelineState` in `voice/conversation_manager.py`:
`STARTING` → `IDLE_WAKE_LISTENING` → `WAKE_DETECTED` → `SPEAKING_WITH_PIPER` → `AWAITING_COMMAND` → `CAPTURING_COMMAND` → `TRANSCRIBING` → `PROCESSING_WITH_QWEN` → `SPEAKING_WITH_PIPER` → `CONVERSATION_ACTIVE` → (`TRANSCRIBING` on follow-up OR `IDLE_WAKE_LISTENING` on timeout/goodbye), plus `DISABLED` (`/voice off` or `VOICE_INPUT_ENABLED=false`) and `ERROR` (mic disconnected/unavailable or missing model).

Wake detection pauses while Piper speaks, and buffered queue frames + wake-word state are reset immediately after playback to prevent self-triggering. Barge-in was deferred to preserve stable echo-free playback in this release.

## 7. Conversation Manager Behavior
- Wake trigger prints `[WAKE] Hey JARVIS detected.` and `[JARVIS] Yes, I'm listening.`, speaks acknowledgment, captures command, prints `[VOICE] Recognized: ...` and `[JARVIS] Processing...`, executes through `JarvisAgent` under `_agent_lock`, speaks response via Piper, and enters `CONVERSATION_ACTIVE`.
- Follow-up turns reuse the same `JarvisAgent` `ConversationManager` & SQLite session without repeating `"Hey JARVIS"`.
- Conversation timeout (`CONVERSATION_TIMEOUT_SECONDS=25` default) starts after Piper finishes speaking and resets on each recognized follow-up.
- Saying `"Goodbye JARVIS"` (or sleep phrases) triggers `"Certainly. I'll be here when you need me."` and returns immediately to `IDLE_WAKE_LISTENING`.

## 8. VAD Implementation
- Reused `SileroVADModel` (`silero_vad_v6.onnx` bundled in `faster_whisper.vad`) on `onnxruntime` CPUExecutionProvider (`SileroSpeechEndpointDetector`).
- Evaluates `512`-sample (`32 ms`) 16 kHz frames with stateful LSTM `(h, c, context)` tracking.
- Prepends 10 pre-roll chunks (~320 ms) to preserve speech onset, enforces `VOICE_MIN_SPEECH_SECONDS=0.3` to reject clicks/empty clips, tolerates brief mid-sentence pauses, stops after `VOICE_SILENCE_TIMEOUT_SECONDS=1.0`, and caps recordings at `VOICE_MAX_UTTERANCE_SECONDS=20`.

## 9. Follow-Up Conversation Results
- Verified via `TestMicrophoneAndConversationManager.test_full_hands_free_flow_followup_context_and_goodbye`:
  - Wake word triggered once (`pcm_calls == 1`).
  - Turn 1 (`"What is today's date?"`) → `"Today is November 24, 2026."`
  - Turn 2 without wake phrase (`"What about tomorrow?"`) → retained prior `"date"` context and returned `"Tomorrow is November 25, 2026."`
  - Turn 3 (`"Goodbye JARVIS."`) → `"Certainly. I'll be here when you need me."` → returned cleanly to `IDLE_WAKE_LISTENING`.

## 10. CPU and Memory Measurements
Measured directly on Windows (Intel i7 11th Gen, 16 GB RAM, CPU inference) during live `JarvisCLI` startup with real microphone stream and all models loaded:
- **Process RSS at import start:** `26.6 MB`
- **Process RSS in `IDLE_WAKE_LISTENING` (openWakeWord + mic stream active):** `228.4 MB`
- **Process RSS after all voice models loaded (openWakeWord + Faster-Whisper `base` INT8 + Piper `en_GB-alan-medium`):** `472.8 MB`
- **Idle CPU Usage (3.0s continuous live mic + openWakeWord scoring):** `0.52%`
- **openWakeWord Latency (per 80 ms frame):** `2.20 ms`
- **Piper Synthesis Latency (WAV generation):** `240.9 ms` (`2.74 s` total for synthesis + speaker playback of `"Yes, I am listening."`)
- **Faster-Whisper Transcription Latency:** `1399.6 ms` (~1.40 s)
- **Ollama `qwen3.5:4b` Response Latency (CPU, warm session with 26 tools):** `63.5 s` (from earlier live verification; cold loads may exceed `OLLAMA_TIMEOUT=120` unless raised in `.env`)

## 11. Wake-Word & False-Positive Tests
Tested locally offline using Piper-synthesized 16 kHz PCM across conditions + live room mic noise:
- `"Hey Jarvis"` normal volume (`gain=1.0`): **Activated** (`score = 0.9964`)
- `"Hey Jarvis"` softer volume (`gain=0.25`): **Activated** (`score >= 0.5`)
- `"Hey Jarvis"` with additive noise (`noise_std=0.015`): **Activated** (`score >= 0.5`)
- `"Hey Jordan"`: **Rejected** (`score = 0.2962 < 0.5`)
- `"What time is it"`: **Rejected** (`score = 0.00024`)
- `"Hey Google"`: **Rejected** (`score = 0.00010`)
- `"Open my workspace folder"`: **Rejected**
- Pure white noise & 3.0s live ambient room microphone: **Rejected** (`0` false triggers)
- Repeated audio buffer within cooldown: **Blocked** (`cooldown_seconds` + `reset()`)

## 12. Offline Test Results
- Blocked all non-loopback `socket.create_connection` calls + set `HF_HUB_OFFLINE=1`:
  - `JarvisCLI` initialized `OllamaProvider`, `HandsFreeConversationManager`, `OpenWakeWordDetector`, `FasterWhisperEngine`, and `PiperEngine` with zero cloud calls.
  - Startup banner accurately printed `Wake Detection: Enabled` and `Voice Mode: Hands-Free`.
  - `/voice status` reported real active stream (`Microphone Array (Intel® Smart `), `IDLE_WAKE_LISTENING`, and `25.0s` timeout.
  - `/voice test` passed all 4 hardware/model checks (`Microphone`, `Wake Word`, `STT Engine`, `TTS Engine`).
  - `/voice off` stopped monitoring (`mic_after_off == False`).
- **Full pytest suite (`pytest -v`):** **169 passed, 1 warning in 22.57s** (0 failed, 0 skipped).

## 13. Failed or Skipped Tests
- **Failed tests:** `0`
- **Skipped tests:** `0`

## 14. Remaining Manual Hardware Tests
While real Windows microphone capture (`512`-sample frames from `Microphone Array`), speaker playback via Piper, and offline `openWakeWord` scoring against synthesized `"Hey Jarvis"` speech have all been verified directly, **live in-room human speech testing** remains necessary for you to validate with your own voice:
1. Speaking `"Hey JARVIS"` naturally at various distances/angles in your room acoustic environment (and tuning `WAKE_WORD_THRESHOLD` if needed).
2. Speaking natural multi-sentence commands + follow-up questions with real room background noise to fine-tune `VOICE_SILENCE_TIMEOUT_SECONDS`.
3. Confirming speaker-to-microphone acoustic isolation in your physical workspace (confirming Piper's acknowledgment/responses do not re-trigger after mic queue drain).
