"""Enhanced memory tools using MemoryManager from aios-local pattern."""

from __future__ import annotations

import os
from pathlib import Path

from friday.core.memory_manager import MemoryManager

# Initialize memory manager with paths in ~/.friday
_friday_home = Path(os.getenv("FRIDAY_HOME", Path.home() / ".friday"))
_memory_manager = MemoryManager(
    episodes_path=_friday_home / "episodes",
    memory_file=_friday_home / "long_term_memory.json",
    max_working=100,
    max_episodes=200,
)


def register(mcp):
    """Register enhanced memory tools with MCP server."""

    @mcp.tool()
    async def memory_add_working(role: str, content: str) -> str:
        """Add a message to working memory (short-term context).

        Args:
            role: Who said it (e.g., 'user', 'assistant', 'system')
            content: The message content
        """
        _memory_manager.add_working(role, content)
        return f"Added to working memory. Current size: {len(_memory_manager.working)}"

    @mcp.tool()
    async def memory_get_context(max_chars: int = 8000) -> str:
        """Get recent working memory as context for the LLM.

        Args:
            max_chars: Maximum characters to return (default: 8000)
        """
        return _memory_manager.get_working_context(max_chars=max_chars)

    @mcp.tool()
    async def memory_save_episode(task: str, outcome: str, tools_used: list[str]) -> str:
        """Save a completed task to episodic long-term memory.

        Args:
            task: Description of the task
            outcome: What happened / result
            tools_used: List of tools that were used
        """
        episode = _memory_manager.save_episode(task, outcome, tools_used)
        return f"Episode saved with ID: {episode['id']}"

    @mcp.tool()
    async def memory_recall_episodes(query: str, limit: int = 3) -> str:
        """Recall relevant past episodes based on query similarity.

        Args:
            query: Search query to find similar episodes
            limit: Maximum episodes to return (default: 3)
        """
        episodes = _memory_manager.get_relevant_episodes(query, limit)
        if not episodes:
            return f"No relevant episodes found for: {query}"

        lines = [f"Found {len(episodes)} relevant episode(s):\n"]
        for ep in episodes:
            lines.append(f"\n[ID: {ep['id']}] {ep['task'][:80]}")
            lines.append(f"  Outcome: {ep['outcome'][:100]}...")
            lines.append(f"  Tools: {', '.join(ep['tools_used'])}")
            lines.append(f"  When: {ep['timestamp'][:10]}")

        return "\n".join(lines)

    @mcp.tool()
    async def memory_list_episodes(limit: int = 20) -> str:
        """List recent episodes from memory.

        Args:
            limit: Maximum episodes to list (default: 20)
        """
        episodes = _memory_manager.list_episodes(limit)
        if not episodes:
            return "No episodes in memory."

        lines = [f"Recent episodes ({len(episodes)} total):\n"]
        for ep in episodes:
            lines.append(f"\n[{ep['id']}] {ep['task'][:60]}...")
            lines.append(f"   Agent: {ep['agent']} | Tools: {len(ep['tools_used'])} | {ep['timestamp'][:10]}")

        return "\n".join(lines)

    @mcp.tool()
    async def memory_save_fact(category: str, content: str) -> str:
        """Save a long-term fact to memory.

        Args:
            category: Category of the fact (e.g., 'preference', 'contact', 'task')
            content: The fact content
        """
        fact = _memory_manager.save_fact(category, content)
        return f"Fact saved with ID: {fact['id']} in category '{category}'"

    @mcp.tool()
    async def memory_search_facts(query: str, category: str = "") -> str:
        """Search saved facts by query and optional category.

        Args:
            query: Search query
            category: Optional category filter
        """
        facts = _memory_manager.search_facts(query, category if category else None)
        if not facts:
            return f"No facts found for query: {query}"

        lines = [f"Found {len(facts)} fact(s):\n"]
        for f in facts:
            lines.append(f"\n[{f['id']}] {f['category']}")
            lines.append(f"  {f['content'][:200]}")

        return "\n".join(lines)

    @mcp.tool()
    async def memory_clear_working() -> str:
        """Clear working memory (short-term context window)."""
        count = len(_memory_manager.working)
        _memory_manager.clear_working()
        return f"Working memory cleared. Removed {count} messages."
