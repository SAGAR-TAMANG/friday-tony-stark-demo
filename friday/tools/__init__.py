"""
Tool registry — imports and registers all tool modules with the MCP server.
Add new tool modules here as you build them.
"""

from friday.tools import (
    desktop,
    diagnostics,
    mac_worker,
    memory,
    messaging,
    odysseus,
    shell,
    spotify,
    web,
    system,
    utils,
)


def register_all_tools(mcp):
    """Register all tool groups onto the MCP server instance."""
    web.register(mcp)
    system.register(mcp)
    utils.register(mcp)
    desktop.register(mcp)
    mac_worker.register(mcp)
    messaging.register(mcp)
    memory.register(mcp)
    diagnostics.register(mcp)
    odysseus.register(mcp)
    shell.register(mcp)
    spotify.register(mcp)
