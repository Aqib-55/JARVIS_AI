"""Tests for runtime path resolution (source vs packaged Windows vs JARVIS_HOME) and packaging smoke mode."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from config.settings import Settings, _PROJECT_ROOT, is_packaged_app


def test_dev_mode_uses_project_root(monkeypatch):
    monkeypatch.delenv("JARVIS_HOME", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert is_packaged_app() is False
    s = Settings()
    assert s.IS_PACKAGED is False
    assert s.APP_DATA_DIR == _PROJECT_ROOT
    assert s.RESOURCE_ROOT == _PROJECT_ROOT
    assert s.DATA_DIR == _PROJECT_ROOT / "data"
    assert s.DB_PATH == _PROJECT_ROOT / "data" / "jarvis.db"
    assert s.WHISPER_MODEL_DIR == _PROJECT_ROOT / "models" / "stt"
    assert s.PIPER_MODEL_PATH == _PROJECT_ROOT / "models" / "tts"
    assert s.WAKE_WORD_MODEL_DIR == _PROJECT_ROOT / "models" / "wakeword"


def test_jarvis_home_override_and_preserve_existing_env(monkeypatch, tmp_path: Path):
    custom_home = tmp_path / "custom_jarvis_home"
    monkeypatch.setenv("JARVIS_HOME", str(custom_home))
    monkeypatch.setenv("WHISPER_MODEL_PATH", "models/stt/faster-whisper-base")
    monkeypatch.setenv("PIPER_MODEL_PATH", "models/tts")
    monkeypatch.setenv("WAKE_WORD_MODEL_DIR", "models/wakeword")

    s = Settings()
    assert s.APP_DATA_DIR == custom_home.resolve()
    assert s.RESOURCE_ROOT == _PROJECT_ROOT
    assert s.DATA_DIR == custom_home.resolve() / "data"
    assert s.DB_PATH == custom_home.resolve() / "data" / "jarvis.db"
    assert s.LOG_DIR == custom_home.resolve() / "logs"
    assert s.WORKSPACE_DIR == custom_home.resolve() / "workspace"
    assert s.WHISPER_MODEL_PATH == custom_home.resolve() / "models" / "stt" / "faster-whisper-base"
    assert s.PIPER_MODEL_PATH == custom_home.resolve() / "models" / "tts"
    assert s.WAKE_WORD_MODEL_DIR == custom_home.resolve() / "models" / "wakeword"
    assert s.ENV_FILE.is_file()

    # Existing .env must NEVER be overwritten on subsequent initializations
    sentinel = "# USER CUSTOMIZED CONFIG\nOLLAMA_MODEL=qwen3.5:4b\n"
    s.ENV_FILE.write_text(sentinel, encoding="utf-8")
    s2 = Settings()
    assert s2.ENV_FILE.read_text(encoding="utf-8") == sentinel


def test_packaged_windows_mode_uses_localappdata(monkeypatch, tmp_path: Path):
    local_app_data = tmp_path / "LocalAppData"
    bundle_dir = tmp_path / "temp_bundle_dir"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fake_exe = bundle_dir / "JARVIS_AI.exe"
    fake_exe.write_bytes(b"")

    monkeypatch.delenv("JARVIS_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("WHISPER_MODEL_PATH", "models/stt/faster-whisper-base")
    monkeypatch.setenv("PIPER_MODEL_PATH", "models/tts")
    monkeypatch.setenv("WAKE_WORD_MODEL_DIR", "models/wakeword")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    assert is_packaged_app() is True
    s = Settings()
    expected_root = local_app_data / "JARVIS_AI"
    assert s.IS_PACKAGED is True
    assert s.RESOURCE_ROOT == bundle_dir.resolve()
    assert s.APP_DATA_DIR == expected_root
    assert s.DB_PATH == expected_root / "data" / "jarvis.db"
    assert s.LOG_DIR == expected_root / "logs"
    assert s.WORKSPACE_DIR == expected_root / "workspace"
    assert s.WHISPER_MODEL_DIR == expected_root / "models" / "stt"
    assert s.PIPER_MODEL_PATH == expected_root / "models" / "tts"
    assert s.WAKE_WORD_MODEL_DIR == expected_root / "models" / "wakeword"
    assert not (bundle_dir / "data").exists()
    assert not (bundle_dir / "logs").exists()


def test_prebuild_icon_script_and_smoke_test_from_outside_cwd(tmp_path: Path):
    # 1. Pre-build script succeeds in offscreen mode
    prep = subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "scripts" / "prepare_desktop_build.py")],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert prep.returncode == 0, prep.stderr
    assert "PASS: Icon ready" in prep.stdout

    # 2. Smoke test passes from OUTSIDE repo root with isolated JARVIS_HOME
    outside_cwd = tmp_path / "outside_launch_dir"
    outside_cwd.mkdir(parents=True, exist_ok=True)
    smoke_home = tmp_path / "isolated_appdata"

    env = dict(os.environ)
    env["JARVIS_HOME"] = str(smoke_home)
    env["QT_QPA_PLATFORM"] = "offscreen"

    smoke = subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "desktop_main.py"), "--packaging-smoke-test"],
        cwd=str(outside_cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert smoke.returncode == 0, f"STDOUT: {smoke.stdout}\nSTDERR: {smoke.stderr}"
    assert "PASS: Packaging smoke test succeeded" in smoke.stdout
    assert (smoke_home / ".env").is_file()
    assert not (outside_cwd / "data").exists()
