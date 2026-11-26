# JARVIS AI — Voice Integration & Setup Guide

This guide explains how to configure, test, and troubleshoot the local microphone wake-word, speech-to-text (STT), and speaker text-to-speech (TTS) subsystems on Windows.

> See [HANDS_FREE_VOICE_SETUP.md](HANDS_FREE_VOICE_SETUP.md) for full hands-free `"Hey JARVIS"` wake-word details and model licensing.

---

## 1. Required Packages & Local Models

All required audio dependencies are listed in `requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_local_models.py
```

### Dependency Overview:
- `openwakeword` (ONNX Runtime CPU): Local `"Hey JARVIS"` wake-word detection.
- `faster-whisper`: Local CPU INT8 neural speech recognition (includes Silero VAD v6 ONNX).
- `piper-tts`: Local neural text-to-speech (`en_GB-alan-medium`).
- `sounddevice`, `soundfile`, `numpy`: Single-stream 16 kHz mono PCM microphone capture and WAV playback.

---

## 2. Configuration Settings

Voice settings are controlled via environment variables in `.env` (or configured via `config/settings.py`):

```env
# ------ Voice Subsystem Settings (Local Only) ------
VOICE_ENABLED=true
VOICE_INPUT_ENABLED=true
VOICE_OUTPUT_ENABLED=true
VOICE_STT_PROVIDER=faster_whisper
VOICE_TTS_PROVIDER=piper
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=auto
PIPER_MODEL_PATH=models/tts
PIPER_VOICE=en_GB-alan-medium
TTS_VOLUME=1.0
TTS_SPEED=1.0
WAKE_WORD_ENABLED=true
WAKE_WORD_PHRASE=hey jarvis
WAKE_WORD_THRESHOLD=0.5
VOICE_MODE=hands_free
VOICE_SILENCE_TIMEOUT_SECONDS=1.0
CONVERSATION_TIMEOUT_SECONDS=25
```

---

## 3. Windows Audio Device Configuration

### Microphone Setup:
1. Open Windows **Settings** > **System** > **Sound** > **Input**.
2. Select your active microphone and ensure the input volume is at least **70%–80%**.
3. Under **Privacy & security** > **Microphone**, ensure **Microphone access** and **Let desktop apps access your microphone** are turned **ON**.

### Speaker Setup:
1. Open Windows **Settings** > **System** > **Sound** > **Output**.
2. Select your default speakers or headphones.
3. Test sound playback.

---

## 4. Conversation Modes

### Mode A: Text Mode
- Terminal typing works exactly as before. Voice output can be triggered manually via `/speak <text>`.
- Switch via CLI command: `/voice text` or say `"Jarvis, switch to text mode"`.

### Mode B: Push-to-Talk (Default)
- Type `/voice` or press Enter at prompt to begin recording.
- JARVIS displays `[JARVIS] 🎙️ Listening... (Speak now)`.
- Speak your command (e.g. `"What time is it?"` or `"Create a folder named Project"`).
- JARVIS transcribes, processes the request through the agent, and speaks the answer aloud.

### Mode C: Continuous Conversation Mode
- Type `/voice continuous` or say `"Jarvis, start listening"`.
- JARVIS continuously listens for consecutive questions with automatic silence detection.
- To pause or exit continuous mode, say `"Jarvis, stop listening"` or press `Ctrl+C`.

---

## 5. Voice Commands Quick Reference

| Spoken Phrase | Effect |
|---|---|
| `"Jarvis, stop speaking"` | Halts active speech synthesis immediately |
| `"Jarvis, repeat that"` | Re-speaks the previous assistant answer |
| `"Jarvis, start listening"` | Activates Continuous Conversation Mode |
| `"Jarvis, stop listening"` | Returns to Idle / Push-to-Talk |
| `"Jarvis, switch to text mode"` | Disables voice input, switches to keyboard |
| `"Jarvis, switch to voice mode"` | Activates Push-to-Talk voice input |
| `"Jarvis, what can you do?"` | Speaks a capability summary |

---

## 6. Troubleshooting

1. **`Microphone unavailable` / invalid input device**:
   - Verify that your microphone is plugged in and recognized under Windows Sound Settings.
   - Run `.\.venv\Scripts\python.exe -c "from voice.wake_word import list_input_devices; print(list_input_devices())"` to inspect detected input devices and set `VOICE_MICROPHONE_INDEX` if needed.

2. **Missing local STT / TTS / Wake-Word files**:
   - Run `.\.venv\Scripts\python.exe setup_local_models.py` once to download missing local models into `models/`.

3. **Run in-app voice diagnostics**:
   - Use `/voice status` and `/voice test` inside the CLI.
