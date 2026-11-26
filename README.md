# JARVIS AI — Local Personal AI & Hands-Free Voice Assistant

A 100% local, privacy-focused personal AI task-execution assistant for Windows and Python 3.13. JARVIS runs completely offline for AI reasoning (Ollama + Qwen 3.5 4B), wake-word detection (openWakeWord), speech recognition (Faster-Whisper), speech synthesis (Piper TTS), and persistent memory (SQLite), while enforcing a 4-tier security model across 26 sandboxed tools.

---

## Architecture Overview

```text
JARVIS AI
    |
    +-- Ollama
    |      |
    |      +-- Qwen 3.5 4B
    |
    +-- Voice
    |      |
    |      +-- openWakeWord
    |      +-- Faster-Whisper
    |      +-- Piper TTS
    |      +-- Conversation Manager
    |
    +-- Core Agent
    |      |
    |      +-- Planner
    |      +-- Tool Registry
    |      +-- Executor
    |      +-- Safety Controls
    |
    +-- Memory
           |
           +-- SQLite
```

---

## Directory Structure

```text
D:\JARVIS_AI\
├── main.py                          # Application entry point
├── requirements.txt                 # Local AI, voice, and test dependencies
├── setup_local_models.py            # One-time setup for Whisper, Piper, and openWakeWord models
├── pytest.ini                       # Pytest configuration
├── .env                             # Local runtime configuration (never committed)
├── .env.example                     # Configuration template
├── .gitignore                       # Excludes .env, .venv/, models/, *.onnx, *.db, logs/
├── README.md                        # System documentation
├── LOCAL_AI_SETUP.md                # Local Ollama AI & model setup guide
├── HANDS_FREE_VOICE_SETUP.md        # Hands-free wake-word, mic, privacy & licensing guide
├── ARCHITECTURE.md                  # Detailed core architectural overview
├── TOOL_DOCUMENTATION.md            # Tool catalog & parameter schemas
├── SECURITY.md                      # Security policies & permission model
├── TESTING.md                       # Test suite guide & coverage
├── VOICE_SETUP.md                   # Voice configuration & troubleshooting guide
├── VOICE_ARCHITECTURE.md            # Voice pipeline & state machine documentation
├── config/
│   ├── __init__.py
│   └── settings.py                  # Validated settings via python-dotenv & os.getenv
├── core/
│   ├── __init__.py
│   ├── agent.py                     # Multi-turn autonomous task orchestrator
│   ├── conversation.py              # Session context & sliding window
│   ├── executor.py                  # Dependency-aware tool execution engine
│   ├── permissions.py               # 4-tier security model & emergency stop
│   └── planner.py                   # Dependency graphs & status tracking
├── providers/
│   ├── __init__.py
│   ├── base.py                      # Abstract AI provider interface
│   ├── factory.py                   # Provider factory (Ollama only; LOCAL_AI_ONLY enforced)
│   └── ollama.py                    # Local Ollama HTTP client (native tool calling & streaming)
├── voice/
│   ├── __init__.py
│   ├── wake_word.py                 # openWakeWord ONNX detector, single mic stream, Silero VAD
│   ├── conversation_manager.py      # Hands-free state machine & follow-up continuity
│   ├── speech_to_text.py            # Local Faster-Whisper CPU INT8 transcription
│   ├── text_to_speech.py            # Local Piper neural TTS & text sanitization
│   └── voice_controller.py          # AudioState machine & voice commands
├── tools/
│   ├── __init__.py                  # Tool definitions, schemas, categories & permissions
│   ├── registry.py                  # Categorized tool discovery, timeout & dispatch
│   ├── filesystem.py                # Sandboxed file management (list, create, copy, move, delete)
│   ├── system_automation.py         # System specs, resource stats, processes, app/web launching
│   ├── productivity.py              # Notes, reminders, tasks, summarization
│   ├── development.py               # Python syntax checks, code reader, script & command runner
│   ├── calculator.py                # Safe AST-based math evaluator
│   └── datetime_tool.py             # Date/time/timezone tool
├── memory/
│   ├── __init__.py
│   ├── database.py                  # SQLite schema v2 (WAL mode, foreign keys)
│   ├── memory_manager.py            # Facts, preferences, metrics, cross-domain search
│   ├── conversation_history.py      # Session chat persistence
│   └── task_history.py              # Task execution audit logs
├── interface/
│   ├── __init__.py
│   └── cli.py                       # Interactive streaming CLI with hands-free & PTT voice
├── models/                          # Local downloaded model weights (gitignored)
├── workspace/                       # Sandboxed directory for all file operations
├── data/                            # Local SQLite database (jarvis.db, gitignored)
├── logs/                            # Application logs (jarvis.log, gitignored)
└── tests/                           # Automated pytest suite
```

