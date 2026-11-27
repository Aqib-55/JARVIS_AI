"""Pre-build verification & asset generator for JARVIS AI Windows Desktop packaging."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop.resources.icons.icon_factory import ensure_app_ico


def main() -> int:
    root = ROOT
    ico_path = root / "desktop" / "resources" / "icons" / "jarvis.ico"
    env_example = root / ".env.example"

    if not env_example.is_file():
        print(f"FAIL: Missing template file required for packaging: {env_example}", file=sys.stderr)
        return 1

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app  # keep Qt GUI context alive during offscreen pixmap/ICO rasterization

    try:
        generated = ensure_app_ico(ico_path)
    except Exception as exc:
        print(f"FAIL: Icon generation failed for {ico_path}: {exc}", file=sys.stderr)
        return 1

    if not generated.is_file() or generated.stat().st_size == 0:
        print(f"FAIL: Generated icon is missing or empty: {generated}", file=sys.stderr)
        return 1

    print(f"PASS: Icon ready at {generated} ({generated.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
