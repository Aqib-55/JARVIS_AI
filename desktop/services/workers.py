"""
Qt Background Workers & Thread-Safe Approval Bridge.

Ensures AI inference, Faster-Whisper STT, Piper TTS, and diagnostics never
block the PySide6 GUI event loop, and routes TaskExecutor approval callbacks
safely to a modal confirmation dialog on the main UI thread.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from desktop.services.ui_state import ToolApprovalRequest


class WorkerSignals(QObject):
    """Generic Qt signals for QRunnable tasks."""
    finished = Signal(object)
    error = Signal(str)
    chunk = Signal(str)


class CallableWorker(QRunnable):
    """Execute any backend callable safely inside QThreadPool."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            res = self._fn(*self._args, **self._kwargs)
            try:
                self.signals.finished.emit(res)
            except RuntimeError:
                pass
        except Exception as exc:
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:
                pass


class GuiApprovalBridge(QObject):
    """
    Synchronizes worker-thread TaskExecutor approval requests with the GUI thread.

    Worker thread calls `request_approval(step, check)` -> blocks on an Event ->
    main GUI thread displays ConfirmationDialog -> calls `resolve(req_id, approved)` ->
    worker thread resumes and returns bool to TaskExecutor.
    """

    approval_requested = Signal(str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[threading.Event, list[bool]]] = {}

    def request_approval(self, req: ToolApprovalRequest, timeout: float = 120.0) -> bool:
        req_id = uuid.uuid4().hex
        ev = threading.Event()
        holder = [False]
        with self._lock:
            self._pending[req_id] = (ev, holder)

        self.approval_requested.emit(req_id, req)
        approved = False
        if ev.wait(timeout=timeout):
            approved = holder[0]

        with self._lock:
            self._pending.pop(req_id, None)
        return approved

    def resolve(self, req_id: str, approved: bool) -> None:
        with self._lock:
            entry = self._pending.get(req_id)
        if entry is not None:
            ev, holder = entry
            holder[0] = bool(approved)
            ev.set()

    def cancel_all(self) -> None:
        with self._lock:
            entries = list(self._pending.values())
        for ev, holder in entries:
            holder[0] = False
            ev.set()
