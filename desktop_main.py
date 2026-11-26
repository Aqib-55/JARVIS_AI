r"""
JARVIS AI — Native Windows Desktop Application Entry Point (PySide6 / Qt 6).

Run:
    .\.venv\Scripts\python.exe desktop_main.py

Existing CLI entry point remains preserved:
    .\.venv\Scripts\python.exe main.py
"""

import sys

from desktop.app import run_desktop_app


def main() -> int:
    return run_desktop_app(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
