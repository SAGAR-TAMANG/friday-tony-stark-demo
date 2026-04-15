"""
Tool registry — imports and registers all tool modules with the MCP server.
Add new tool modules here as you build them.
"""

from friday.tools import calculator, finance, reminders, system, tickets, utils, weather, web


def register_all_tools(mcp):
    """Register all tool groups onto the MCP server instance."""
    web.register(mcp)
    system.register(mcp)
    weather.register(mcp)
    finance.register(mcp)
    tickets.register(mcp)
    reminders.register(mcp)
    calculator.register(mcp)
    utils.register(mcp)
