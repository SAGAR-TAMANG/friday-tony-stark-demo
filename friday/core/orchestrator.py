"""Agent Orchestrator — Multi-agent coordination and task routing.

Pattern from agency-agents: central orchestrator that can spawn specialized
agents for different tasks, with routing based on task type.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from friday.core.a2a import A2ABus, A2AMessage, get_a2a_bus
from friday.core.memory_manager import MemoryManager
from friday.core.persistence import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class AgentTask:
    """A task assigned to an agent."""
    id: str
    task_type: str
    description: str
    input_data: dict
    assigned_agent: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class AgentDefinition:
    """Definition of a specialized agent."""
    name: str
    description: str
    capabilities: list[str]
    system_prompt: str
    model: str = "gemini-2.5-pro"
    temperature: float = 0.7
    max_tokens: int = 4096


class AgentOrchestrator:
    """Orchestrates multiple specialized agents.

    Key features:
    - Task routing to appropriate agents based on task type
    - A2A message bus for inter-agent communication
    - Task lifecycle management
    - Result aggregation
    """

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        db_manager: Optional[DatabaseManager] = None,
        a2a_bus: Optional[A2ABus] = None,
    ):
        self.agents: dict[str, AgentDefinition] = {}
        self.tasks: dict[str, AgentTask] = {}
        self.memory = memory_manager
        self.db = db_manager
        self.a2a = a2a_bus or get_a2a_bus()
        self.running = False
        self._task_handlers: dict[str, Callable[[AgentTask], dict]] = {}
        self._agent_instances: dict[str, Any] = {}

    def register_agent(self, definition: AgentDefinition) -> None:
        """Register a specialized agent definition."""
        self.agents[definition.name] = definition
        logger.info(f"Registered agent: {definition.name}")

        # Register A2A handler
        self.a2a.register_handler(definition.name, self._handle_a2a_message)

    def register_task_handler(self, task_type: str, handler: Callable[[AgentTask], dict]) -> None:
        """Register a handler for a specific task type."""
        self._task_handlers[task_type] = handler

    def create_task(
        self,
        task_type: str,
        description: str,
        input_data: dict,
        preferred_agent: Optional[str] = None,
    ) -> AgentTask:
        """Create and route a new task."""
        import uuid

        task_id = str(uuid.uuid4())[:8]
        task = AgentTask(
            id=task_id,
            task_type=task_type,
            description=description,
            input_data=input_data,
            assigned_agent=preferred_agent or self._route_task(task_type),
        )
        self.tasks[task_id] = task

        # Persist if DB available
        if self.db:
            self.db.log_event("task_created", {
                "task_id": task_id,
                "task_type": task_type,
                "agent": task.assigned_agent,
            })

        return task

    def _route_task(self, task_type: str) -> Optional[str]:
        """Route a task to the best agent based on task type and capabilities."""
        # Simple routing: match task_type to agent capabilities
        for name, agent in self.agents.items():
            if task_type in agent.capabilities or task_type in agent.name.lower():
                return name

        # Default to first agent if no match
        if self.agents:
            return list(self.agents.keys())[0]

        return None

    async def execute_task(self, task_id: str) -> AgentTask:
        """Execute a task and return the completed task."""
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        if not task.assigned_agent:
            task.status = "failed"
            task.result = {"error": "No agent available for this task"}
            return task

        task.status = "running"
        task.started_at = datetime.now(timezone.utc).isoformat()

        try:
            # Get handler for task type
            handler = self._task_handlers.get(task.task_type)

            if handler:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, handler, task
                )
                task.result = result
                task.status = "completed" if result.get("success", True) else "failed"
            else:
                # Default execution: send via A2A
                message = A2AMessage.create(
                    from_agent="orchestrator",
                    to_agent=task.assigned_agent,
                    content=json.dumps(task.input_data),
                    message_type="task",
                    metadata={"task_id": task_id, "task_type": task.task_type},
                )
                self.a2a.send(message)

                # Wait for response (simple implementation)
                await asyncio.sleep(0.1)
                task.status = "completed"
                task.result = {"status": "sent_via_a2a", "agent": task.assigned_agent}

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            task.status = "failed"
            task.result = {"error": str(e)}

        task.completed_at = datetime.now(timezone.utc).isoformat()

        # Save episode to memory
        if self.memory:
            self.memory.save_episode(
                task=task.description,
                outcome=json.dumps(task.result) if task.result else "",
                tools_used=[task.assigned_agent or "unknown"],
                agent_role=task.assigned_agent or "orchestrator",
            )

        return task

    async def execute_parallel(self, task_ids: list[str]) -> list[AgentTask]:
        """Execute multiple tasks in parallel."""
        tasks = [self.execute_task(tid) for tid in task_ids]
        return await asyncio.gather(*tasks)

    def _handle_a2a_message(self, message: A2AMessage) -> None:
        """Handle incoming A2A messages."""
        logger.info(f"A2A message for {message.to_agent}: {message.message_type}")

        # Check if it's a task response
        if message.message_type == "response" and message.reply_to:
            task_id = message.metadata.get("task_id")
            if task_id and task_id in self.tasks:
                task = self.tasks[task_id]
                task.status = "completed"
                task.result = {"response": message.content}
                task.completed_at = datetime.now(timezone.utc).isoformat()

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """Get status of a task."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        return {
            "id": task.id,
            "type": task.task_type,
            "status": task.status,
            "agent": task.assigned_agent,
            "created": task.created_at,
            "started": task.started_at,
            "completed": task.completed_at,
            "result": task.result,
        }

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        """List tasks with optional filtering."""
        tasks = list(self.tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sort by created date (newest first)
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return [
            {
                "id": t.id,
                "type": t.task_type,
                "description": t.description[:80] + "..." if len(t.description) > 80 else t.description,
                "status": t.status,
                "agent": t.assigned_agent,
            }
            for t in tasks[:limit]
        ]

    async def run_agent_loop(self, agent_name: str) -> None:
        """Run an agent's message processing loop."""
        self.running = True

        while self.running:
            message = self.a2a.receive_nowait(agent_name)

            if message:
                logger.info(f"[{agent_name}] Processing message: {message.id}")

                # Process message based on type
                if message.message_type == "task":
                    # Execute task and send response
                    response = A2AMessage.create(
                        from_agent=agent_name,
                        to_agent=message.from_agent,
                        content=f"Task processed by {agent_name}",
                        message_type="response",
                        reply_to=message.id,
                        metadata=message.metadata,
                    )
                    self.a2a.send(response)

            await asyncio.sleep(0.1)  # 100ms tick

    def stop(self) -> None:
        """Stop the orchestrator."""
        self.running = False


# Pre-defined agent definitions (inspired by agency-agents)
DEFAULT_AGENTS = {
    "friday-core": AgentDefinition(
        name="friday-core",
        description="FRIDAY's core reasoning and coordination agent",
        capabilities=["reasoning", "coordination", "planning"],
        system_prompt="You are FRIDAY, a Tony Stark-inspired AI assistant. Be concise, accurate, and witty.",
    ),
    "code-agent": AgentDefinition(
        name="code-agent",
        description="Specialized in code generation and review",
        capabilities=["coding", "python", "javascript", "review"],
        system_prompt="You are a senior software engineer. Write clean, efficient, well-documented code.",
    ),
    "research-agent": AgentDefinition(
        name="research-agent",
        description="Specialized in web research and information gathering",
        capabilities=["research", "search", "analysis"],
        system_prompt="You are a research analyst. Gather accurate, current information and provide sources.",
    ),
    "shell-agent": AgentDefinition(
        name="shell-agent",
        description="Specialized in shell commands and system operations",
        capabilities=["shell", "system", "devops"],
        system_prompt="You are a DevOps engineer. Execute shell commands safely and efficiently.",
    ),
}
