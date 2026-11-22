# JARVIS AI — System Architecture (Phase 2)

## 1. High-Level Architecture Diagram

```
                     ┌──────────────────────────────┐
                     │          USER / CLI          │
                     │      (interface/cli.py)      │
                     └──────────────┬───────────────┘
                                    │ Instructions / Approval
                                    ▼
                     ┌──────────────────────────────┐
                     │         JARVIS AGENT         │
                     │       (core/agent.py)        │
                     └──────────────┬───────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   Conversation   │      │   Task Planner   │      │  Memory Manager  │
│     Manager      │      │ (core/planner.py)│      │  (memory/...)    │
│(core/conversat..)│      └─────────┬────────┘      └─────────┬────────┘
└──────────────────┘                │                         │
                                    ▼                         │
                          ┌──────────────────┐                │
                          │  Task Executor   │                │
                          │(core/executor.py)│                │
                          └─────────┬────────┘                │
                                    │                         │
         ┌──────────────────────────┴──────────┐              │
         ▼                                     ▼              ▼
┌──────────────────┐                 ┌──────────────────┐ ┌──────────┐
│Permission Manager│                 │  Tool Registry   │ │  SQLite  │
│ (4-Tier Model &  │                 │ (Categorized &   │ │ Database │
│ Emergency Stop)  │                 │ Timeout Enforced)│ │ (v2 WAL) │
└──────────────────┘                 └────────┬─────────┘ └──────────┘
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              ▼                               ▼                               ▼
    ┌───────────────────┐           ┌───────────────────┐           ┌───────────────────┐
    │  File Management  │           │ System Automation │           │   Productivity    │
    │  (tools/fs.py)    │           │ (tools/sys_auto..)│           │ (tools/product..) │
    └───────────────────┘           └───────────────────┘           └───────────────────┘
```

---

## 2. Core Subsystems

### 2.1 Agent Core (`core/agent.py`)
- Acts as the central orchestrator coordinating provider interactions, planning, execution, and persistent memory.
- Implements an **autonomous multi-step execution loop**:
  - Turns 1..N: Model inspects current environment, executes tool, receives observation.
  - Model requests next tool or completes task with structured report.
  - Bounded by `max_autonomous_turns = 6` to avoid runaway token consumption or execution loops.
- Intercepts and enforces **Global Emergency Stop** prior to each turn.
- Automatically queries `MemoryManager` to inject relevant user preferences and historical facts into the prompt without blowing up the context window.

### 2.2 Task Planner (`core/planner.py`)
- Converts model requests and higher-level natural language instructions into structured `TaskPlan` instances.
- Manages **task dependency graphs**: Step 2 can depend on Step 1 (`depends_on: [1]`).
- Supports lifecycle statuses:
  - `PENDING`: Initial state waiting for execution.
  - `PLANNING`: Plan is being constructed or validated.
  - `RUNNING`: Execution is currently in progress.
  - `WAITING_FOR_APPROVAL`: Paused awaiting user confirmation.
  - `COMPLETED`: Finished successfully.
  - `FAILED`: Step encountered an error.
  - `CANCELLED`: Execution halted manually or via emergency stop.
- Enforces retry strategies with limits (`max_retries`, `retry_delay_seconds`).

### 2.3 Task Executor (`core/executor.py`)
- Iteratively resolves ready steps from the dependency graph.
- Dispatches execution to the registered tool with execution timeouts.
- Catches runtime errors, records step audit logs, and handles downstream dependent step skipping.

### 2.4 Security & Permissions (`core/permissions.py`)
- Standardized **4-Tier Risk Model**:
  - **Level 0 (Read-Only)**: Inspection, system stats, file reads. Always allowed.
  - **Level 1 (Low Risk)**: Additive, non-destructive actions (creating folders, notes, files).
  - **Level 2 (Moderate Risk)**: Modifications, renames, moves, script runs. Requires user confirmation.
  - **Level 3 (High Risk)**: Destructive actions (deletions, administrative changes). Requires explicit confirmation.
- **Global Emergency Stop**: A kill switch (`/stop`) that instantly blocks all executions.
- **Directory Allowlists**: Path traversal prevention strictly restricting filesystem tools to approved roots.

### 2.5 Tool Architecture (`tools/`)
- Tools are organized into 4 distinct categories:
  - `FILE_MANAGEMENT`
  - `SYSTEM_AUTOMATION`
  - `PRODUCTIVITY`
  - `DEVELOPMENT`
- Each tool definition enforces parameter schemas, permission level, and a per-tool timeout (default 30s) running in isolated thread pools.

### 2.6 Memory & SQLite (`memory/`)
- SQLite database configured with Write-Ahead Logging (`WAL`) mode and foreign key integrity.
- Stores:
  - `conversations` & `messages` (session-based sliding window)
  - `tasks` & `task_steps` (audit history)
  - `tool_executions` (audit trail)
  - `important_facts` (long-term memory)
  - `notes`, `reminders`, `todo_items`
  - `tool_usage_metrics` (call frequency and success rates)
  - `user_preferences` (key-value settings)
