"""CRT scanline + grid overlay.

Two layers, both transparent-to-input:

1. A faint cyan grid drawn behind content (call ``GridBackground``).
2. Horizontal CRT scanlines painted over content (call ``ScanlineOverlay``).

Together they sell the "deck of a Stark workshop console" feel without
hurting readability.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme


class GridBackground(QWidget):
    """Behind everything. Paints a faint 1px cyan grid."""

    SPACING = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(theme.GRID_LINE)
        pen.setWidthF(1.0)
        p.setPen(pen)
        w, h = self.width(), self.height()
        s = self.SPACING
        x = 0
        while x < w:
            p.drawLine(x, 0, x, h)
            x += s
        y = 0
        while y < h:
            p.drawLine(0, y, w, y)
            y += s


class ScanlineOverlay(QWidget):
    """On top of content. Horizontal scanlines + soft vignette."""

    STEP = 3  # px between scanlines

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(theme.SCANLINE)
        pen.setWidthF(1.0)
        p.setPen(pen)
        w, h = self.width(), self.height()
        y = 0
        while y < h:
            p.drawLine(0, y, w, y)
            y += self.STEP

        # Subtle corner vignette so the eye anchors to center.
        p.setPen(Qt.NoPen)
        from PySide6.QtGui import QRadialGradient, QColor
        cx, cy = w / 2, h / 2
        grad = QRadialGradient(cx, cy, max(w, h) * 0.75)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.75, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 90))
        p.setBrush(grad)
        p.drawRect(QRectF(self.rect()))
