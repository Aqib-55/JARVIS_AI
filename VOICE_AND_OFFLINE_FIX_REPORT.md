# JARVIS AI — Voice & Offline Accuracy Fix Report

## Summary of Issues Resolved

### Issue 1: Piper Model Discovery, Validation & API Compatibility
**Root Cause:**
1. `D:\JARVIS_AI\models\tts\` was empty — `en_GB-alan-medium.onnx` and `en_GB-alan-medium.onnx.json` had not been downloaded via `setup_local_models.py`.
2. `PiperEngine._find_model_file()` in `voice/text_to_speech.py` ignored `self._model_dir`, did not validate the companion `.onnx.json` config file, and used a wildcard `rglob("*.onnx")` fallback.
3. `PiperEngine.is_available()` only checked `import piper`, reporting `True` even when model files were missing.
4. `PiperEngine.speak()` passed a raw binary handle (`open(tmp_path, "wb")`) to `PiperVoice.synthesize()`, which is incompatible with installed `piper-tts` (`1.8.0`), where `PiperVoice.synthesize()` yields `AudioChunk` objects and `PiperVoice.synthesize_wav(text, wave_writer, syn_config=...)` writes WAV data via `wave.Wave_write`.

**Fixes Implemented:**
- Added `verify_piper_model_files(model_dir, voice_name)` in `voice/text_to_speech.py` to validate both `<voice_name>.onnx` and `<voice_name>.onnx.json` (non-empty files + valid JSON).
- Updated `PiperEngine` to validate against `self._model_dir` without triggering runtime downloads, report `is_available() == False` when model files are missing, and record clear setup instructions in `self.last_error` (`python setup_local_models.py`).
- Added `PiperEngine.synthesize_to_wav()` using `wave.open(..., "wb")` + `PiperVoice.synthesize_wav(..., syn_config=SynthesisConfig(...))` and verified playable WAV generation and audio playback.
- Downloaded `en_GB-alan-medium.onnx` (63,201,294 bytes) and `en_GB-alan-medium.onnx.json` (4,888 bytes) via `setup_local_models.download_piper_voice("en_GB-alan-medium")` into `D:\JARVIS_AI\models\tts\`. Verified ignored by `.gitignore` (`models/`).

### Issue 2: Offline Truthfulness & System Instructions
**Root Cause:**
`SYSTEM_INSTRUCTION` in `core/agent.py` contained no architecture grounding, allowing `qwen3.5:4b` to guess cloud connectivity despite `LOCAL_AI_ONLY=true`.

**Fixes Implemented:**
- Updated `SYSTEM_INSTRUCTION` in `core/agent.py` to explicitly identify Ollama + local model, Faster-Whisper STT, and Piper TTS, prohibit fabricating cloud connectivity or external API usage, and distinguish local tools from internet-dependent tools.
- Added `JarvisAgent.set_voice_diagnostics_provider()` and `_get_runtime_diagnostics_block()` inside `_build_dynamic_instruction()` so every turn injects live provider, model, `LOCAL_AI_ONLY`, SQLite, STT availability/path, TTS availability/voice/dir, and registered tool classification.
- Wired `JarvisCLI.__init__` in `interface/cli.py` to connect `VoiceController.get_diagnostics` to `JarvisAgent`.

**Tool Offline Classification:**
- **Fully Local / Offline Capable:** File management tools (`list_files`, `create_folder`, `create_file`, `read_file`, `search_files`, `file_exists`, `rename_file`, `copy_file`, `move_file`, `delete_file`), calculator/datetime (`calculate`, `get_datetime`), system inspection/local apps (`get_system_info`, `get_resource_usage`, `list_processes`, `open_application`), productivity (`manage_notes`, `manage_reminders`, `manage_tasks`, `summarize_text`), and development (`create_python_file`, `read_code_file`, `explain_code_error`, `run_python_script`, local `execute_approved_command`).
- **Intentionally Network-Dependent:** `open_website` in `tools/system_automation.py` (opens an HTTP/HTTPS URL in the default browser, requiring network access for external websites). Any user-specified network shell command via `execute_approved_command` also depends on external connectivity.

### Issue 3: Voice State Lifecycle & Duplicate `[JARVIS] Ready.`
**Root Cause:**
1. `VoiceController.speak_response()` set `AudioState.SPEAKING` *before* calling `self._tts.speak()`, causing `[JARVIS] Speaking...` to print even when Piper voice loading failed.
2. `VoiceController.speak_response()` transitioned to `AudioState.IDLE` at the end, and `listen_and_process()` called `self._set_state(AudioState.IDLE)` again immediately afterward — emitting `[JARVIS] Ready.` twice.
3. `_play_wav()` did not propagate playback failure back to `speak()`.

**Fixes Implemented:**
- Added `on_playback_start` callback to `BaseTTSEngine.speak()` / `PiperEngine.speak()` / `Pyttsx3Engine.speak()` / `MockTTSEngine.speak()` so `AudioState.SPEAKING` is emitted **only after** WAV synthesis succeeds and playback actually begins.
- Updated `PiperEngine._play_wav()` to return `bool` so playback failures are accurately surfaced instead of claiming playback succeeded.
- Added `on_speech_unavailable` callback to `VoiceController` and `JarvisCLI._on_speech_unavailable()` to display `[JARVIS] 🔇 Speech output unavailable (...)` while keeping the text response visible.
- Guarded `VoiceController._set_state()` against redundant transitions to the same state and removed the duplicate `self._set_state(AudioState.IDLE)` calls in `listen_and_process()`.

### Issue 4: Offline Verification Results

| Check | Result | Notes |
| --- | --- | --- |
| Full pytest suite (`pytest -v`) | **159 passed, 1 warning (16.15s)** | Includes all existing tests, [test_faster_whisper_local.py](tests/test_faster_whisper_local.py), and [test_offline_and_voice_fixes.py](tests/test_offline_and_voice_fixes.py) |
| Piper WAV generation & playback | **Passed** | `22050 Hz`, mono 16-bit, `69632` frames generated; `speak()` triggered `SPEAKING` and returned `True` |
| Live Ollama local response (updated prompt) | **Passed** | `Init: 0.9s`, `Response: 63.5s` (`OllamaProvider(timeout=240)`); accurately reported local Ollama/`qwen3.5:4b`, `FasterWhisperEngine`, `PiperEngine`, SQLite, local tools, and `open_website` needing internet |
| Offline E2E with external internet blocked | **Passed** | Blocked all non-loopback `socket.create_connection` + `HF_HUB_OFFLINE=1`; Piper WAV synthesis -> Faster-Whisper transcription (`'Jarvis Offline Voice Test'`, `lang: en`) -> Ollama response all succeeded |
| No Gemini / Cloud STT / Cloud TTS fallback | **Passed** | Verified via `test_no_gemini_or_cloud_stt_tts_fallback`: `RuntimeError` raised for `gemini`, `speech_recognition`, and `edge_tts`; `google.genai` not loaded |

## Files Modified / Created
- `voice/text_to_speech.py`
- `voice/voice_controller.py`
- `core/agent.py`
- `interface/cli.py`
- `tests/test_offline_and_voice_fixes.py` (new)
- `VOICE_AND_OFFLINE_FIX_REPORT.md` (new)

## Unresolved / Environmental Observations
- **CPU Inference Latency vs `OLLAMA_TIMEOUT=120`:** During the first cold live agent call with all 26 tool JSON schemas attached (`timeout=120s`), `qwen3.5:4b` on CPU exceeded 120 seconds and timed out; a subsequent call with `timeout=240` completed in `63.5s` (once loaded). Users on CPU-only hardware running full 26-tool prompts cold may want to increase `OLLAMA_TIMEOUT` (e.g., `180`–`240`) in `.env`.
- **Hindi Audio Hardware Note:** No local Hindi system TTS voice is installed on Windows here; Hindi (`language="hi"`) decoding was tested in [test_faster_whisper_local.py](tests/test_faster_whisper_local.py) using local SAPI audio in Hindi mode rather than a native Hindi speaker sample.
- **Git Status:** Model binaries remain excluded by `.gitignore` (`models/`), and no changes were committed or pushed.
