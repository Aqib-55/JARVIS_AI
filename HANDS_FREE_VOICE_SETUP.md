# JARVIS AI — Hands-Free Voice Setup & Guide

## 1. Overview
JARVIS operates in a 100% local hands-free voice architecture:
- **Wake-Word Detection:** `openWakeWord` (`hey_jarvis_v0.1.onnx` via ONNX Runtime CPU)
- **Speech Endpointing (VAD):** Silero VAD v6 (`silero_vad_v6.onnx` via ONNX Runtime CPU)
- **Speech-to-Text (STT):** Faster-Whisper (`Systran/faster-whisper-base`, CPU INT8, English & Hindi auto-detect)
- **Reasoning Engine:** Ollama (`qwen3.5:4b` at `http://127.0.0.1:11434`)
- **Text-to-Speech (TTS):** Piper TTS (`en_GB-alan-medium.onnx` + `.onnx.json`)

## 2. Installation & Model Downloads

### Install Python Dependencies
Inside `.venv` on Windows (Python 3.13):
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Download Local Models (One-Time Setup)
JARVIS never downloads models during normal startup or `/voice`. Run setup once:
```powershell
.\.venv\Scripts\python.exe setup_local_models.py
```

Downloaded locations (excluded from Git via `.gitignore` `models/` rule):
- **Wake-Word ONNX (`models/wakeword/`):**
  - `hey_jarvis_v0.1.onnx`
  - `melspectrogram.onnx`
  - `embedding_model.onnx`
- **Faster-Whisper (`models/stt/faster-whisper-base/`):**
  - `config.json`, `model.bin`, `tokenizer.json`, `vocabulary.txt`
- **Piper TTS (`models/tts/`):**
  - `en_GB-alan-medium.onnx`, `en_GB-alan-medium.onnx.json`

## 3. Model & Component Licensing
> **Important Licensing Notice:**
> - **openWakeWord library:** Apache License 2.0 (`Apache-2.0`).
> - **openWakeWord pretrained release models (including `hey_jarvis_v0.1.onnx`):** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (**`CC-BY-NC-SA-4.0`**). Future **commercial redistribution** requires training or replacing the wake-word model with a commercially licensed model.
> - **Piper TTS (`piper-tts`):** GPL-licensed.
> - **Faster-Whisper & Silero VAD:** MIT-licensed.

## 4. Microphone Configuration
To view available input devices and indices:
```powershell
.\.venv\Scripts\python.exe -c "from voice.wake_word import list_input_devices; print(list_input_devices())"
```
Set `VOICE_MICROPHONE_INDEX` in `.env` (leave empty to use the Windows default input device):
```env
VOICE_MICROPHONE_INDEX=
VOICE_SAMPLE_RATE=16000
VOICE_CHANNELS=1
```

## 5. Enabling, Disabling & Tuning Voice Mode
Key `.env` variables:
```env
VOICE_ENABLED=true
VOICE_INPUT_ENABLED=true
VOICE_OUTPUT_ENABLED=true
WAKE_WORD_ENABLED=true
WAKE_WORD_PHRASE=hey jarvis
WAKE_WORD_THRESHOLD=0.5

VOICE_SILENCE_TIMEOUT_SECONDS=1.0
VOICE_MAX_UTTERANCE_SECONDS=20
VOICE_MIN_SPEECH_SECONDS=0.3
CONVERSATION_TIMEOUT_SECONDS=25
VOICE_MODE=hands_free
```
- Setting `VOICE_INPUT_ENABLED=false` or `WAKE_WORD_ENABLED=false` disables automatic wake-word monitoring on startup.
- In-session commands:
  - `/voice on` — Enable hands-free wake-word detection and open the microphone stream.
  - `/voice off` — Stop wake-word detection and **close** hardware microphone access immediately.
  - `/voice status` — Display live pipeline state, microphone monitoring state, device name, STT/TTS availability, and timeout.
  - `/voice test` — Test microphone stream capture, `openWakeWord` scoring, `Faster-Whisper`, and `Piper`.
  - `/voice` — Trigger a single push-to-talk turn (shares the active mic stream cleanly without opening competing streams).

## 6. Privacy & Offline Behavior
- Continuous idle microphone frames (`16 kHz` mono `int16` PCM) remain strictly in bounded memory queues and are scored locally by `openWakeWord`.
- Idle microphone audio is **never** written to disk, **never** transcribed by Whisper, **never** sent to Ollama, and **never** uploaded anywhere.
- Speech is passed to Faster-Whisper **only** after a wake trigger (`"Hey JARVIS"`) or during an active follow-up conversation window.
- During Piper playback, wake-word detection is paused and buffered mic frames are drained afterward to avoid self-activation.
- Note on tools: all AI, STT, TTS, wake-word, and SQLite subsystems run offline; the `open_website` tool intentionally opens URLs in your web browser and requires internet to load external sites.

## 7. Testing & Offline Verification
Run the full automated test suite:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
Run offline verification (blocking external network access while testing wake-word, Whisper, and Piper):
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hands_free_voice.py tests/test_offline_and_voice_fixes.py -v
```

## 8. Troubleshooting
- **`Wake Detection: Unavailable` on startup:** Run `python setup_local_models.py` to populate `models/wakeword/` and verify a microphone is connected in Windows Sound Settings.
- **Repeated miss or false triggers:** Adjust `WAKE_WORD_THRESHOLD` in `.env` (lower e.g. `0.4` for softer voice / farther distance; raise e.g. `0.6` in noisy rooms).
- **Sentences cut off during pauses:** Increase `VOICE_SILENCE_TIMEOUT_SECONDS` (e.g., `1.3` or `1.5`).
- **Slow CPU LLM responses (`Ollama request timed out`):** Increase `OLLAMA_TIMEOUT` (e.g., `180`–`240`) in `.env` for CPU-only hardware.
