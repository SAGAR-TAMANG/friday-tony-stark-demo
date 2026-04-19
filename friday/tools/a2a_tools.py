"""A2A Protocol tools — Agent-to-Agent communication via MCP."""

from __future__ import annotations

import json
import os
from pathlib import Path

from friday.core.a2a import A2AMessage, get_a2a_bus

# Initialize A2A bus
_a2a_bus = get_a2a_bus(
    persistence_path=Path(os.getenv("FRIDAY_HOME", Path.home() / ".friday")) / "a2a_history.json"
)


def register(mcp):
    """Register A2A protocol tools with MCP server."""

    @mcp.tool()
    async def a2a_send_message(
        to_agent: str,
        content: str,
        message_type: str = "task",
        from_agent: str = "friday",
        metadata: str = "",
    ) -> str:
        """Send a message to another agent via A2A protocol.

        Args:
            to_agent: Name of the target agent
            content: Message content
            message_type: Type of message ('task', 'response', 'event', 'heartbeat')
            from_agent: Sender name (default: 'friday')
            metadata: Optional JSON metadata string
        """
        try:
            meta = json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            return "[A2A ERROR] Invalid metadata JSON"

        message = A2AMessage.create(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=message_type,
            metadata=meta,
        )

        _a2a_bus.send(message)
        return f"[A2A] Message sent to {to_agent} (ID: {message.id[:8]})"

    @mcp.tool()
    async def a2a_receive_message(agent_name: str, timeout: float = 0.0) -> str:
        """Receive a message for an agent (non-blocking by default).

        Args:
            agent_name: Name of the agent to receive for
            timeout: Seconds to wait (0 = non-blocking)
        """
        message = _a2a_bus.receive(agent_name, timeout=timeout if timeout > 0 else None)

        if not message:
            return f"[A2A] No messages for {agent_name}"

        lines = [
            f"[A2A] Message from {message.from_agent}:",
            f"  Type: {message.message_type}",
            f"  Content: {message.content[:200]}{'...' if len(message.content) > 200 else ''}",
            f"  Timestamp: {message.timestamp}",
        ]

        if message.metadata:
            lines.append(f"  Metadata: {json.dumps(message.metadata)}")

        return "\n".join(lines)

    @mcp.tool()
    async def a2a_check_inbox(agent_name: str) -> str:
        """Check message count for an agent without consuming messages.

        Args:
            agent_name: Name of the agent to check
        """
        status = _a2a_bus.status()
        count = status.get(agent_name, 0)

        if count == 0:
            return f"[A2A] Inbox empty for {agent_name}"
        return f"[A2A] {agent_name} has {count} message(s) waiting"

    @mcp.tool()
    async def a2a_get_history(
        agent: str = "",
        message_type: str = "",
        limit: int = 50,
    ) -> str:
        """Get message history.

        Args:
            agent: Filter by agent name (optional)
            message_type: Filter by message type (optional)
            limit: Maximum messages to return (default: 50)
        """
        history = _a2a_bus.get_history(
            agent=agent if agent else None,
            message_type=message_type if message_type else None,
            limit=limit,
        )

        if not history:
            return "[A2A] No message history"

        lines = [f"[A2A] Message history ({len(history)} messages):\n"]
        for msg in history:
            direction = "→" if msg.from_agent == "friday" else "←"
            lines.append(f"[{msg.id[:8]}] {msg.from_agent} {direction} {msg.to_agent}")
            lines.append(f"   Type: {msg.message_type} | {msg.content[:60]}...")

        return "\n".join(lines)

    @mcp.tool()
    async def a2a_broadcast(content: str, from_agent: str = "friday") -> str:
        """Broadcast a message to all known agents.

        Args:
            content: Message content to broadcast
            from_agent: Sender name
        """
        # Get all agents from status
        status = _a2a_bus.status()
        sent_count = 0

        for agent_name in status.keys():
            if agent_name != from_agent:
                message = A2AMessage.create(
                    from_agent=from_agent,
                    to_agent=agent_name,
                    content=content,
                    message_type="event",
                    metadata={"broadcast": True},
                )
                _a2a_bus.send(message)
                sent_count += 1

        return f"[A2A] Broadcast sent to {sent_count} agent(s)"
