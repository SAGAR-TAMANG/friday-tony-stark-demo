"""Bottom command bar — terminal-style prompt.

  friday@stark://~ ❯ open finance world monitor▏

Slash commands (typed) get autocompleted from a fixed registry. Emits
``submitted(str)`` like the old ChatPanel input did, so wiring stays
identical from the brain's perspective.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCompleter, QHBoxLayout, QLabel, QLineEdit, QWidget,
)

from . import theme
from .voicein import MicButton, VoiceCapture


SLASH_COMMANDS = [
    "/news",
    "/finance",
    "/world",
    "/screen",
    "/memory",
    "/recall",
    "/save",
    "/diag",
    "/odysseus",
    "/ody notes",
    "/ody tasks",
    "/ody memory",
    "/ody settings",
    "/ody research",
    "/core",
    "/help",
    "/clear",
]


class CommandBar(QWidget):
    """Bottom-of-window prompt. Emits ``submitted(str)`` on Enter."""

    submitted = Signal(str)
    cleared = Signal()
    voice_state = Signal(str)   # "idle" | "recording" | "transcribing"
    voice_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(theme.CMDBAR_H)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("CmdBar")
        self.setStyleSheet(
            f"#CmdBar {{ background: rgba(2,4,8,225); "
            f"border-top: 1px solid rgba(0,180,210,80); }}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(10)

        self._prompt = QLabel("friday@stark://~ ❯")
        self._prompt.setStyleSheet(
            f"color: {theme.TEXT_PROMPT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 11px; "
            f"font-weight: 600; letter-spacing: 1px; background: transparent;"
        )
        row.addWidget(self._prompt)

        # Mic — click to start, click to stop + transcribe.
        self.capture = VoiceCapture(self)
        self.capture.transcribed.connect(self._on_voice_text)
        self.capture.state_changed.connect(self.voice_state.emit)
        self.capture.error.connect(self.voice_error.emit)
        self.mic = MicButton(self.capture)
        row.addWidget(self.mic)

        self._input = QLineEdit()
        self._input.setPlaceholderText("speak, ask, command…")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; "
            f"color: {theme.TEXT_BRIGHT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 12px; "
            f"selection-background-color: rgba(0,229,255,90); }} "
            f"QLineEdit::placeholder {{ color: {theme.TEXT_FAINT.name()}; }}"
        )
        self._input.returnPressed.connect(self._on_submit)
        row.addWidget(self._input, 1)

        # Slash autocomplete.
        self._completer = QCompleter(SLASH_COMMANDS, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        popup = self._completer.popup()
        popup.setStyleSheet(
            f"QListView {{ background: rgba(8,11,16,245); "
            f"color: {theme.TEXT_BRIGHT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 11px; "
            f"border: 1px solid rgba(0,180,210,140); "
            f"selection-background-color: rgba(0,229,255,60); "
            f"selection-color: {theme.HUD_CYAN.name()}; "
            f"padding: 4px; }}"
        )
        self._input.setCompleter(self._completer)

        # Cursor blink / focus indicator on the right (faux caret tail).
        self._caret_dot = QLabel("█")
        self._caret_dot.setStyleSheet(
            f"color: {theme.TEXT_PROMPT.name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 11px; background: transparent;"
        )
        row.addWidget(self._caret_dot)

        # Esc clears.
        QShortcut(QKeySequence(Qt.Key_Escape), self._input, activated=self._handle_escape)
        # Ctrl+L clears transcript (signal).
        QShortcut(QKeySequence("Ctrl+L"), self._input, activated=self.cleared.emit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled_input(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)
        self._input.setPlaceholderText(
            "speak, ask, command…" if enabled else "[ working ]"
        )
        self._prompt.setStyleSheet(
            f"color: {(theme.TEXT_PROMPT if enabled else theme.TEXT_FAINT).name()}; "
            f"font-family: {theme.FONT_HUD}; font-size: 11px; "
            f"font-weight: 600; letter-spacing: 1px; background: transparent;"
        )

    def focus_input(self) -> None:
        self._input.setFocus()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        if text == "/clear":
            self.cleared.emit()
            return
        self.submitted.emit(text)

    def _handle_escape(self) -> None:
        if self._input.text():
            self._input.clear()
        else:
            self._input.clearFocus()

    def _on_voice_text(self, text: str) -> None:
        """Whisper returned a transcript — treat it like the user typed it."""
        text = text.strip()
        if not text:
            return
        self.submitted.emit(text)
