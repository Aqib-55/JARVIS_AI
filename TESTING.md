# JARVIS AI — Testing Guide & Verification Suite

Automated testing is mandatory for ensuring agent reliability, safety enforcement, and regression protection.

---

## 1. Running the Test Suite

Run all tests using the project virtual environment:

```powershell
& ".\.venv\Scripts\pytest.exe" -v
```

To run a specific module:
```powershell
& ".\.venv\Scripts\pytest.exe" tests/test_extended_tools.py -v
```

---

## 2. Test Suite Structure (104 Tests)

The test suite contains 104 tests organized across 10 modules:

| Test Module | Test Count | Domain Covered |
|---|---|---|
| `tests/test_calculator.py` | 16 | Arithmetic, operator precedence, powers, modulo, syntax errors, zero division |
| `tests/test_database.py` | 9 | SQLite initialization, table creation, foreign keys, task/session tracking |
| `tests/test_filesystem.py` | 19 | Path traversal protection, sandbox containment, folder/file creation, reading |
| `tests/test_permissions.py` | 5 | Baseline permission checks and approval workflows |
| `tests/test_registry.py` | 6 | Tool registration, parameter validation, schema export |
| `tests/test_settings.py` | 5 | API key presence, placeholder detection, length checking, config validation |
| `tests/test_extended_tools.py` | 16 | Extended file management (rename, copy, move, delete), system automation, productivity, development tools |
| `tests/test_enhanced_permissions.py` | 7 | 4-tier model (L0-L3), emergency stop triggers, directory allowlist boundaries |
| `tests/test_enhanced_planner.py` | 6 | Multi-step plans, dependency resolution, circular dependency blocking, retry counters |
| `tests/test_memory_manager.py` | 6 | Facts lifecycle, preferences, tool metrics, cross-domain search, context retrieval |
| `tests/test_agent_lifecycle.py` | 5 | Mock AI provider simulating single-turn, multi-turn autonomous loops, emergency stop halting, confirmation rejection |

---

## 3. Mock Testing Policy

All agent lifecycle and multi-turn execution tests use `MockProvider` to eliminate paid/network API calls during automated test runs.
Live API calls are restricted to deliberate manual tests and interactive user sessions.
