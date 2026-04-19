"""
Tool registry — imports and registers all tool modules with the MCP server.
Add new tool modules here as you build them.

Integrated tools from:
- OpenJarvis: shell, browser, git, skills
- SUPER AGI: code_runner
- aios-local: enhanced_memory, a2a_tools
- agency-agents: orchestrator_tools
- Original: web, news, finance, weather, notify, calendar, mail, memory, system, utils
"""

from friday.tools import (
    a2a_tools,
    browser,
    calendar,
    code_runner,
    enhanced_memory,
    finance,
    git,
    mail,
    memory,
    news,
    notify,
    orchestrator_tools,
    shell,
    skills,
    system,
    utils,
    weather,
    web,
)


def register_all_tools(mcp) -> None:
    """Register every tool group with the shared MCP instance."""
    # Original tools
    web.register(mcp)
    news.register(mcp)
    finance.register(mcp)
    weather.register(mcp)
    notify.register(mcp)
    calendar.register(mcp)
    mail.register(mcp)
    memory.register(mcp)
    system.register(mcp)
    utils.register(mcp)

    # OpenJarvis + SUPER AGI tools
    shell.register(mcp)
    browser.register(mcp)
    git.register(mcp)
    code_runner.register(mcp)

    # Enhanced memory (aios-local pattern)
    enhanced_memory.register(mcp)

    # A2A Protocol (aios-local)
    a2a_tools.register(mcp)

    # Orchestrator (agency-agents pattern)
    orchestrator_tools.register(mcp)

    # Skills management (OpenJarvis)
    skills.register(mcp)

    # Log registration
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Registered 18 tool modules with MCP server")
