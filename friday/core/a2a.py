"""A2A Protocol — Agent-to-Agent communication (aios-local pattern).

Enables FRIDAY to communicate with other agents, delegate tasks,
and participate in multi-agent workflows.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class A2AMessage:
    """A message between agents."""
    id: str
    from_agent: str
    to_agent: str
    content: str
    message_type: str  # "task", "response", "event", "heartbeat"
    timestamp: float
    metadata: dict = field(default_factory=dict)
    reply_to: Optional[str] = None

    @classmethod
    def create(
        cls,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: str = "task",
        metadata: Optional[dict] = None,
        reply_to: Optional[str] = None,
    ) -> "A2AMessage":
        return cls(
            id=str(uuid.uuid4()),
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=message_type,
            timestamp=time.time(),
            metadata=metadata or {},
            reply_to=reply_to,
        )

    def to_dict(self) -> dict:
        return asdict(self)


class A2ABus:
    """In-memory message bus for agent-to-agent communication.

    Pattern from aios-local: simple queue-based messaging.
    """

    def __init__(self, persistence_path: Optional[Path] = None):
        self.queues: dict[str, deque[A2AMessage]] = defaultdict(deque)
        self.handlers: dict[str, Callable[[A2AMessage], None]] = {}
        self.persistence_path = persistence_path
        self.message_history: list[A2AMessage] = []
        self.max_history = 1000

        # Load persisted messages if available
        if persistence_path and persistence_path.exists():
            self._load_history()

    def send(self, message: A2AMessage) -> None:
        """Send a message to an agent's queue."""
        self.queues[message.to_agent].append(message)
        self.message_history.append(message)

        # Trim history
        if len(self.message_history) > self.max_history:
            self.message_history = self.message_history[-self.max_history:]

        # Persist
        if self.persistence_path:
            self._save_history()

        # Trigger handler if registered
        if message.to_agent in self.handlers:
            try:
                self.handlers[message.to_agent](message)
            except Exception as e:
                print(f"[A2A] Handler error for {message.to_agent}: {e}")

    def receive(self, agent_name: str, timeout: Optional[float] = None) -> Optional[A2AMessage]:
        """Receive a message for an agent (blocking with optional timeout)."""
        start = time.time()
        while True:
            if self.queues[agent_name]:
                return self.queues[agent_name].popleft()

            if timeout is not None and time.time() - start > timeout:
                return None

            time.sleep(0.01)  # 10ms poll

    def receive_nowait(self, agent_name: str) -> Optional[A2AMessage]:
        """Receive a message without blocking."""
        if self.queues[agent_name]:
            return self.queues[agent_name].popleft()
        return None

    def register_handler(self, agent_name: str, handler: Callable[[A2AMessage], None]) -> None:
        """Register a callback for incoming messages."""
        self.handlers[agent_name] = handler

    def unregister_handler(self, agent_name: str) -> None:
        """Remove a message handler."""
        self.handlers.pop(agent_name, None)

    def status(self) -> dict:
        """Get queue status for all agents."""
        return {k: len(v) for k, v in self.queues.items()}

    def get_history(
        self,
        agent: Optional[str] = None,
        message_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[A2AMessage]:
        """Get message history with optional filtering."""
        filtered = self.message_history

        if agent:
            filtered = [m for m in filtered if m.to_agent == agent or m.from_agent == agent]

        if message_type:
            filtered = [m for m in filtered if m.message_type == message_type]

        return filtered[-limit:]

    def _save_history(self) -> None:
        """Persist message history to disk."""
        if not self.persistence_path:
            return

        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            data = [m.to_dict() for m in self.message_history[-100:]]  # Last 100 only
            self.persistence_path.write_text(json.dumps(data, indent=2), "utf-8")
        except Exception as e:
            print(f"[A2A] Failed to save history: {e}")

    def _load_history(self) -> None:
        """Load message history from disk."""
        try:
            data = json.loads(self.persistence_path.read_text("utf-8"))
            self.message_history = [A2AMessage(**m) for m in data]
        except Exception as e:
            print(f"[A2A] Failed to load history: {e}")


class A2AClient:
    """Client for connecting to external A2A endpoints."""

    def __init__(self, base_url: str, agent_name: str):
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name

    async def send_message(
        self,
        to_agent: str,
        content: str,
        message_type: str = "task",
        metadata: Optional[dict] = None,
    ) -> dict:
        """Send a message to an external agent."""
        import httpx

        message = A2AMessage.create(
            from_agent=self.agent_name,
            to_agent=to_agent,
            content=content,
            message_type=message_type,
            metadata=metadata,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/a2a/send",
                json=message.to_dict(),
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def receive_messages(self, agent_name: Optional[str] = None) -> list[dict]:
        """Poll for messages from external agents."""
        import httpx

        target = agent_name or self.agent_name
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/a2a/receive/{target}",
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()


# Global bus instance (singleton pattern)
_global_bus: Optional[A2ABus] = None


def get_a2a_bus(persistence_path: Optional[Path] = None) -> A2ABus:
    """Get or create the global A2A bus."""
    global _global_bus
    if _global_bus is None:
        _global_bus = A2ABus(persistence_path=persistence_path)
    return _global_bus
