"""
Memory tools — persistent per-user memory for FRIDAY.

Two kinds of entries share one JSON file:
  - "fact"  : stable truths (user name, preferences, home city)
  - "event" : time-stamped things that happened ("watched Ironman on 2026-04-10")

Inspired by Desktop/jarvis/memory.py and aios-local/core/memory.py.
Keeps the implementation dependency-free (no vector DB) so it boots cold;
swap in FAISS/Chroma later if recall quality demands it.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

MEMORY_PATH = Path(os.getenv("FRIDAY_MEMORY_PATH", Path.home() / ".friday" / "memory.json"))


def _load() -> list[dict[str, Any]]:
    if not MEMORY_PATH.exists():
        return []
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _append(kind: str, content: str, tags: list[str]) -> dict[str, Any]:
    entries = _load()
    entry = {
        "id": uuid.uuid4().hex[:8],
        "kind": kind,
        "content": content,
        "tags": [t.lower().strip() for t in tags if t.strip()],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    entries.append(entry)
    _save(entries)
    return entry


def _search(query: str, kind: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    q = query.lower().strip()
    terms = [t for t in q.split() if t]
    hits = []
    for e in _load():
        if kind and e.get("kind") != kind:
            continue
        haystack = (e.get("content", "") + " " + " ".join(e.get("tags", []))).lower()
        if not terms or all(t in haystack for t in terms):
            hits.append(e)
    hits.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return hits[:limit]


def _delete(entry_id: str) -> bool:
    entries = _load()
    before = len(entries)
    entries = [e for e in entries if e.get("id") != entry_id]
    if len(entries) == before:
        return False
    _save(entries)
    return True


def register(mcp):

    @mcp.tool()
    async def remember_fact(content: str, tags: str = "") -> str:
        """
        Save a durable fact about the user (name, preferences, home, family, etc.).
        Tags are comma-separated for later recall.
        """
        entry = await asyncio.to_thread(_append, "fact", content, tags.split(","))
        return f"Noted. [{entry['id']}]"

    @mcp.tool()
    async def remember_event(content: str, tags: str = "") -> str:
        """Log a time-stamped event the user mentioned ('I watched X today')."""
        entry = await asyncio.to_thread(_append, "event", content, tags.split(","))
        return f"Logged. [{entry['id']}]"

    @mcp.tool()
    async def recall(query: str, kind: str = "", limit: int = 5) -> str:
        """
        Search memory. `kind` can be '', 'fact', or 'event'.
        Empty query lists the most recent N entries.
        """
        kind_arg = kind if kind in ("fact", "event") else None
        hits = await asyncio.to_thread(_search, query, kind_arg, max(1, min(int(limit), 20)))
        if not hits:
            return "Nothing in memory matches that, boss."
        lines = [f"Recall ({len(hits)} hit{'s' if len(hits) != 1 else ''}):"]
        for e in hits:
            lines.append(f"  [{e['id']}] ({e['kind']}, {e['created_at']}) {e['content']}")
        return "\n".join(lines)

    @mcp.tool()
    async def forget(entry_id: str) -> str:
        """Delete a memory entry by ID (use the ID returned from recall)."""
        ok = await asyncio.to_thread(_delete, entry_id)
        return "Forgotten." if ok else f"No entry with id {entry_id!r}."
