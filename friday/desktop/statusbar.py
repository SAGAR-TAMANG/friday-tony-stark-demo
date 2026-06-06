"""Top status strip — the always-on HUD breadcrumb.

  F.R.I.D.A.Y. ▸ ONLINE ▸ GPT-4O ▸ 14 TOOLS ▸ 18:42:07 UTC      ─  ✕

Click-drag anywhere in the strip moves the frameless window (handled by
the parent). The strip itself only paints + ticks the clock.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from . import theme


def _hud_label(text: str, color, size: float = 10.0, spacing: float = 2.0, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    weight = "600" if bold else "500"
    lbl.setStyleSheet(
        f"color: {color.name()}; "
        f"font-family: {theme.FONT_HUD}; "
        f"font-size: {size}px; "
        f"font-weight: {weight}; "
        f"letter-spacing: {spacing}px; "
        f"background: transparent;"
    )
    return lbl


class _TrafficLight(QPushButton):
    """macOS-style traffic-light dot — colored circle with hover glyph.

    Colors (Apple's reference values):
        close  #FF5F57 → glyph ✕
        min    #FEBC2E → glyph −
        zoom   #28C840 → glyph +

    Reveals the centered glyph on hover, mirroring the real Aqua controls.
    """

    SIZE = 13

    def __init__(self, kind: str):
        super().__init__()
        assert kind in ("close", "min", "zoom")
        self.kind = kind
        self.setFixedSize(self.SIZE + 2, self.SIZE + 2)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("background: transparent; border: none;")
        self._hover = False
        self._color = {
            "close": QColor("#FF5F57"),
            "min":   QColor("#FEBC2E"),
            "zoom":  QColor("#28C840"),
        }[kind]
        self._glyph = {"close": "✕", "min": "−", "zoom": "+"}[kind]

    def enterEvent(self, ev):
        self._hover = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self.update()
        super().leaveEvent(ev)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        cx, cy = r.width() / 2, r.height() / 2
        radius = self.SIZE / 2

        # Solid colored disk.
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(int(cx - radius), int(cy - radius), self.SIZE, self.SIZE)

        # Soft inner shading for depth.
        shade = QColor(0, 0, 0, 35)
        p.setBrush(shade)
        p.drawEllipse(
            int(cx - radius + 1), int(cy - radius + 1),
            self.SIZE - 2, self.SIZE - 2,
        )
        p.setBrush(self._color)
        p.drawEllipse(
            int(cx - radius + 0), int(cy - radius - 1),
            self.SIZE, self.SIZE - 2,
        )

        # Hover glyph — dark, centered.
        if self._hover:
            p.setPen(QColor(0, 0, 0, 200))
            from PySide6.QtGui import QFont
            f = QFont(theme.FONT_HUD.split(",")[0].strip().strip("'\""))
            f.setPixelSize(10)
            f.setWeight(QFont.Bold)
            p.setFont(f)
            p.drawText(r, Qt.AlignCenter, self._glyph)


class StatusBar(QWidget):
    """Top HUD strip with macOS-style traffic-light controls (top-right)."""

    minimize_requested = Signal()
    close_requested = Signal()
    zoom_requested = Signal()

    def __init__(self, *, model_label: str, tool_count: int, parent=None):
        super().__init__(parent)
        self.setFixedHeight(theme.TOPBAR_H)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("StatusBar")
        self.setStyleSheet(
            f"#StatusBar {{ background: rgba(2,4,8,210); "
            f"border-bottom: 1px solid rgba(0,180,210,80); }}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 8, 0)
        row.setSpacing(10)

        sep = lambda: _hud_label("▸", theme.TEXT_FAINT, size=9.5, spacing=0)

        self._brand = _hud_label("F.R.I.D.A.Y.", theme.HUD_ICE, size=10.5, spacing=4, bold=True)
        self._mode  = _hud_label("ONLINE",      theme.HUD_GREEN, size=10, spacing=3, bold=True)
        self._model = _hud_label(model_label.upper(), theme.HUD_CYAN_DIM, size=10, spacing=2)
        self._tools = _hud_label(f"{tool_count} TOOLS", theme.TEXT_DIM, size=10, spacing=2)
        self._clock = _hud_label("--:--:-- UTC", theme.TEXT_DIM, size=10, spacing=2)

        row.addWidget(self._brand)
        row.addWidget(sep())
        row.addWidget(self._mode)
        row.addWidget(sep())
        row.addWidget(self._model)
        row.addWidget(sep())
        row.addWidget(self._tools)
        row.addStretch(1)
        # Heartbeat dot — visible proof the event loop is alive.
        self._beat_dot = _hud_label("●", theme.HUD_GREEN, size=8, spacing=0)
        row.addWidget(self._beat_dot)
        row.addWidget(self._clock)
        row.addSpacing(12)

        # macOS traffic-light buttons (top-right per user request).
        btn_zoom  = _TrafficLight("zoom")
        btn_min   = _TrafficLight("min")
        btn_close = _TrafficLight("close")
        btn_zoom.clicked.connect(self.zoom_requested.emit)
        btn_min.clicked.connect(self.minimize_requested.emit)
        btn_close.clicked.connect(self.close_requested.emit)
        row.addWidget(btn_zoom)
        row.addSpacing(2)
        row.addWidget(btn_min)
        row.addSpacing(2)
        row.addWidget(btn_close)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_clock)
        self._tick.start(1000)
        self._refresh_clock()

        # Heartbeat timer — flip dot visibility every 1s.
        self._beat_on = True
        self._beat = QTimer(self)
        self._beat.timeout.connect(self._toggle_beat)
        self._beat.start(1000)

    def _toggle_beat(self) -> None:
        self._beat_on = not self._beat_on
        self._beat_dot.setVisible(self._beat_on)

    def _refresh_clock(self) -> None:
        self._clock.setText(time.strftime("%H:%M:%S UTC", time.gmtime()))

    # ------------------------------------------------------------------
    # Public setters used by the brain / window
    # ------------------------------------------------------------------

    def set_mode(self, label: str, color=None) -> None:
        self._mode.setText(label.upper())
        if color is not None:
            self._mode.setStyleSheet(
                f"color: {color.name()}; font-family: {theme.FONT_HUD}; "
                f"font-size: 10px; font-weight: 600; letter-spacing: 3px; background: transparent;"
            )

    def set_tool_count(self, n: int) -> None:
        self._tools.setText(f"{n} TOOLS")