---

## Quickstart & Installation

### 1. Virtual Environment & Dependencies
JARVIS runs on Python 3.13 inside `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Local AI & Voice Models (One-Time Setup)
Install [Ollama](https://ollama.com) and pull Qwen 3.5 4B:
```powershell
ollama pull qwen3.5:4b
```

Download all required local STT (`Systran/faster-whisper-base`), TTS (`en_GB-alan-medium`), and Wake-Word (`hey_jarvis_v0.1.onnx` + shared ONNX assets) into `models/`:
```powershell
.\.venv\Scripts\python.exe setup_local_models.py
```

### 3. Configure Environment
Copy `.env.example` to `.env` (no cloud API keys required):
```env
AI_PROVIDER=ollama
LOCAL_AI_ONLY=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_KEEP_ALIVE=10m
OLLAMA_NUM_CTX=8192
OLLAMA_STREAM=true

VOICE_ENABLED=true
VOICE_INPUT_ENABLED=true
VOICE_OUTPUT_ENABLED=true
WAKE_WORD_ENABLED=true
WAKE_WORD_PHRASE=hey jarvis
WAKE_WORD_THRESHOLD=0.5
CONVERSATION_TIMEOUT_SECONDS=25
VOICE_MODE=hands_free
```

### 4. Launch JARVIS
```powershell
.\.venv\Scripts\python.exe main.py
```
Say **"Hey JARVIS"** to activate hands-free mode, speak requests, ask follow-up questions without repeating the wake phrase, or say **"Goodbye JARVIS"** to return to idle wake-word detection.

### In-Session CLI Commands
- `/voice on` — Enable hands-free wake-word & microphone monitoring
- `/voice off` — Stop microphone monitoring completely
- `/voice status` — Show live wake-word, microphone, STT, and TTS status
- `/voice test` — Run diagnostics on microphone, openWakeWord, Faster-Whisper, and Piper
- `/voice` or `/voice ptt` — Trigger single Push-to-Talk voice input
- `/voice text` — Switch to Text-only Mode
- `/speak <text>` — Speak custom text aloud via Piper TTS
- `/tools` — View all 26 registered tools organized across the 4 categories
- `/status` — View connectivity, audio subsystem state, and emergency stop status
- `/history` — View recent tasks and execution outcomes
- `/memory [query]` — View stored facts or search across past notes/tasks
- `/stop` — **Emergency Stop**: Instantly halts all active tool executions and speech
- `/resume` — Clears Emergency Stop and restores normal execution
- `/clear` — Clear the conversation window and begin a new session
- `/exit` — Shut down JARVIS safely

See [LOCAL_AI_SETUP.md](LOCAL_AI_SETUP.md) and [HANDS_FREE_VOICE_SETUP.md](HANDS_FREE_VOICE_SETUP.md) for full details.

---

## Offline Capabilities & Tool Notes
- **100% Local / Offline:** Ollama LLM (`qwen3.5:4b`), openWakeWord, Silero VAD, Faster-Whisper STT, Piper TTS, SQLite memory, and 25 of 26 tools (file management, calculator, datetime, system specs/processes/local apps, productivity, and local Python tools).
- **Network-Dependent Tool:** `open_website` opens an HTTP/HTTPS URL in your default browser and intentionally requires internet connectivity for remote websites.

---

## Automated Test Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
