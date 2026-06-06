"""Transcript stream — terminal-style chat log.

No bubbles, no avatars. Each turn renders as a line with a HUD prefix:

    [18:42:07]  boss ❯  open the world monitor
    [18:42:08]  fri  ◂  Let me open up the world monitor for you.
    [18:42:08]  tool ·  open_world_monitor

Width-spans the center column. Mono font, color-coded by role. Keeps
the original ChatPanel API surface (``add_message``, ``replace_last``,
``set_enabled_input``, ``submitted`` signal) so the brain wiring in
window.py doesn't need to change.

The Enter-key input has moved to ``commandbar.CommandBar`` — this panel
no longer renders a QLineEdit. ``set_enabled_input`` is kept as a no-op
shim because the brain still calls it on state changes.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from . import theme


_ROLE = {
    "user":      ("boss", "❯", theme.TEXT_USER),
    "assistant": ("fri ", "◂", theme.TEXT_BRIGHT),
    "tool":      ("tool", "·", theme.HUD_CYAN_DIM),
    "system":    ("sys ", "*", theme.TEXT_FAINT),
}


class _Line(QFrame):
    """One transcript line. Prefix + body, both mono."""

    def __init__(self, text: str, role: str):
        super().__init__()
        self.role = role
        prefix_name, arrow, body_color = _ROLE.get(role, _ROLE["assistant"])

        ts = time.strftime("%H:%M:%S")

        stamp = QLabel(f"[{ts}]")
        stamp.setStyleSheet(
            f"color: {theme.TEXT_FAINT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 10.5px; "
            f"background: transparent;"
        )

        prefix = QLabel(f"{prefix_name} {arrow}")
        prefix.setStyleSheet(
            f"color: {theme.HUD_CYAN.name() if role == 'user' else theme.HUD_ICE.name() if role == 'assistant' else theme.HUD_CYAN_DIM.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 11px; "
            f"font-weight: 600; letter-spacing: 1px; "
            f"background: transparent;"
        )

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(
            f"color: {body_color.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 12px; "
            f"line-height: 1.55; background: transparent;"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(stamp, 0, Qt.AlignTop)
        row.addWidget(prefix, 0, Qt.AlignTop)
        row.addWidget(body, 1)
        self._body = body

    def set_text(self, text: str) -> None:
        self._body.setText(text)


class ChatPanel(QWidget):
    """Center-column transcript stream. ``submitted`` kept for API parity."""

    submitted = Signal(str)  # no longer used by this widget; kept for shape

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("Transcript")
        self.setStyleSheet(
            f"#Transcript {{ background: rgba(6,9,13,180); "
            f"border-left: 1px solid rgba(0,180,210,55); "
            f"border-right: 1px solid rgba(0,180,210,55); }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 14)
        outer.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header = QLabel("TRANSCRIPT · /var/log/friday.log")
        header.setStyleSheet(
            f"color: {theme.TEXT_FAINT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 9.5px; "
            f"letter-spacing: 3px; background: transparent;"
        )
        header_row.addWidget(header)
        header_row.addStretch(1)
        self._cursor = QLabel("●")
        self._cursor.setStyleSheet(
            f"color: {theme.HUD_GREEN.name()}; font-family: {theme.FONT_HUD}; "
            f"font-size: 10px; background: transparent;"
        )
        header_row.addWidget(self._cursor)
        outer.addLayout(header_row)

        # Scrollable log area.
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
        self._log = QVBoxLayout(self._inner)
        self._log.setContentsMargins(0, 0, 6, 0)
        self._log.setSpacing(6)
        self._log.addStretch(1)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, 1)

        # Blink the cursor dot.
        self._blink_on = True
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._tick_cursor)
        self._blink.start(700)

    # ------------------------------------------------------------------
    # API parity with the old ChatPanel
    # ------------------------------------------------------------------

    def add_message(self, text: str, role: str = "assistant") -> _Line:
        line = _Line(text, role)
        self._log.insertWidget(self._log.count() - 1, line)
        QTimer.singleShot(20, self._scroll_to_bottom)
        return line

    def replace_last(self, text: str) -> None:
        for i in range(self._log.count() - 1, -1, -1):
            w = self._log.itemAt(i).widget()
            if isinstance(w, _Line) and w.role == "assistant":
                w.set_text(text)
                return
        self.add_message(text, "assistant")

    def set_enabled_input(self, enabled: bool) -> None:
        # Input lives in CommandBar now. This is a shim — flip the
        # status dot to communicate working/idle to the eye.
        color = theme.HUD_GREEN if enabled else theme.HUD_AMBER
        self._cursor.setStyleSheet(
            f"color: {color.name()}; font-family: {theme.FONT_HUD}; "
            f"font-size: 10px; background: transparent;"
        )

    def clear_log(self) -> None:
        while self._log.count() > 1:  # leave the trailing stretch
            item = self._log.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _tick_cursor(self) -> None:
        self._blink_on = not self._blink_on
        self._cursor.setVisible(self._blink_on)
