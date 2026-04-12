"""
Data resources — expose static content or dynamic data via MCP resources.
"""

import datetime


def register(mcp):

    @mcp.resource("friday://info")
    def server_info() -> str:
        """Returns basic info about this MCP server."""
        return (
            "Friday MCP Server\n"
            "A Tony Stark-inspired AI assistant.\n"
            "Built with FastMCP."
        )
    
    @mcp.resource("friday://status")
    def status():
        """Returns MCSP server uptime."""
        return f"Server running since {datetime.datetime.now()}"
