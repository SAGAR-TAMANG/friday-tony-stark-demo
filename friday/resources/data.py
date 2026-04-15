"""
MCP Resources — dynamic data exposed to connected clients.
"""

import platform
from datetime import datetime, timezone


_TOOL_MANIFEST = {
    "web": ["get_world_news", "search_web", "fetch_url", "open_world_monitor"],
    "system": ["get_current_time", "get_system_info", "get_system_diagnostics"],
    "weather": ["get_weather"],
    "finance": ["get_stock_price", "get_market_overview"],
    "tickets": ["create_ticket", "list_tickets"],
    "reminders": ["add_reminder", "list_reminders", "clear_reminders"],
    "utils": ["calculate", "format_json", "word_count"],
}


def register(mcp):

    @mcp.resource("friday://info")
    def server_info() -> str:
        """Returns identity and runtime info about this MCP server."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            "F.R.I.D.A.Y. MCP Server\n"
            "Fully Responsive Intelligent Digital Assistant for You\n"
            f"Host OS  : {platform.system()} {platform.release()}\n"
            f"Python   : {platform.python_version()}\n"
            f"Online at: {now}\n"
            "Transport: SSE on port 8000"
        )

    @mcp.resource("friday://tools")
    def tool_manifest() -> dict:
        """Returns the full map of available tool modules and their tool names."""
        total = sum(len(v) for v in _TOOL_MANIFEST.values())
        return {
            "total_tools": total,
            "modules": _TOOL_MANIFEST,
        }
