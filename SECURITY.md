# JARVIS AI — Security Model & Policies (Phase 2)

Security is foundational to JARVIS AI. The system is designed to execute tasks autonomously without risking user data, system stability, or credential exposure.

---

## 1. The 4-Tier Permission Model

Every tool has an explicit permission classification defined in its `ToolDefinition`.

| Level | Risk Category | Description | Approval Required? | Example Actions |
|---|---|---|---|---|
| **Level 0** | **Read-Only** | Non-mutating queries, inspections, read operations | **No** | `get_system_info`, `read_file`, `calculator`, `list_files`, `get_resource_usage` |
| **Level 1** | **Low Risk** | Reversible, safe additions inside workspace | **No** | `create_folder`, `create_file`, `manage_notes` (create), `open_website` |
| **Level 2** | **Moderate Risk** | Mutations, renames, file moves, running sandboxed scripts | **Yes** | `move_file`, `rename_file`, `open_application`, `run_python_script`, `execute_approved_command` |
| **Level 3** | **High Risk** | Irreversible, destructive actions | **Yes (Explicit)** | `delete_file` (requires `confirm=True` and user approval) |

---

## 2. Global Emergency Stop Mechanism

JARVIS incorporates a hard fail-safe:
- Can be activated at any time via the `/stop` CLI command or `agent.trigger_emergency_stop()`.
- When engaged, **all tool executions are instantly blocked**, including Level 0 read operations.
- Any actively pending task plan is transitioned to `CANCELLED`.
- To resume operations, the user must explicitly run `/resume`.

---

## 3. Directory Allowlists & Path Traversal Defense

1. **Strict Sandboxing**:
   - By default, all filesystem operations are confined strictly to `D:\JARVIS_AI\workspace\`.
2. **Canonical Resolution**:
   - Every user-supplied path is resolved via `Path.resolve()`.
   - The path is validated against the authorized directory tree using `path.relative_to(allowed_root)`.
   - Any attempt to escape via `..`, absolute drive paths (`C:\Windows\`), or symbolic links throws an immediate `AccessDenied` error.

---

## 4. Subprocess Execution Guardrails

1. **No Arbitrary Command Execution**:
   - JARVIS never exposes arbitrary `cmd.exe` or `powershell.exe` execution to AI models.
2. **Strict Whitelisting**:
   - Terminal execution is restricted strictly to an approved whitelist (`git status`, `python --version`, `pytest`, `pip list`, `dir`, `echo`, `hostname`, `whoami`).
3. **Execution Timeouts**:
   - Python script executions and subprocess calls enforce a hard timeout (15–30s) running in isolated thread pools.
4. **No Administrator Privileges**:
   - JARVIS does not elevate or run administrative commands.

---

## 5. Credential & Privacy Protection

1. **Environment Segregation & Zero Cloud AI Keys**:
   - JARVIS runs 100% locally using Ollama (`127.0.0.1:11434`), openWakeWord, Faster-Whisper, Piper TTS, and SQLite. No cloud LLM API keys are required.
   - `.env`, `.env.*`, and `*.env` are in `.gitignore`.
2. **Local-Only Mode Enforcement (`LOCAL_AI_ONLY=true`)**:
   - `config/settings.py`, `providers/factory.py`, `voice/speech_to_text.py`, and `voice/text_to_speech.py` reject external LLM hosts, Gemini, or cloud STT/TTS services.
   - Idle wake-word microphone audio remains strictly in memory and is never saved to disk or transmitted externally.
3. **Database Privacy**:
   - Passwords, API keys, and sensitive tokens are never persisted to the SQLite memory database.
