# JARVIS AI — Local AI Setup Guide

## 1. Overview
JARVIS uses a 100% local AI and voice stack with **no cloud LLM, no Gemini API key, and no cloud STT/TTS fallback**:
- **AI Runtime & Model:** Ollama (`http://127.0.0.1:11434`) running `qwen3.5:4b`
- **Wake-Word Detection:** openWakeWord ONNX (`hey_jarvis_v0.1.onnx`)
- **Speech Recognition (STT):** Faster-Whisper (`Systran/faster-whisper-base`, CPU INT8)
- **Speech Synthesis (TTS):** Piper TTS (`en_GB-alan-medium`)
- **Persistent Memory:** SQLite (`data/jarvis.db`)

---

## 2. Ollama Setup

1. Install Ollama for Windows from https://ollama.com.
2. Pull the default model:
   ```powershell
   ollama pull qwen3.5:4b
   ```
3. Verify the model and service:
   ```powershell
   ollama list
   ollama show qwen3.5:4b
   ```
4. If Ollama is not already running in the background, start it:
   ```powershell
   ollama serve
   ```

---

## 3. Python Environment & Local Model Setup

Use the existing `.venv` (Python 3.13):
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Download all required local STT, TTS, and Wake-Word weights once into `models/`:
```powershell
.\.venv\Scripts\python.exe setup_local_models.py
```

Expected local model layout:
- `models/stt/faster-whisper-base/` (`config.json`, `model.bin`, `tokenizer.json`, `vocabulary.txt`)
- `models/tts/` (`en_GB-alan-medium.onnx`, `en_GB-alan-medium.onnx.json`)
- `models/wakeword/` (`hey_jarvis_v0.1.onnx`, `melspectrogram.onnx`, `embedding_model.onnx`)

JARVIS **never** downloads model weights automatically during normal startup or `/voice`.

---

## 4. Configuration (`.env`)

Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```

Recommended local settings:
```env
AI_PROVIDER=ollama
LOCAL_AI_ONLY=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_TIMEOUT=180
OLLAMA_KEEP_ALIVE=10m
OLLAMA_NUM_CTX=8192
OLLAMA_STREAM=true
MAX_CONVERSATION_HISTORY=12
```

When `LOCAL_AI_ONLY=true`:
- Only `AI_PROVIDER=ollama` and loopback addresses (`127.0.0.1`, `localhost`, `::1`) are allowed.
- Requests for cloud providers or cloud STT/TTS raise `RuntimeError`.

---

## 5. Offline vs Network-Dependent Tools
- **Local Tools (25 tools):** File management (`workspace/`), calculator, datetime, system specs/resources/processes, local app launcher, notes/reminders/tasks/summarization, and local Python dev tools run completely offline.
- **Network-Dependent Tool:** `open_website` opens URLs in your default web browser and requires internet access to load external sites.

---

## 6. Licensing Summary
- **openWakeWord library:** `Apache-2.0`; pretrained wake-word model (`hey_jarvis_v0.1.onnx`): **`CC-BY-NC-SA-4.0`** (non-commercial; replacement required for commercial redistribution).
- **Piper TTS (`piper-tts`):** GPL-licensed.
- **Faster-Whisper & Silero VAD:** MIT-licensed.
- **Qwen 3.5:** Apache-2.0.
