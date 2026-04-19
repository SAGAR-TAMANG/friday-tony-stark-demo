"""
Friday MCP Server — Entry Point

Transports:
  - streamable-http  (default, MCP spec 2025-03-26; URL: /mcp)
  - sse              (legacy; kept for LiveKit-plugin fallback; URL: /sse)
  - stdio            (for local subprocess embedding)

Select via env var MCP_TRANSPORT. Run with: uv run friday
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from friday.config import config
from friday.core.persistence import DatabaseManager
from friday.prompts import register_all_prompts
from friday.resources import register_all_resources
from friday.tools import register_all_tools

# Initialize database manager
_db_manager = DatabaseManager(config.FRIDAY_DB_PATH)

mcp = FastMCP(
    name=config.SERVER_NAME,
    instructions=(
        "You are Friday, a Tony Stark-style AI assistant. "
        "You have access to a set of tools to help the user. "
        "Be concise, accurate, and a little witty."
    ),
)

register_all_tools(mcp)
register_all_prompts(mcp)
register_all_resources(mcp)


@mcp.tool()
async def get_telemetry_stats(hours: int = 24) -> str:
    """Get FRIDAY usage statistics.

    Args:
        hours: Time window in hours (default: 24)
    """
    stats = _db_manager.get_stats(hours=hours)
    lines = [
        f"Telemetry (last {stats['hours']}h):",
        f"  Total events: {stats['total_events']}",
        "  By type:",
    ]
    for event_type, count in stats['by_type'].items():
        lines.append(f"    {event_type}: {count}")
    return "\n".join(lines)


@mcp.tool()
async def get_execution_traces(tool_name: str = "", limit: int = 50) -> str:
    """Get recent tool execution traces for debugging.

    Args:
        tool_name: Filter by specific tool (optional)
        limit: Maximum traces to return (default: 50)
    """
    traces = _db_manager.get_traces(
        tool_name=tool_name if tool_name else None,
        limit=limit
    )
    if not traces:
        return "No execution traces found."

    lines = [f"Recent execution traces ({len(traces)} shown):\n"]
    for t in traces:
        status = "✓" if t.success else "✗"
        lines.append(f"[{status}] {t.tool_name} ({t.elapsed_ms:.1f}ms)")
        lines.append(f"    Trace ID: {t.trace_id}")
        if t.error:
            lines.append(f"    Error: {t.error[:100]}")

    return "\n".join(lines)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    print(f"[Friday] MCP server starting | transport={transport}")
    print(f"[Friday] Database: {config.FRIDAY_DB_PATH}")
    print(f"[Friday] Home: {config.FRIDAY_HOME}")

    # Log startup event
    _db_manager.log_event("server_startup", {"transport": transport})

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
