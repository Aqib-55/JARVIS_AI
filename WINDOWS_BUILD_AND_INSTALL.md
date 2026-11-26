# JARVIS AI — Windows Executable Build & Installation Guide

This guide explains how to download, run, configure, troubleshoot, and rebuild the compiled Windows x64 standalone distribution of **JARVIS AI Desktop** (`PySide6 / Qt 6 + Nuitka + MSVC`).

> **Important:** The compiled Windows ZIP package contains the JARVIS AI desktop executable, Python 3.13 runtime, PySide6/Qt 6 libraries, and required DLLs. It does **not** bundle Ollama, `qwen3.5:4b`, Faster-Whisper weights, Piper voice weights, openWakeWord ONNX weights, `.env`, or any SQLite databases. Those remain local runtime prerequisites on your PC.

---

## 1. Download from GitHub Actions

1. Open the repository on GitHub (`Aqib-55/JARVIS_AI`) and click the **Actions** tab.
2. Select the **Build JARVIS AI Windows x64 Desktop** workflow (or the latest run on branch `feature/complete-local-ai-migration`).
3. Scroll to the **Artifacts** section at the bottom of the completed run.
4. Download **`JARVIS_AI-Windows-x64`**.

---

## 2. Extract and Launch JARVIS

1. Right-click `JARVIS_AI-Windows-x64.zip` and choose **Extract All…** into a permanent folder (for example, `C:\Users\<You>\Apps\JARVIS_AI\`).
   - Do **not** launch the `.exe` directly from inside a ZIP preview window; the `.exe` needs access to the DLLs and `PySide6\plugins` beside it.
2. Open the extracted `JARVIS_AI\` folder and run the executable (for example `JARVIS_AI.exe` or `desktop_main.exe`, check `README_FIRST_RUN.txt` inside the extracted folder for the exact binary name).

---

## 3. Persistent User Data & Configuration Paths

When running the compiled Windows executable, JARVIS stores all writable user files **outside** the executable folder under:

```text
%LOCALAPPDATA%\JARVIS_AI\
├── .env                  # Created from .env.example on first launch (never overwritten)
├── data\
│   └── jarvis.db         # SQLite memory, facts, preferences & task audit logs
├── logs\
│   └── jarvis_desktop.log
├── workspace\            # Sandboxed folder for all file-management tools
├── recordings\           # Temporary voice captures
└── models\
    ├── stt\              # faster-whisper-base\
    ├── tts\              # en_GB-alan-medium.onnx & .onnx.json
    └── wakeword\         # hey_jarvis_v0.1.onnx, melspectrogram.onnx, embedding_model.onnx
```

You can override this location cleanly by setting environment variable `JARVIS_HOME` before launching the executable.

---

## 4. Install Runtime Prerequisites (Ollama + Local Models)

### A. Ollama & `qwen3.5:4b`
1. Download and install [Ollama for Windows](https://ollama.com).
2. Open PowerShell and pull the configured local model:
   ```powershell
   ollama pull qwen3.5:4b
   ```
3. Ensure Ollama is running (`http://127.0.0.1:11434`). JARVIS Settings defaults to `LOCAL_AI_ONLY=true` and `AI_PROVIDER=ollama`.

### B. Faster-Whisper, Piper TTS & openWakeWord Models
To enable local voice input, neural speech output, and `"Hey JARVIS"` wake-word detection:

- **Option 1 (Source setup script targeting packaged directory):**
  ```powershell
  $env:JARVIS_HOME = "$env:LOCALAPPDATA\JARVIS_AI"
  .\.venv\Scripts\python.exe setup_local_models.py
  ```
- **Option 2 (Manual placement):** Copy your existing `models\stt\faster-whisper-base\`, `models\tts\en_GB-alan-medium.onnx*`, and `models\wakeword\*.onnx` folders into `%LOCALAPPDATA%\JARVIS_AI\models\`.

Even without local voice models installed yet, the desktop app opens cleanly, reports missing speech engines honestly on the **Overview** cards, and supports full text chat & tools via Ollama.

---

## 5. Packaging Smoke Test

To verify Qt runtime initialization, bundled Python/PySide6 imports, and writable `%LOCALAPPDATA%\JARVIS_AI` directory creation without requiring Ollama or microphone hardware:

```powershell
.\<executable_name>.exe --packaging-smoke-test
```

Expected output ends with `PASS: Packaging smoke test succeeded ...` and exit code `0`.

---

## 6. Troubleshooting

- **Missing DLL / VCRUNTIME errors:** Install the latest [Microsoft Visual C++ Redistributable (x64)](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist). Always extract the entire ZIP folder so Qt/MSVC runtime DLLs stay beside the `.exe`.
- **Ollama Offline on Overview card:** Run `ollama serve` (or launch the Ollama desktop tray app) and verify `ollama list` includes `qwen3.5:4b`.
- **STT / TTS / Wake-Word Unavailable:** Confirm model files exist under `%LOCALAPPDATA%\JARVIS_AI\models\` (or check `%LOCALAPPDATA%\JARVIS_AI\.env` for custom `WHISPER_MODEL_PATH`, `PIPER_MODEL_PATH`, or `WAKE_WORD_MODEL_DIR` values).

---

## 7. Rebuilding Locally (Windows x64 with Visual Studio 2022 MSVC)

Prerequisites:
- Windows 10/11 64-bit
- Python 3.13 (x64)
- Visual Studio 2022 Build Tools with C++ x64 workload (`cl.exe` and `dumpbin.exe` initialized via **x64 Native Tools Command Prompt for VS 2022**)

Build steps:
```powershell
python -m pip install -r requirements.txt
python -m pip install "PySide6==6.12.0" "Nuitka==4.1.1"
python scripts/prepare_desktop_build.py
pyside6-deploy -c pysidedeploy.spec --force --mode standalone --verbose
```
