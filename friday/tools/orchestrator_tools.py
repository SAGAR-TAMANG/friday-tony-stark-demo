"""Orchestrator tools — Multi-agent coordination and task management."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from friday.core.orchestrator import AgentDefinition, AgentOrchestrator, DEFAULT_AGENTS
from friday.core.persistence import DatabaseManager
from friday.core.memory_manager import MemoryManager
from friday.core.a2a import get_a2a_bus

# Initialize orchestrator
_orchestrator: AgentOrchestrator | None = None


def _get_orchestrator() -> AgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        friday_home = Path(os.getenv("FRIDAY_HOME", Path.home() / ".friday"))

        memory = MemoryManager(
            episodes_path=friday_home / "episodes",
            memory_file=friday_home / "long_term_memory.json",
        )

        db = DatabaseManager(friday_home / "databases")
        a2a_bus = get_a2a_bus(friday_home / "a2a_history.json")

        _orchestrator = AgentOrchestrator(
            memory_manager=memory,
            db_manager=db,
            a2a_bus=a2a_bus,
        )

        # Register default agents
        for agent_def in DEFAULT_AGENTS.values():
            _orchestrator.register_agent(agent_def)

    return _orchestrator


def register(mcp):
    """Register orchestrator tools with MCP server."""

    @mcp.tool()
    async def agent_create_task(
        task_type: str,
        description: str,
        input_data: str = "",
        preferred_agent: str = "",
    ) -> str:
        """Create and queue a new task for an agent.

        Args:
            task_type: Type of task (e.g., 'coding', 'research', 'shell')
            description: Task description
            input_data: JSON string of input data
            preferred_agent: Specific agent to assign (auto-routed if empty)
        """
        orchestrator = _get_orchestrator()

        try:
            data = json.loads(input_data) if input_data else {}
        except json.JSONDecodeError:
            return "[ORCHESTRATOR ERROR] Invalid input_data JSON"

        task = orchestrator.create_task(
            task_type=task_type,
            description=description,
            input_data=data,
            preferred_agent=preferred_agent if preferred_agent else None,
        )

        return (
            f"[ORCHESTRATOR] Task created: {task.id}\n"
            f"  Type: {task.task_type}\n"
            f"  Assigned to: {task.assigned_agent or 'PENDING'}\n"
            f"  Status: {task.status}"
        )

    @mcp.tool()
    async def agent_execute_task(task_id: str) -> str:
        """Execute a task and wait for completion.

        Args:
            task_id: Task ID from agent_create_task
        """
        orchestrator = _get_orchestrator()

        if task_id not in orchestrator.tasks:
            return f"[ORCHESTRATOR ERROR] Task not found: {task_id}"

        task = await orchestrator.execute_task(task_id)

        lines = [
            f"[ORCHESTRATOR] Task {task.id} completed:",
            f"  Status: {task.status}",
            f"  Agent: {task.assigned_agent}",
        ]

        if task.result:
            lines.append(f"  Result: {json.dumps(task.result, indent=2)[:500]}")

        return "\n".join(lines)

    @mcp.tool()
    async def agent_list_tasks(status: str = "", limit: int = 20) -> str:
        """List recent tasks.

        Args:
            status: Filter by status ('pending', 'running', 'completed', 'failed')
            limit: Maximum tasks to show (default: 20)
        """
        orchestrator = _get_orchestrator()
        tasks = orchestrator.list_tasks(
            status=status if status else None,
            limit=limit,
        )

        if not tasks:
            return "[ORCHESTRATOR] No tasks found"

        lines = [f"[ORCHESTRATOR] Recent tasks ({len(tasks)} shown):\n"]
        for t in tasks:
            lines.append(f"[{t['id']}] {t['type']} → {t['status']}")
            lines.append(f"   {t['description']}")
            lines.append(f"   Agent: {t['agent']}")

        return "\n".join(lines)

    @mcp.tool()
    async def agent_get_task_status(task_id: str) -> str:
        """Get detailed status of a task.

        Args:
            task_id: Task ID to check
        """
        orchestrator = _get_orchestrator()
        status = orchestrator.get_task_status(task_id)

        if not status:
            return f"[ORCHESTRATOR ERROR] Task not found: {task_id}"

        lines = [
            f"[ORCHESTRATOR] Task {status['id']}:",
            f"  Type: {status['type']}",
            f"  Status: {status['status']}",
            f"  Agent: {status['agent']}",
            f"  Created: {status['created']}",
        ]

        if status.get('started'):
            lines.append(f"  Started: {status['started']}")
        if status.get('completed'):
            lines.append(f"  Completed: {status['completed']}")
        if status.get('result'):
            lines.append(f"  Result: {json.dumps(status['result'], indent=2)[:400]}")

        return "\n".join(lines)

    @mcp.tool()
    async def agent_list_available() -> str:
        """List all available agents and their capabilities."""
        orchestrator = _get_orchestrator()

        if not orchestrator.agents:
            return "[ORCHESTRATOR] No agents registered"

        lines = [f"[ORCHESTRATOR] Available agents ({len(orchestrator.agents)}):\n"]
        for name, agent in orchestrator.agents.items():
            lines.append(f"  {name}")
            lines.append(f"    {agent.description}")
            lines.append(f"    Capabilities: {', '.join(agent.capabilities)}")
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def agent_register(
        name: str,
        description: str,
        capabilities: str,
        system_prompt: str,
        model: str = "gemini-2.5-pro",
    ) -> str:
        """Register a new specialized agent.

        Args:
            name: Agent name (unique identifier)
            description: What this agent does
            capabilities: Comma-separated list of capabilities
            system_prompt: System prompt for the agent
            model: LLM model to use (default: gemini-2.5-pro)
        """
        orchestrator = _get_orchestrator()

        agent = AgentDefinition(
            name=name,
            description=description,
            capabilities=[c.strip() for c in capabilities.split(",")],
            system_prompt=system_prompt,
            model=model,
        )

        orchestrator.register_agent(agent)
        return f"[ORCHESTRATOR] Registered agent: {name}"

    @mcp.tool()
    async def agent_delegated_task(
        task_description: str,
        required_capability: str,
    ) -> str:
        """Create and execute a task with automatic agent selection.

        Args:
            task_description: Description of what needs to be done
            required_capability: Required agent capability
        """
        orchestrator = _get_orchestrator()

        # Create task
        task = orchestrator.create_task(
            task_type=required_capability,
            description=task_description,
            input_data={"auto": True},
        )

        if not task.assigned_agent:
            return f"[ORCHESTRATOR] No agent available for capability: {required_capability}"

        # Execute immediately
        completed_task = await orchestrator.execute_task(task.id)

        return (
            f"[ORCHESTRATOR] Delegated task completed:\n"
            f"  Task: {task_description[:60]}...\n"
            f"  Assigned to: {completed_task.assigned_agent}\n"
            f"  Status: {completed_task.status}\n"
            f"  Result: {json.dumps(completed_task.result)[:300] if completed_task.result else 'None'}"
        )
