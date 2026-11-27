"""Pure-Qt programmatic icon and Windows .ico generator for JARVIS AI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def create_jarvis_pixmap(size: int = 64) -> QPixmap:
    """Render a minimal futuristic cyan/blue waveform ring emblem."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = max(3.0, size * 0.08)
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    # Dark medallion center
    painter.setBrush(QColor("#0D1420"))
    painter.setPen(QPen(QColor("#42CBEF"), max(1.8, size * 0.055)))
    painter.drawEllipse(rect)

    # Inner subtle blue ring
    inner_m = size * 0.19
    inner_rect = QRectF(inner_m, inner_m, size - 2 * inner_m, size - 2 * inner_m)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#368DFF"), max(1.0, size * 0.025)))
    painter.drawEllipse(inner_rect)

    # Minimal 5-bar centered waveform
    cx = size / 2.0
    cy = size / 2.0
    heights = [0.16, 0.30, 0.42, 0.30, 0.16]
    spacing = size * 0.105
    bar_pen = QPen(QColor("#42CBEF"), max(1.6, size * 0.045), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(bar_pen)
    for idx, h_ratio in enumerate(heights):
        x = cx + (idx - 2) * spacing
        half_h = (size * h_ratio) / 2.0
        painter.drawLine(QPointF(x, cy - half_h), QPointF(x, cy + half_h))

    painter.end()
    return pixmap


def create_jarvis_icon() -> QIcon:
    """Create a multi-resolution QIcon for window title bar and taskbar."""
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(create_jarvis_pixmap(sz))
    return icon


def ensure_app_ico(output_path: Path) -> Path:
    """Save Windows .ico or .png icon for packaging and Windows taskbar use."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        fmt = "ICO" if output_path.suffix.lower() == ".ico" else None
        pixmap = create_jarvis_pixmap(256)
        if fmt:
            pixmap.save(str(output_path), fmt)
        else:
            pixmap.save(str(output_path))
    return output_path
