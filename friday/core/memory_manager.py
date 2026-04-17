"""Enhanced memory system — aios-local pattern with episodic + working memory."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class MemoryManager:
    """Manages working memory (context window) and episodic memory (stored episodes).

    Pattern from aios-local/core/memory.py:
    - Working: Last 100 messages, retrieved for context
    - Episodic: Saved task outcomes with similarity search
    """

    def __init__(self, episodes_path: Path, memory_file: Path, max_working: int = 100, max_episodes: int = 200):
        self.working: list[dict] = []
        self.episodes_path = Path(episodes_path)
        self.memory_file = Path(memory_file)
        self.max_working = max_working
        self.max_episodes = max_episodes

        # Ensure directories exist
        self.episodes_path.mkdir(parents=True, exist_ok=True)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Working Memory
    # ------------------------------------------------------------------

    def add_working(self, role: str, content: str, metadata: dict | None = None):
        """Add a message to working memory."""
        entry = {
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self.working.append(entry)
        # Prune if exceeds max
        if len(self.working) > self.max_working:
            self.working = self.working[-self.max_working:]

    def get_working_context(self, max_chars: int = 8000, last_n: int = 20) -> str:
        """Get recent working memory as context string."""
        recent = self.working[-last_n:]
        lines = [f"{m['role']}: {m['content'][:500]}" for m in recent]
        text = "\n".join(lines)
        return text[-max_chars:] if len(text) > max_chars else text

    def clear_working(self):
        """Clear working memory."""
        self.working = []

    # ------------------------------------------------------------------
    # Episodic Memory
    # ------------------------------------------------------------------

    def save_episode(
        self,
        task: str,
        outcome: str,
        tools_used: list[str],
        agent_role: str = "friday",
        metadata: dict | None = None,
    ) -> dict:
        """Save a task episode to long-term memory."""
        episode = {
            "id": hashlib.md5(f"{task}{time.time()}".encode()).hexdigest()[:12],
            "task": task,
            "outcome": outcome,
            "tools_used": tools_used,
            "agent": agent_role,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_count": len(self.working),
            "metadata": metadata or {},
        }
        path = self.episodes_path / f"{episode['id']}.json"
        path.write_text(json.dumps(episode, ensure_ascii=False, indent=2), "utf-8")
        self._prune_episodes()
        return episode

    def _prune_episodes(self):
        """Remove oldest episodes if over limit."""
        files = sorted(self.episodes_path.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if len(files) <= self.max_episodes:
            return
        for f in files[: len(files) - self.max_episodes]:
            try:
                f.unlink()
            except Exception:
                pass

    def get_relevant_episodes(self, query: str, limit: int = 3) -> list[dict]:
        """Find episodes similar to query using simple word overlap."""
        episodes = []
        for f in self.episodes_path.glob("*.json"):
            try:
                episodes.append(json.loads(f.read_text("utf-8")))
            except Exception:
                pass

        if not episodes:
            return []

        query_words = set(query.lower().split())
        scored = []
        for ep in episodes:
            task_words = set(ep.get("task", "").lower().split())
            outcome_words = set(ep.get("outcome", "").lower().split())
            all_words = task_words | outcome_words
            overlap = len(query_words & all_words) / max(len(query_words), 1)
            scored.append((ep, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [ep for ep, s in scored[:limit] if s > 0.1]

    def list_episodes(self, limit: int = 50) -> list[dict]:
        """List recent episodes."""
        files = sorted(self.episodes_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        episodes = []
        for f in files[:limit]:
            try:
                episodes.append(json.loads(f.read_text("utf-8")))
            except Exception:
                pass
        return episodes

    # ------------------------------------------------------------------
    # Long-term Facts (from existing memory.py)
    # ------------------------------------------------------------------

    def read_facts(self) -> list[dict]:
        """Read long-term facts from memory file."""
        if not self.memory_file.exists():
            return []
        try:
            return json.loads(self.memory_file.read_text("utf-8"))
        except Exception:
            return []

    def save_fact(self, category: str, content: str) -> dict:
        """Save a fact to long-term memory."""
        facts = self.read_facts()
        fact = {
            "id": hashlib.md5(f"{category}{content}{time.time()}".encode()).hexdigest()[:8],
            "category": category,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        facts.append(fact)
        self.memory_file.write_text(json.dumps(facts, ensure_ascii=False, indent=2), "utf-8")
        return fact

    def search_facts(self, query: str, category: str | None = None) -> list[dict]:
        """Search facts by query and optional category."""
        facts = self.read_facts()
        query_lower = query.lower()
        results = []
        for fact in facts:
            if category and fact.get("category") != category:
                continue
            if query_lower in fact.get("content", "").lower():
                results.append(fact)
        return results
