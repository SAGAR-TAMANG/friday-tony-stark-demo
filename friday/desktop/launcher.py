"""Cross-process launcher for the FRIDAY process trio.

Three sibling processes — MCP server, voice agent, desktop HUD — each
with its own PID lock under ``/tmp/`` so any process can check whether
its peers are alive without racing.

Used by:

* the voice agent on the wake phrase, to spawn the desktop;
* the desktop on startup, to autostart the MCP server + voice agent so
  the boss never has to remember three terminals.

Each ``ensure_*_running`` function is idempotent: returns
``{"status":"already_running"}`` if the lock is live, or spawns and
returns the new PID. Spawned children:

* run in their own session (``start_new_session=True``), so a SIGINT
  on the parent doesn't take them down — the parent terminates them
  explicitly on shutdown if it owns them;
* redirect stdout/stderr to log files under ``/tmp/`` so failures are
  diagnosable;
* are launched via the Python interpreter that's running us, so we
  inherit the active ``uv`` venv.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx


PID_DESKTOP = Path("/tmp/friday-desktop.pid")
PID_VOICE   = Path("/tmp/friday-voice.pid")
PID_MCP     = Path("/tmp/friday-mcp.pid")
PID_ODYSSEUS = Path("/tmp/friday-odysseus.pid")

LOG_VOICE = Path("/tmp/friday-voice.log")
LOG_MCP   = Path("/tmp/friday-mcp.log")
LOG_ODYSSEUS = Path("/tmp/friday-odysseus.log")


def _read_pid(lock: Path) -> int | None:
    try:
        raw = lock.read_text().strip()
    except (FileNotFoundError, OSError):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _lock_is_live(lock: Path) -> bool:
    pid = _read_pid(lock)
    return pid is not None and _is_alive(pid)


def _wipe_stale(lock: Path) -> None:
    try:
        if lock.exists():
            lock.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------
# Desktop
# ---------------------------------------------------------------------

def desktop_is_running() -> bool:
    return _lock_is_live(PID_DESKTOP)


def ensure_desktop_running() -> dict:
    if desktop_is_running():
        return {"status": "already_running", "pid": _read_pid(PID_DESKTOP)}
    _wipe_stale(PID_DESKTOP)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "friday.desktop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception as exc:
        return {"status": "launch_failed", "error": str(exc)}
    return {"status": "launched", "pid": proc.pid}


# ---------------------------------------------------------------------
# MCP server  (`uv run friday` / `server:main`)
# ---------------------------------------------------------------------

def mcp_is_running() -> bool:
    return _lock_is_live(PID_MCP)


def ensure_mcp_running() -> dict:
    """Start the FastMCP/SSE server if no lock holder is alive."""
    if mcp_is_running():
        return {"status": "already_running", "pid": _read_pid(PID_MCP)}
    _wipe_stale(PID_MCP)
    try:
        LOG_MCP.touch(exist_ok=True)
        log = LOG_MCP.open("a", buffering=1)
        proc = subprocess.Popen(
            [sys.executable, "-c", "from server import main; main()"],
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
        PID_MCP.write_text(str(proc.pid))
    except Exception as exc:
        return {"status": "launch_failed", "error": str(exc)}
    return {"status": "launched", "pid": proc.pid, "log": str(LOG_MCP)}


# ---------------------------------------------------------------------
# Voice agent (`uv run friday_voice` / `agent_friday:dev`)
# ---------------------------------------------------------------------

def voice_is_running() -> bool:
    return _lock_is_live(PID_VOICE)


def ensure_voice_running() -> dict:
    """Start the LiveKit voice agent if no lock holder is alive."""
    if voice_is_running():
        return {"status": "already_running", "pid": _read_pid(PID_VOICE)}
    _wipe_stale(PID_VOICE)
    try:
        LOG_VOICE.touch(exist_ok=True)
        log = LOG_VOICE.open("a", buffering=1)
        # ``agent_friday:dev`` injects "dev" into argv if missing and
        # hands off to LiveKit's cli.run_app — same path as
        # ``uv run friday_voice``.
        proc = subprocess.Popen(
            [sys.executable, "-c", "from agent_friday import dev; dev()"],
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
        PID_VOICE.write_text(str(proc.pid))
    except Exception as exc:
        return {"status": "launch_failed", "error": str(exc)}
    return {"status": "launched", "pid": proc.pid, "log": str(LOG_VOICE)}


# ---------------------------------------------------------------------
# Odysseus (`uvicorn app:app` in the Odysseus repo)
# ---------------------------------------------------------------------

def _odysseus_base_url() -> str:
    return os.getenv("ODYSSEUS_BASE_URL", "http://127.0.0.1:7870").strip().rstrip("/")


def _odysseus_repo() -> Path:
    return Path(os.getenv("ODYSSEUS_REPO", "/Users/dhruvsmac/Desktop/odysseus")).expanduser().resolve()


def _odysseus_port() -> str:
    parsed = urlparse(_odysseus_base_url())
    return str(parsed.port or (443 if parsed.scheme == "https" else 80))


def _odysseus_python(repo: Path) -> str:
    venv_python = repo / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    legacy_venv_python = repo / "venv" / "bin" / "python"
    if legacy_venv_python.exists():
        return str(legacy_venv_python)
    return sys.executable


def odysseus_is_running() -> bool:
    try:
        response = httpx.get(f"{_odysseus_base_url()}/api/health", timeout=1.5)
        return response.status_code == 200
    except Exception:
        return False


def ensure_odysseus_running() -> dict:
    """Start Odysseus if the configured localhost health endpoint is down."""
    if odysseus_is_running():
        return {"status": "already_running"}
    _wipe_stale(PID_ODYSSEUS)
    repo = _odysseus_repo()
    if not (repo / "app.py").exists():
        return {"status": "launch_failed", "error": f"Odysseus repo not found: {repo}"}
    try:
        LOG_ODYSSEUS.touch(exist_ok=True)
        log = LOG_ODYSSEUS.open("a", buffering=1)
        env = os.environ.copy()
        env["AUTH_ENABLED"] = os.getenv("ODYSSEUS_AUTH_ENABLED", "false")
        proc = subprocess.Popen(
            [
                _odysseus_python(repo),
                "-m",
                "uvicorn",
                "app:app",
                "--host",
                "127.0.0.1",
                "--port",
                _odysseus_port(),
            ],
            cwd=str(repo),
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
        log.close()
        PID_ODYSSEUS.write_text(str(proc.pid))
    except Exception as exc:
        return {"status": "launch_failed", "error": str(exc)}
    return {"status": "launched", "pid": proc.pid, "log": str(LOG_ODYSSEUS)}


# ---------------------------------------------------------------------
# Shutdown helpers
# ---------------------------------------------------------------------

def terminate_if_owned(lock: Path) -> None:
    """SIGTERM the process named by ``lock`` and clear the lock."""
    pid = _read_pid(lock)
    if pid is None:
        return
    try:
        os.kill(pid, 15)   # SIGTERM
    except (ProcessLookupError, PermissionError, OSError):
        pass
    _wipe_stale(lock)
