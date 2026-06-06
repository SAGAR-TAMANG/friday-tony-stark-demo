"""
Daily journal — auto-log every conversation turn into
Memory/Daily/YYYY-MM-DD.md so FRIDAY can recall recent context across
sessions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from friday.memory import vault


_MAX_RECALL_CHARS = 4000


def daily_path(now: Optional[datetime] = None) -> str:
    """Return the vault-relative path to today's journal note."""
    now = now or datetime.now()
    return f"Daily/{now:%Y-%m-%d}.md"


def append_turn(speaker: str, text: str, now: Optional[datetime] = None) -> Path:
    """Append a turn to today's journal. Creates the file with
    frontmatter on first call of the day."""
    now = now or datetime.now()
    rel = daily_path(now)
    block = f"\n## {now:%H:%M} — {speaker}\n\n{text.strip()}\n"
    frontmatter = {
        "date": f"{now:%Y-%m-%d}",
        "tags": ["daily", "friday-log"],
    }
    return vault.append_note(rel, block, frontmatter=frontmatter)


def recent_journal(days: int = 3) -> str:
    """Concatenate the last `days` daily notes for boot-time recall,
    trimmed to ~4k chars (most-recent last so the LLM weights it most)."""
    today = datetime.now()
    chunks: list[str] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        body = vault.read_note(daily_path(d))
        if body:
            chunks.append(f"### {d:%Y-%m-%d}\n{body.strip()}")
    if not chunks:
        return ""
    combined = "\n\n".join(chunks)
    if len(combined) > _MAX_RECALL_CHARS:
        combined = "…\n" + combined[-_MAX_RECALL_CHARS:]
    return combined
