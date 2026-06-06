"""FRIDAY desktop — entry point.

Run via:
    uv run friday_desktop
or:
    python -m friday.desktop
"""

from __future__ import annotations

import sys

import atexit
import os

from dotenv import load_dotenv
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from . import launcher
from .window import MainWindow


PID_LOCK = launcher.PID_DESKTOP


def _resolve_mono_family() -> str:
    """Return the first installed monospace family, or fall back to a hint."""
    families = QFontDatabase.families()
    for candidate in ("Menlo", "SF Mono", "Monaco", "JetBrains Mono",
                      "Consolas", "Courier New"):
        if candidate in families:
            return candidate
    return "Monaco"


def _write_pid_lock() -> None:
    try:
        PID_LOCK.write_text(str(os.getpid()))
    except OSError:
        pass


def _clear_pid_lock() -> None:
    try:
        if PID_LOCK.exists() and PID_LOCK.read_text().strip() == str(os.getpid()):
            PID_LOCK.unlink()
    except OSError:
        pass


def _autostart_siblings() -> dict:
    """Start Odysseus + the MCP server + voice agent if they aren't already up.

    Disable with ``FRIDAY_AUTOSTART=0``. If ``FRIDAY_AUTOSTART_VOICE=0``
    only the MCP server is auto-started (useful if the boss wants to
    run the voice agent from a terminal so he can watch its logs).
    """
    if os.getenv("FRIDAY_AUTOSTART", "1").lower() in {"0", "false", "no"}:
        return {"status": "skipped"}

    result = {"odysseus": launcher.ensure_odysseus_running(), "mcp": launcher.ensure_mcp_running()}
    if os.getenv("FRIDAY_AUTOSTART_VOICE", "1").lower() not in {"0", "false", "no"}:
        result["voice"] = launcher.ensure_voice_running()
    return result


def _stop_siblings_if_we_own() -> None:
    """If we autostarted them, take them down on exit."""
    if os.getenv("FRIDAY_AUTOSTART_STOP_ON_EXIT", "1").lower() in {"0", "false", "no"}:
        return
    launcher.terminate_if_owned(launcher.PID_VOICE)
    launcher.terminate_if_owned(launcher.PID_MCP)
    launcher.terminate_if_owned(launcher.PID_ODYSSEUS)


def main() -> int:
    load_dotenv()  # pick up OPENAI_API_KEY, OBSIDIAN_VAULT_PATH, etc.

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("FRIDAY")
    app.setApplicationDisplayName("FRIDAY")

    mono = _resolve_mono_family()
    # Qt sometimes asks for the generic "Sans Serif" alias which doesn't
    # exist as an installed family on macOS, prompting a slow fontconfig
    # alias scan. Pre-register a substitution so the lookup is instant.
    QFont.insertSubstitution("Sans Serif", "Helvetica")
    QFont.insertSubstitution("sans-serif", "Helvetica")
    app.setFont(QFont(mono, 10))

    _write_pid_lock()
    atexit.register(_clear_pid_lock)

    # Spawn MCP + voice before the window mounts so the boss never has
    # to remember three terminals. They run in their own session and we
    # tear them down on exit (unless overridden by env).
    auto = _autostart_siblings()
    atexit.register(_stop_siblings_if_we_own)

    window = MainWindow()
    # Surface the autostart result on the activity feed so the boss
    # can see what was launched.
    if auto.get("status") != "skipped":
        for name, payload in (("odysseus", auto.get("odysseus")), ("mcp", auto.get("mcp")), ("voice", auto.get("voice"))):
            if not payload:
                continue
            status = payload.get("status", "?")
            pid = payload.get("pid", "—")
            kind = "ok" if status in {"launched", "already_running"} else "err"
            window.activity.log("autostart", f"{name}: {status} pid={pid}", kind)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
