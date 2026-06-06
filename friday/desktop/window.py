"""FRIDAY desktop HUD — main window.

Layout:

  ┌──────────────────────────────────────────────────────────────────┐
  │ F.R.I.D.A.Y. ▸ ONLINE ▸ GPT-4O ▸ 14 TOOLS ▸ HH:MM:SS UTC  ─  ✕   │  ← StatusBar
  ├────────┬───────────────────────────────────┬─────────────────────┤
  │        │                                   │                     │
  │  SYS   │              ORB                  │   EVENTS · LIVE     │
  │  rail  │      (warm arc reactor)           │  (log-tail feed)    │
  │ (psu)  │                                   │                     │
  │        │  ─── transcript stream ───        │                     │
  │        │                                   │                     │
  ├────────┴───────────────────────────────────┴─────────────────────┤
  │ friday@stark://~ ❯  command…                              █      │  ← CommandBar
  └──────────────────────────────────────────────────────────────────┘

Behind everything: a faint cyan grid. On top of everything: subtle CRT
scanlines + vignette. Drag the status bar to move the frameless window.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from . import theme
from .activity import ActivityFeed
from .audio_bus import AudioBus
from .brain import Brain
from .chat import ChatPanel
from .commandbar import CommandBar
from .events import read_events_since
from .orb import Orb
from .odysseus_panel import OdysseusPanel
from .scanlines import GridBackground, ScanlineOverlay
from .statusbar import StatusBar
from .sysrail import SystemRail


ODYSSEUS_COMMANDS = {
    "/odysseus": "home",
    "/ody": "home",
    "/ody home": "home",
    "/ody chat": "chat",
    "/ody notes": "notes",
    "/ody tasks": "tasks",
    "/ody memory": "memory",
    "/ody settings": "settings",
    "/ody research": "research",
    "/ody calendar": "calendar",
    "/ody compare": "compare",
    "/ody gallery": "gallery",
    "/ody cookbook": "cookbook",
    "/core": "__core__",
}


def parse_odysseus_command(text: str) -> str | None:
    command = " ".join((text or "").strip().lower().split())
    if command in ODYSSEUS_COMMANDS:
        return ODYSSEUS_COMMANDS[command]
    return None


class _RoundedShell(QWidget):
    """Rounded translucent base. Sits behind the grid."""

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), theme.CORNER_RADIUS, theme.CORNER_RADIUS)
        p.fillPath(path, theme.BG_BASE)
        # Outer cyan hairline.
        pen = QPen(theme.BORDER_DIM)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(QSize(theme.WINDOW_W, theme.WINDOW_H))
        self.setWindowTitle("F.R.I.D.A.Y.")

        # ── outer rounded shell ───────────────────────────────────────
        self._shell = _RoundedShell(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._shell)

        # The shell stacks: grid (back) → content → scanlines (front).
        # Content lives in a child widget we lay out manually.
        self._grid = GridBackground(self._shell)
        self._content = QWidget(self._shell)
        self._content.setAttribute(Qt.WA_TranslucentBackground, True)
        self._scanlines = ScanlineOverlay(self._shell)

        # Build the content tree.
        shell_layout = QVBoxLayout(self._content)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # ── top status bar ────────────────────────────────────────────
        # Brain needs to exist first so we know the model + tool count.
        self.brain = Brain(parent=self)
        tool_count = len(self.brain._tools_schema) if hasattr(self.brain, "_tools_schema") else 0
        self.statusbar = StatusBar(
            model_label=self.brain.model, tool_count=tool_count,
        )
        self.statusbar.minimize_requested.connect(self.showMinimized)
        self.statusbar.close_requested.connect(self.close)
        self.statusbar.zoom_requested.connect(self._toggle_maximize)
        shell_layout.addWidget(self.statusbar)

        # ── middle row: rail | orb+transcript | activity ──────────────
        middle = QWidget()
        middle.setAttribute(Qt.WA_TranslucentBackground, True)
        mid_l = QHBoxLayout(middle)
        mid_l.setContentsMargins(0, 0, 0, 0)
        mid_l.setSpacing(0)

        # Left rail.
        self.sysrail = SystemRail()
        mcp_online = self.brain._client is not None
        self.sysrail.set_mcp(online=mcp_online, tool_count=tool_count)
        mid_l.addWidget(self.sysrail, 0)

        # Center stack — core FRIDAY view or embedded Odysseus.
        self.center_stack = QStackedWidget()
        self.center_stack.setAttribute(Qt.WA_TranslucentBackground, True)

        self.core_view = QWidget()
        self.core_view.setAttribute(Qt.WA_TranslucentBackground, True)
        center_l = QVBoxLayout(self.core_view)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(0)

        self.orb = Orb()
        self.orb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.orb.setMinimumHeight(340)
        center_l.addWidget(self.orb, 3)

        self.chat = ChatPanel()
        center_l.addWidget(self.chat, 4)

        self.odysseus_panel = OdysseusPanel()
        self.center_stack.addWidget(self.core_view)
        self.center_stack.addWidget(self.odysseus_panel)
        self.center_stack.setCurrentWidget(self.core_view)

        mid_l.addWidget(self.center_stack, 1)

        # Right rail — activity log.
        self.activity = ActivityFeed()
        mid_l.addWidget(self.activity, 0)

        shell_layout.addWidget(middle, 1)

        # ── bottom command bar ────────────────────────────────────────
        self.cmdbar = CommandBar()
        shell_layout.addWidget(self.cmdbar)

        # ── brain wiring ──────────────────────────────────────────────
        self.brain.state_changed.connect(self._on_state)
        self.brain.activity.connect(self.activity.log)
        self.brain.assistant_text.connect(self._on_assistant)
        self.brain.error.connect(lambda e: self.activity.log("error", e[:120], "err"))
        self.cmdbar.submitted.connect(self._on_user_submit)
        self.cmdbar.cleared.connect(self._on_cleared)
        self.cmdbar.voice_state.connect(self._on_voice_state)
        self.cmdbar.voice_error.connect(
            lambda e: self.activity.log("mic", e[:120], "err")
        )

        # External event polling (from the voice agent process).
        self._event_offset = 0
        self._event_timer = QTimer(self)
        self._event_timer.timeout.connect(self._poll_external_events)
        self._event_timer.start(300)

        # ── intro line ───────────────────────────────────────────────
        self.activity.log("boot", f"hud online · {tool_count} tools", "ok")
        QTimer.singleShot(
            350,
            lambda: self.chat.add_message(
                "Online and listening, boss. What are we working on?",
                "assistant",
            ),
        )
        QTimer.singleShot(400, self.cmdbar.focus_input)

        # Frameless drag — only when grabbing the status bar.
        self._drag_pos: QPoint | None = None

    # ------------------------------------------------------------------
    # Layout — keep grid/content/scanlines stacked on resize
    # ------------------------------------------------------------------

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        r = self._shell.rect()
        self._grid.setGeometry(r)
        self._content.setGeometry(r)
        self._scanlines.setGeometry(r)
        self._scanlines.raise_()

    # ------------------------------------------------------------------
    # Frameless drag (status bar only)
    # ------------------------------------------------------------------

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            sb_geo = self.statusbar.geometry()
            sb_geo.translate(self._content.pos())
            if sb_geo.contains(ev.position().toPoint()):
                self._drag_pos = (
                    ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ------------------------------------------------------------------
    # State / events
    # ------------------------------------------------------------------

    def _on_state(self, state: str) -> None:
        self.orb.set_state(state)
        label = {
            "idle":      "ONLINE",
            "listening": "LISTENING",
            "thinking":  "PROCESSING",
            "speaking":  "RESPONDING",
        }.get(state, "ONLINE")
        color = {
            "idle":      theme.HUD_GREEN,
            "listening": theme.HUD_CYAN,
            "thinking":  theme.HUD_VIOLET,
            "speaking":  theme.HUD_AMBER,
        }.get(state, theme.HUD_GREEN)
        self.statusbar.set_mode(label, color)
        if state in ("speaking", "idle"):
            self.cmdbar.set_enabled_input(True)
            self.chat.set_enabled_input(True)
        else:
            self.cmdbar.set_enabled_input(False)
            self.chat.set_enabled_input(False)

    def _on_user_submit(self, text: str) -> None:
        panel = parse_odysseus_command(text)
        if panel == "__core__":
            self.show_core()
            return
        if panel:
            self.show_odysseus_panel(panel)
            return
        self.chat.add_message(text, "user")
        self.activity.log("user", text[:60], "user")
        self.brain.send(text)

    def _on_assistant(self, text: str) -> None:
        self.chat.add_message(text, "assistant")
        self.orb.pulse(0.6)

    def _on_cleared(self) -> None:
        self.chat.clear_log()
        self.activity.clear()
        self.activity.log("clear", "transcript wiped", "warn")

    def _on_voice_state(self, state: str) -> None:
        self.sysrail.set_mic(state)
        if state == "recording":
            self.activity.log("mic", "capturing voice", "info")
            self._on_state("listening")
        elif state == "transcribing":
            self.activity.log("mic", "whisper transcribing", "info")
        elif state == "idle":
            self._on_state("idle")

    def show_core(self) -> None:
        self.center_stack.setCurrentWidget(self.core_view)
        self.activity.log("hud", "core view", "info")
        self.statusbar.set_mode("ONLINE", theme.HUD_GREEN)
        self.cmdbar.focus_input()

    def show_odysseus_panel(self, panel: str = "home") -> None:
        try:
            url = self.odysseus_panel.open_panel(panel)
        except Exception as exc:
            self.activity.log("odysseus", str(exc)[:120], "err")
            return
        self.center_stack.setCurrentWidget(self.odysseus_panel)
        self.activity.log("odysseus", f"panel={panel} · {url}", "ok")
        self.statusbar.set_mode("ODYSSEUS", theme.HUD_ICE)
        self.cmdbar.focus_input()

    def _poll_external_events(self) -> None:
        batch = read_events_since(self._event_offset)
        self._event_offset = batch.offset
        for event in batch.events:
            apply_external_event(self, event)


def apply_external_event(window: MainWindow, event: dict) -> None:
    """Apply a voice-agent event to the visible desktop UI."""
    event_type = event.get("type")
    if event_type == "chat":
        role = event.get("role", "assistant")
        text = str(event.get("text", "")).strip()
        if not text:
            return
        if role == "assistant":
            window._on_assistant(text)
        elif role == "user":
            window.chat.add_message(text, "user")
        else:
            window.chat.add_message(text, "tool")
    elif event_type == "state":
        state = str(event.get("state", "idle"))
        window._on_state(state)
    elif event_type == "activity":
        tool = str(event.get("tool", "event"))
        detail = str(event.get("detail", ""))
        kind = str(event.get("kind", "info"))
        window.activity.log(tool, detail, kind)
    elif event_type == "audio":
        # Real-time amplitude pushed from the voice agent process. This
        # is what makes the orb feel like it's *actually* producing
        # FRIDAY's voice — start, body, and end of each utterance line
        # up with the LiveKit TTS playback window.
        try:
            rms = float(event.get("rms", 0.0))
        except (TypeError, ValueError):
            rms = 0.0
        AudioBus.instance().push_rms(rms)
    elif event_type == "odysseus_panel":
        window.show_odysseus_panel(str(event.get("panel", "home")))
    elif event_type == "error":
        window.activity.log("error", str(event.get("detail", ""))[:120], "err")
