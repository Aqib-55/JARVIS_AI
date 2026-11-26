# JARVIS AI — Native Windows Desktop Application Setup & Packaging Guide

The JARVIS AI Desktop Application (`desktop_main.py`) provides a modern native Windows window built on **PySide6 (Qt 6)** that connects directly to the local Python JARVIS backend (`OllamaProvider` + `qwen3.5:4b`, `JarvisAgent`, `ToolRegistry`, `TaskExecutor`, SQLite `MemoryManager`, `VoiceController`, and `HandsFreeConversationManager`).

No web server, browser wrapper, Electron shell, or Node.js runtime is used.

---

## 1. Prerequisites & Environment

- Windows 10 or Windows 11
- Python 3.13 virtual environment (`.venv`)
- [Ollama](https://ollama.com) running locally with `qwen3.5:4b` pulled:
  ```powershell
  ollama pull qwen3.5:4b
  ```
- Local STT/TTS/Wake-word models downloaded via:
  ```powershell
  .\.venv\Scripts\python.exe setup_local_models.py
  ```
- PySide6 installed in `.venv`:
  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  ```

---

## 2. Launching the Desktop App vs. CLI

**Native Windows Desktop App:**
```powershell
.\.venv\Scripts\python.exe desktop_main.py
```

**Original Terminal CLI (fully preserved):**
```powershell
.\.venv\Scripts\python.exe main.py
```

### Desktop Layout & Views
- **Overview (`DashboardPage`):** Displays real-time health cards (`AI Engine`, `Ollama Connection`, `Voice Recognition`, `Speech Generation`, `Wake-Word Detection`, `Memory Database`) and quick-action buttons (`Open Chat`, `Start Voice`, `Stop Voice`, `Run Diagnostics`, `View Tools`).
- **Chat (`ChatPage`):** Streaming conversation view with rendered Markdown/code blocks, copy-to-clipboard buttons, inline tool execution activity cards, composer bar (`Enter` to send, `Shift+Enter` for newline, Push-to-Talk mic button, Stop button), and the central circular `VoiceVisualizerWidget`.
- **Tools (`ToolsPage`):** Live view of all 26 registered tools grouped across 4 categories (`file_management`, `system_automation`, `productivity`, `development`), showing parameter schemas, 4-tier permission badges, live Emergency Stop status, and quick `Ask JARVIS` prompts.
- **Memory (`MemoryPage`):** Inspects SQLite long-term facts, non-sensitive user preferences, read-only conversation/task audit history, cross-domain search, and confirmed deletion for facts and preferences.
- **Settings (`SettingsPage`):** Shows live AI Engine, Voice & Wake-Word runtime settings, microphone device selection, threshold/timeout adjustments for the active session, Voice Output toggle, and full hardware diagnostics (`Run Diagnostics`).

---

## 3. Privacy & Safety Behavior

- **Explicit Voice Configuration:** Hands-free wake monitoring starts on launch only when `VOICE_INPUT_ENABLED=true`, `WAKE_WORD_ENABLED=true`, and `VOICE_MODE != text` in `.env` / settings.
- **Clean Shutdown:** Closing the desktop window stops active audio streams (`HandsFreeConversationManager.stop()` and `VoiceController`), cancels pending approval waits, waits for `QThreadPool` workers, and ends the SQLite conversation session cleanly.
- **Emergency Stop:** The persistent Topbar **Emergency Stop** toggle immediately halts active voice monitoring and blocks all tool executions via `PermissionManager`.
- **4-Tier Confirmation Modal:** Whenever `TaskExecutor` runs a Level 2 or Level 3 tool, `GuiApprovalBridge` pauses the worker thread and prompts `ConfirmationDialog` on the main GUI thread displaying tool name, description, policy reason, and validated parameters (`Approve Execution` vs. `Reject`).

---

## 4. Packaging Evaluation (`pyside6-deploy`)

JARVIS includes a configured `pysidedeploy.spec` targeting **directory-style standalone packaging** (`mode = standalone`, entry point `desktop_main.py`, custom Windows icon `desktop/resources/icons/jarvis.ico`) with `models/`, `data/`, `logs/`, `recordings/`, `artifacts/`, and `tests/` excluded.

To build a standalone folder distribution on a Windows machine equipped with Visual Studio C++ Build Tools (MSVC `cl.exe` / `dumpbin`) or MinGW64 + `Nuitka==4.1.1`:

```powershell
.\.venv\Scripts\python.exe -m pip install Nuitka==4.1.1
.\.venv\Scripts\pyside6-deploy.exe -c pysidedeploy.spec
```

> **Important Packaging Rule:** Keep `models/`, `data/jarvis.db`, and `.env` outside the compiled bundle directory (or configure paths alongside the executable) so large AI weights and local user data are never baked into build artifacts.

---

## 5. Desktop Verification Tests

```powershell
# Desktop UI, responsiveness, approval modal, tools, and SQLite tests
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_ui.py -v

# Full regression suite across backend + desktop UI
.\.venv\Scripts\python.exe -m pytest -v
```
