"""
Reminders tool — session notes with cross-session persistence.

Notes are kept in memory for fast access and mirrored to
~/.friday/reminders.json so they survive MCP server restarts and reboots.
If the disk write fails (permissions, full disk), reminders still work in
memory — the store is best-effort, never blocks the user.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# WHY Path.home(): cross-platform (works on Windows/WSL/Linux/macOS without
# path hardcoding) and predictable for the user — they know where their notes
# live if they ever want to back them up or wipe them manually.
_STORE_PATH = Path.home() / ".friday" / "reminders.json"

_store: list[dict] = []
_next_id: int = 1
_loaded: bool = False


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


def _load_once() -> None:
    """Populate _store from disk on first access. Idempotent."""
    global _store, _next_id, _loaded
    if _loaded:
        return
    _loaded = True
    if not _STORE_PATH.exists():
        return
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        _store = data.get("reminders", [])
        _next_id = data.get("next_id", len(_store) + 1)
        logger.info("loaded %d reminders from %s", len(_store), _STORE_PATH)
    except (json.JSONDecodeError, OSError) as exc:
        # Corrupt or unreadable file — keep empty store, log but don't crash.
        logger.warning("could not load reminders from %s: %s", _STORE_PATH, exc)


def _persist() -> None:
    """Flush _store to disk. Never raises — persistence is best-effort."""
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(
            json.dumps({"reminders": _store, "next_id": _next_id}, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("could not persist reminders to %s: %s", _STORE_PATH, exc)


def register(mcp):

    @mcp.tool()
    def add_reminder(text: str) -> str:
        """
        Save a note or reminder. Notes persist across sessions at
        ~/.friday/reminders.json — the boss can rely on them across restarts.
        Use when the boss says 'remember that', 'note this', 'remind me', etc.
        """
        global _next_id
        _load_once()
        _store.append({"id": _next_id, "text": text, "created_at": _ts()})
        _next_id += 1
        _persist()
        return f"Noted, boss. I'll keep that in mind: '{text}'"

    @mcp.tool()
    def list_reminders() -> str:
        """
        Recall all saved notes (including those from previous sessions).
        Use when the boss asks 'what did I tell you?', 'any notes?', 'what am I remembering?'.
        """
        _load_once()
        if not _store:
            return "Nothing on the mental stack, sir. Clean slate."

        lines = [f"### NOTES ({len(_store)})"]
        for r in _store:
            lines.append(f"[{r['id']}] {r['text']}  — saved at {r['created_at']}")
        return "\n".join(lines)

    @mcp.tool()
    def clear_reminders() -> str:
        """
        Wipe all notes, including persisted ones on disk.
        Use when the boss says 'clear my notes', 'forget that', 'wipe the slate'.
        """
        _load_once()
        count = len(_store)
        _store.clear()
        _persist()
        return f"Done — cleared {count} note{'s' if count != 1 else ''}, sir."
