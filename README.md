# JARVIS AI — Personal AI Assistant and Task Execution Agent

A production-minded personal AI assistant and task execution agent built in Python for Windows. JARVIS understands natural language instructions via text or voice, constructs multi-step dependency-aware plans, enforces a 4-tier security model, safely executes sandboxed tools across files, system metrics, productivity, and development, and speaks natural voice responses aloud.

---

## Architecture Overview

```
USER / CLI (interface/cli.py) ◄──────► HANDS-FREE MANAGER (voice/conversation_manager.py)
  │                                      ├── Wake Word & VAD (voice/wake_word.py)
  │                                      └── Voice Controller (voice/voice_controller.py)
  │                                            ├── STT Engine (voice/speech_to_text.py — Faster-Whisper)
  │                                            └── TTS Engine (voice/text_to_speech.py — Piper TTS)
  ▼
JARVIS AGENT (core/agent.py)
  ├── Conversation Manager (core/conversation.py)
  ├── Task Planner (core/planner.py)
  ├── Provider Manager (providers/base.py, ollama.py, factory.py)
  ├── Tool Registry (tools/registry.py — 26 tools across 4 categories)
  │     ├── File Management (tools/filesystem.py)
  │     ├── System Automation (tools/system_automation.py)
  │     ├── Productivity (tools/productivity.py, calculator.py, datetime_tool.py)
  │     └── Development Assistance (tools/development.py)
  ├── Permission Manager (core/permissions.py — 4-Tier Security & Emergency Stop)
  ├── Task Executor (core/executor.py — Dependency Execution & Timeouts)
  └── Memory Manager (memory/database.py, memory_manager.py, task_history.py, conversation_history.py)
```

---

## Directory Structure

```
D:\JARVIS_AI\
├── main.py                     # Application entry point
├── requirements.txt            # Project dependencies
├── .env                        # Local secrets (never committed)
├── .env.example                # Configuration template
├── .gitignore                  # Git ignore rules
├── README.md                   # System documentation
├── ARCHITECTURE.md             # Detailed architectural overview
├── TOOL_DOCUMENTATION.md       # Tool catalog & parameter schemas
├── SECURITY.md                 # Security policies & permission model
├── TESTING.md                  # Test suite guide & coverage
├── VOICE_SETUP.md              # Voice configuration and setup guide
├── VOICE_ARCHITECTURE.md       # Voice subsystem architecture & state machine
├── VOICE_TESTING.md            # Voice automated & hardware test guide
├── DEVELOPMENT_PROGRESS.md     # Milestone tracking
├── PHASE_2_AUDIT.md            # Architectural audit
├── PHASE_2_COMPLETION_REPORT.md# Phase 2 verification report
├── PHASE_3_COMPLETION_REPORT.md# Phase 3 verification report
├── config/
│   ├── __init__.py
│   └── settings.py             # Centralized settings via python-dotenv & os.getenv
├── core/
│   ├── __init__.py
│   ├── agent.py                # Multi-turn autonomous task orchestrator
│   ├── conversation.py         # Session context & sliding window
│   ├── executor.py             # Dependency-aware tool execution engine
│   ├── permissions.py          # 4-tier security model & emergency stop
│   └── planner.py              # Dependency graphs & status tracking
├── voice/
│   ├── __init__.py
│   ├── speech_to_text.py       # Microphone audio capture, noise reduction & STT
│   ├── text_to_speech.py       # Markdown sanitization & SAPI5/Edge TTS
│   └── voice_controller.py     # AudioState machine, voice commands & conversation modes
├── providers/
│   ├── __init__.py
│   ├── base.py                 # Abstract AI provider interface
│   ├── factory.py              # Provider factory
│   └── gemini.py               # Google GenAI SDK (google-genai) with backoff retry
├── tools/
│   ├── __init__.py             # Tool definitions, schemas, categories & permissions
│   ├── registry.py             # Categorized tool discovery, timeout & dispatch
│   ├── filesystem.py           # Sandboxed file management (list, create, copy, move, delete)
│   ├── system_automation.py    # System specs, resource stats, processes, app launching
│   ├── productivity.py         # Notes, reminders, tasks, summarization
│   ├── development.py          # Python syntax validation, code viewer, error explainer, script runner
│   ├── calculator.py           # Safe AST-based math evaluator
│   └── datetime_tool.py        # Date/time/timezone tool
├── memory/
│   ├── __init__.py
│   ├── database.py             # SQLite schema v2 (WAL mode, foreign keys)
│   ├── memory_manager.py       # Facts, preferences, metrics, cross-domain search
│   ├── conversation_history.py # Session chat persistence
│   └── task_history.py         # Task execution audit logs
├── interface/
│   ├── __init__.py
│   └── cli.py                  # Interactive CLI with text and voice commands
├── workspace/                  # Sandboxed directory for all file operations
├── data/                       # Local SQLite database (jarvis.db)
├── logs/                       # Application logs (jarvis.log)
└── tests/                      # Automated unit test suite (116 tests)
```

---

## Quickstart & Installation

### 1. Virtual Environment & Dependencies
JARVIS runs on Python 3.13 inside `.venv`:

```powershell
# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 2. Download Local AI & Voice Models (One-Time Setup)
Ensure [Ollama](https://ollama.com) is installed and pull the local model:
```powershell
ollama pull qwen3.5:4b
```

Download all required local STT, TTS, and Wake-Word models into `models/`:
```powershell
.\.venv\Scripts\python.exe setup_local_models.py
```

### 3. Configure Environment
Copy `.env.example` to `.env`:
```env
AI_PROVIDER=ollama
LOCAL_AI_ONLY=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b

# Voice & Hands-Free Wake Word
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
Say **"Hey JARVIS"** to activate hands-free mode, speak requests, ask follow-up questions without repeating the wake phrase, or say **"Goodbye JARVIS"** to return to wake-word listening.

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

See [HANDS_FREE_VOICE_SETUP.md](HANDS_FREE_VOICE_SETUP.md) for detailed microphone configuration, licensing notes (openWakeWord CC BY-NC-SA 4.0 / Piper GPL), privacy guarantees, and offline verification.

---

## Automated Test Verification

Run the automated test suite:

```powershell
& ".\.venv\Scripts\pytest.exe" -v
```
