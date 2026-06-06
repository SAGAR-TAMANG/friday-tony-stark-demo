"""Left system rail — host telemetry.

Polled at 1Hz with psutil. Renders as a stack of HUD blocks:

    SYS · LIVE
    ─────────
    CPU   ▓▓▓▓▓░░░░░  47%
    MEM   ▓▓▓▓▓▓▓░░░  68%
    NET   ↑  142 kB/s
          ↓   18 kB/s

    MCP   ● online · 14 tools
    SES   00:14:23
    HOST  dhruv-mbp · 192.168.1.42

Pure read-only telemetry — no controls live here. Click-through is
blocked so drags on this column don't move the window.
"""

from __future__ import annotations

import socket
import time

import psutil
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QHBoxLayout

from . import theme


def _hud(text: str, color, size: float = 10.0, spacing: float = 1.5, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    weight = "600" if bold else "500"
    lbl.setStyleSheet(
        f"color: {color.name()}; font-family: {theme.FONT_HUD}; "
        f"font-size: {size}px; font-weight: {weight}; "
        f"letter-spacing: {spacing}px; background: transparent;"
    )
    return lbl


class _Bar(QWidget):
    """Tiny 10-segment HUD meter."""

    SEGMENTS = 14

    def __init__(self, label: str, accent: QColor, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._value = 0.0
        self._accent = accent
        self._label = label

    def set_value(self, v: float) -> None:
        v = max(0.0, min(1.0, v))
        if abs(v - self._value) > 0.001:
            self._value = v
            self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()

        # Label.
        p.setPen(QPen(theme.TEXT_DIM))
        p.setFont(self.font())
        p.drawText(0, 0, 40, h, Qt.AlignVCenter | Qt.AlignLeft, self._label)

        # Bar grid.
        bar_x = 44
        bar_w = w - 88
        bar_h = 8
        bar_y = (h - bar_h) // 2

        seg_gap = 2
        seg_w = (bar_w - seg_gap * (self.SEGMENTS - 1)) / self.SEGMENTS
        filled = int(round(self._value * self.SEGMENTS))

        # Color shifts to red when bar gets hot.
        if self._value > 0.85:
            accent = theme.HUD_RED
        elif self._value > 0.65:
            accent = theme.HUD_AMBER
        else:
            accent = self._accent

        for i in range(self.SEGMENTS):
            x = bar_x + i * (seg_w + seg_gap)
            on = i < filled
            color = accent if on else QColor(accent.red(), accent.green(), accent.blue(), 35)
            p.fillRect(int(x), bar_y, int(seg_w), bar_h, color)

        # Percent readout.
        pct = f"{int(self._value * 100):3d}%"
        p.setPen(QPen(theme.TEXT_BRIGHT))
        p.drawText(w - 40, 0, 40, h, Qt.AlignVCenter | Qt.AlignRight, pct)


class _Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(
            f"background: rgba(0,180,210,55);"
        )


class _Section(QWidget):
    """Header + body block."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        header = _hud(title, theme.TEXT_FAINT, size=9, spacing=3, bold=True)
        lay.addWidget(header)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(4)
        lay.addLayout(self._body)

    def add(self, widget: QWidget) -> None:
        self._body.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._body.addLayout(layout)


class SystemRail(QWidget):
    """Left-side telemetry column. Width fixed to theme.RAIL_WIDTH."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(theme.RAIL_WIDTH)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("SysRail")
        self.setStyleSheet(
            f"#SysRail {{ background: rgba(6,9,13,210); "
            f"border-right: 1px solid rgba(0,180,210,70); }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        # ── SYS section ─────────────────────────────────────────
        sys_sec = _Section("SYS · LIVE")
        self._cpu = _Bar("CPU", theme.HUD_CYAN)
        self._mem = _Bar("MEM", theme.HUD_CYAN)
        self._disk = _Bar("DSK", theme.HUD_CYAN)
        self._bat = _Bar("BAT", theme.HUD_CYAN)
        sys_sec.add(self._cpu)
        sys_sec.add(self._mem)
        sys_sec.add(self._disk)
        # Battery row stays hidden on desktops with no battery.
        battery = getattr(psutil, "sensors_battery", lambda: None)()
        self._has_battery = battery is not None
        if self._has_battery:
            sys_sec.add(self._bat)

        net_row = QVBoxLayout()
        net_row.setSpacing(2)
        self._net_up = _hud("↑     0 B/s", theme.TEXT_DIM, size=10, spacing=1)
        self._net_dn = _hud("↓     0 B/s", theme.TEXT_DIM, size=10, spacing=1)
        net_row.addWidget(self._net_up)
        net_row.addWidget(self._net_dn)
        sys_sec.add_layout(net_row)
        outer.addWidget(sys_sec)

        outer.addWidget(_Divider())

        # ── LINK section ────────────────────────────────────────
        link_sec = _Section("LINK")
        link_row = QHBoxLayout()
        link_row.setSpacing(6)
        self._mcp_dot = _hud("●", theme.HUD_GREEN, size=11, spacing=0, bold=True)
        self._mcp_lbl = _hud("MCP  ONLINE", theme.TEXT_BRIGHT, size=10, spacing=1.5)
        link_row.addWidget(self._mcp_dot)
        link_row.addWidget(self._mcp_lbl)
        link_row.addStretch(1)
        link_sec.add_layout(link_row)

        self._tools_lbl = _hud("TOOLS 0", theme.TEXT_DIM, size=10, spacing=1.5)
        link_sec.add(self._tools_lbl)

        # Mic indicator — dot + label flips when voice capture is live.
        mic_row = QHBoxLayout()
        mic_row.setSpacing(6)
        self._mic_dot = _hud("●", theme.TEXT_FAINT, size=11, spacing=0, bold=True)
        self._mic_lbl = _hud("MIC  IDLE", theme.TEXT_DIM, size=10, spacing=1.5)
        mic_row.addWidget(self._mic_dot)
        mic_row.addWidget(self._mic_lbl)
        mic_row.addStretch(1)
        link_sec.add_layout(mic_row)
        outer.addWidget(link_sec)

        outer.addWidget(_Divider())

        # ── SESSION section ────────────────────────────────────
        ses_sec = _Section("SESSION")
        self._uptime_lbl = _hud("UPTIME  00:00:00", theme.TEXT_BRIGHT, size=10, spacing=1.5)
        self._host_lbl = _hud("HOST   …", theme.TEXT_DIM, size=10, spacing=1.5)
        self._ip_lbl = _hud("ADDR   …", theme.TEXT_DIM, size=10, spacing=1.5)
        ses_sec.add(self._uptime_lbl)
        ses_sec.add(self._host_lbl)
        ses_sec.add(self._ip_lbl)
        outer.addWidget(ses_sec)

        outer.addStretch(1)

        # Footer signature.
        sig = _hud("STARK INDUSTRIES // INTERNAL", theme.TEXT_FAINT, size=8.5, spacing=2)
        sig.setAlignment(Qt.AlignCenter)
        outer.addWidget(sig)

        # Initial host info (one-shot).
        self._fill_host_info()

        # Poll timer (1 Hz).
        self._start_ts = time.time()
        self._last_net = psutil.net_io_counters()
        self._last_ts = time.time()
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._poll)
        self._tick.start(1000)
        self._poll()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_mcp(self, online: bool, tool_count: int = 0) -> None:
        if online:
            self._mcp_dot.setStyleSheet(
                f"color: {theme.HUD_GREEN.name()}; font-family: {theme.FONT_HUD}; "
                f"font-size: 11px; font-weight: 600; background: transparent;"
            )
            self._mcp_lbl.setText("MCP  ONLINE")
        else:
            self._mcp_dot.setStyleSheet(
                f"color: {theme.HUD_RED.name()}; font-family: {theme.FONT_HUD}; "
                f"font-size: 11px; font-weight: 600; background: transparent;"
            )
            self._mcp_lbl.setText("MCP  OFFLINE")
        self._tools_lbl.setText(f"TOOLS {tool_count:>3d}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fill_host_info(self) -> None:
        try:
            host = socket.gethostname()
        except Exception:
            host = "?"
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "0.0.0.0"
        self._host_lbl.setText(f"HOST   {host[:18]}")
        self._ip_lbl.setText(f"ADDR   {ip}")

    def set_mic(self, state: str, level_db: float | None = None) -> None:
        """state: idle | recording | transcribing"""
        if state == "recording":
            color = theme.HUD_RED
            label = f"MIC  LIVE  {level_db:+.0f}dB" if level_db is not None else "MIC  LIVE"
        elif state == "transcribing":
            color = theme.HUD_AMBER
            label = "MIC  ··· "
        else:
            color = theme.TEXT_FAINT
            label = "MIC  IDLE"
        self._mic_dot.setStyleSheet(
            f"color: {color.name()}; font-family: {theme.FONT_HUD}; "
            f"font-size: 11px; font-weight: 600; background: transparent;"
        )
        self._mic_lbl.setText(label)

    def _poll(self) -> None:
        # CPU/MEM/DISK/BAT.
        cpu = psutil.cpu_percent(interval=None) / 100.0
        mem = psutil.virtual_memory().percent / 100.0
        self._cpu.set_value(cpu)
        self._mem.set_value(mem)
        try:
            disk = psutil.disk_usage("/").percent / 100.0
            self._disk.set_value(disk)
        except OSError:
            pass
        if self._has_battery:
            battery = psutil.sensors_battery()
            if battery is not None:
                self._bat.set_value(battery.percent / 100.0)

        # NET — bytes/sec since last tick.
        now = time.time()
        cur = psutil.net_io_counters()
        dt = max(0.001, now - self._last_ts)
        up_bps = (cur.bytes_sent - self._last_net.bytes_sent) / dt
        dn_bps = (cur.bytes_recv - self._last_net.bytes_recv) / dt
        self._last_net = cur
        self._last_ts = now
        self._net_up.setText(f"↑  {_fmt_rate(up_bps):>10s}")
        self._net_dn.setText(f"↓  {_fmt_rate(dn_bps):>10s}")

        # Uptime.
        up = int(now - self._start_ts)
        self._uptime_lbl.setText(
            f"UPTIME  {up // 3600:02d}:{(up % 3600) // 60:02d}:{up % 60:02d}"
        )


def _fmt_rate(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 * 1024:
        return f"{bps / 1024:.1f} kB/s"
    return f"{bps / (1024 * 1024):.2f} MB/s"
