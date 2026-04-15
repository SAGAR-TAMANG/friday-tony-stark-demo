"""
Reminders tool — lightweight in-memory note store for the current session.
Notes survive as long as the MCP server process is running.
"""

from datetime import datetime, timezone

# Module-level store: list of {id, text, created_at}
_store: list[dict] = []
_next_id: int = 1


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


def register(mcp):

    @mcp.tool()
    def add_reminder(text: str) -> str:
        """
        Save a note or reminder for the current session.
        Use when the boss says 'remember that', 'note this', 'remind me', etc.
        """
        global _next_id
        _store.append({"id": _next_id, "text": text, "created_at": _ts()})
        _next_id += 1
        return f"Noted, boss. I'll keep that in mind: '{text}'"

    @mcp.tool()
    def list_reminders() -> str:
        """
        Recall all notes saved this session.
        Use when the boss asks 'what did I tell you?', 'any notes?', 'what am I remembering?'.
        """
        if not _store:
            return "Nothing on the mental stack, sir. Clean slate."

        lines = [f"### SESSION NOTES ({len(_store)})"]
        for r in _store:
            lines.append(f"[{r['id']}] {r['text']}  — saved at {r['created_at']}")
        return "\n".join(lines)

    @mcp.tool()
    def clear_reminders() -> str:
        """
        Wipe all session notes.
        Use when the boss says 'clear my notes', 'forget that', 'wipe the slate'.
        """
        count = len(_store)
        _store.clear()
        return f"Done — cleared {count} note{'s' if count != 1 else ''}, sir."
