# JARVIS AI — Voice Integration & Setup Guide (Phase 3)

This guide explains how to configure, test, and troubleshoot the microphone speech-to-text (STT) and speaker text-to-speech (TTS) subsystems on Windows.

---

## 1. Required Packages & Installation

All required audio dependencies are pre-configured in `requirements.txt`:

```powershell
# Activate your virtual environment
.\.venv\Scripts\Activate.ps1

# Install audio dependencies
pip install pyttsx3 SpeechRecognition PyAudio sounddevice numpy edge-tts
```

### Dependency Overview:
- `pyttsx3`: Offline Windows SAPI5 text-to-speech (low latency, zero internet requirement).
- `SpeechRecognition`: Audio capture, energy threshold adaptation, and ambient noise calibration.
- `PyAudio`: Direct PortAudio bindings for microphone streaming on Windows.
- `sounddevice` & `numpy`: Audio array handling and stream buffer inspection.
- `edge-tts`: Optional high-fidelity neural voices.

---

## 2. Configuration Settings

Voice settings are controlled via environment variables in `.env` (or configured via `config/settings.py`):

```env
# ------ Voice Subsystem Settings ------
VOICE_ENABLED=true
STT_ENGINE=speech_recognition     # Options: speech_recognition, faster_whisper, mock
TTS_ENGINE=pyttsx3                # Options: pyttsx3, edge_tts, mock
STT_LANGUAGE=en-US                # Primary spoken language
TTS_LANGUAGE=en
TTS_RATE=175                      # Speed in words per minute (100 - 300)
TTS_VOLUME=0.9                    # Volume from 0.0 to 1.0
TTS_VOICE=                        # Optional specific voice ID (e.g. David, Zira)
VOICE_MODE=push_to_talk           # Options: push_to_talk, continuous, text
SILENCE_TIMEOUT=2.0               # Silence detection threshold in seconds
ENERGY_THRESHOLD=300              # Microphone noise sensitivity
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

1. **`Microphone error: [Errno -9996] Invalid device`**:
   - Verify that your microphone is plugged in and recognized under Windows Sound Settings.
   - Run `python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"` to verify detected hardware devices.

2. **No speech recognized (`Audio received but speech could not be understood`)**:
   - Speak closer to the microphone.
   - Adjust `ENERGY_THRESHOLD=200` in `.env` if your microphone volume is quiet.

3. **`pyttsx3 voice engine error`**:
   - Ensure the Windows SAPI5 service is active. Windows 10/11 includes `Microsoft David` and `Microsoft Zira` by default.
