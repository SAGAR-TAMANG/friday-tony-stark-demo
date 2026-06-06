"""Activity log — right rail, ``tail -f``-style stream.

  EVENTS · LIVE
  ─────────────
  18:42:07  ●  OPEN_WORLD_MONITOR    —
  18:42:07  ●  GET_WORLD_NEWS        feeds=12
  18:42:08  ●  SEARCH_WEB            query=…       2.1k chars
  18:42:09  ●  USER                  hello fri

Color coded by severity. Auto-scrolls. Capped buffer.
"""

from __future__ import annotations

import time

from PySide6.QtCore import (
    QPropertyAnimation, Qt, QEasingCurve,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)

from . import theme


_MAX_ROWS = 80


class _Row(QWidget):
    def __init__(self, tool: str, detail: str, kind: str = "info"):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        dot_color = {
            "info":   theme.HUD_CYAN,
            "ok":     theme.HUD_GREEN,
            "err":    theme.HUD_RED,
            "warn":   theme.HUD_AMBER,
            "user":   theme.TEXT_USER,
        }.get(kind, theme.HUD_CYAN)

        ts = QLabel(time.strftime("%H:%M:%S"))
        ts.setStyleSheet(
            f"color: {theme.TEXT_FAINT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 9.5px; background: transparent;"
        )
        ts.setFixedWidth(58)

        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {dot_color.name()}; font-family: {theme.FONT_HUD}; "
            f"font-size: 9px; background: transparent;"
        )
        dot.setFixedWidth(12)

        name = QLabel(tool.upper()[:22])
        name.setStyleSheet(
            f"color: {theme.TEXT_BRIGHT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 9.5px; "
            f"font-weight: 600; letter-spacing: 1px; background: transparent;"
        )
        name.setFixedWidth(150)

        detail_lbl = QLabel(detail)
        detail_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 9.5px; background: transparent;"
        )
        detail_lbl.setWordWrap(False)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(6)
        row.addWidget(ts)
        row.addWidget(dot)
        row.addWidget(name)
        row.addWidget(detail_lbl, 1)

        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._anim = anim


class ActivityFeed(QWidget):
    """Right-rail scrolling log. ``log(tool, detail, kind)``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("ActivityFeed")
        self.setStyleSheet(
            f"#ActivityFeed {{ background: rgba(6,9,13,210); "
            f"border-left: 1px solid rgba(0,180,210,70); }}"
        )
        self.setFixedWidth(theme.PANEL_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 12, 14)
        outer.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header = QLabel("EVENTS · LIVE")
        header.setStyleSheet(
            f"color: {theme.TEXT_FAINT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 9.5px; "
            f"letter-spacing: 3px; background: transparent;"
        )
        header_row.addWidget(header)
        header_row.addStretch(1)
        self._count_lbl = QLabel("0")
        self._count_lbl.setStyleSheet(
            f"color: {theme.HUD_CYAN_DIM.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 9.5px; "
            f"letter-spacing: 1.5px; background: transparent;"
        )
        header_row.addWidget(self._count_lbl)
        outer.addLayout(header_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { background: transparent; width: 6px; }"
            "QScrollBar::handle:vertical { background: rgba(0,229,255,90); border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._rows_box = QVBoxLayout(self._inner)
        self._rows_box.setContentsMargins(0, 0, 4, 0)
        self._rows_box.setSpacing(1)
        self._rows_box.addStretch(1)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, 1)

        self._count = 0

    def log(self, tool: str, detail: str, kind: str = "info") -> None:
        if len(detail) > 90:
            detail = detail[:87] + "…"
        row = _Row(tool, detail, kind)
        self._rows_box.insertWidget(self._rows_box.count() - 1, row)

        # Cap.
        while self._rows_box.count() - 1 > _MAX_ROWS:
            old = self._rows_box.takeAt(0)
            if old and old.widget():
                old.widget().deleteLater()

        self._count += 1
        self._count_lbl.setText(f"{self._count:04d}")
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear(self) -> None:
        while self._rows_box.count() > 1:
            item = self._rows_box.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._count = 0
        self._count_lbl.setText("0000")
