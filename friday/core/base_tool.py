"""Base tool class — OpenJarvis registry pattern + SUPER AGI result pattern."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .result import Result


@dataclass
class ToolResult(Result):
    """Tool execution result with content and metadata."""
    tool_name: str = ""
    content: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def formatted(self) -> str:
        if self.error:
            return f"[{self.tool_name} FAILED] {self.error}"
        return f"[{self.tool_name}] {self.content}" if self.content else f"[{self.tool_name} OK]"


class BaseTool(ABC):
    """Abstract base for all FRIDAY tools.

    Pattern from SUPER AGI + OpenJarvis:
    - .run() executes the tool
    - .name returns tool identifier
    - .description returns tool description for LLM
    - .formatted returns human-readable output
    """

    tool_id: str = ""
    is_local: bool = True

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name/identifier."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM."""
        pass

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool."""
        pass

    def _timed_run(self, **kwargs: Any) -> ToolResult:
        """Wrap execution with timing."""
        t0 = time.time()
        try:
            result = self.run(**kwargs)
            result.elapsed_ms = (time.time() - t0) * 1000
            return result
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                elapsed_ms=(time.time() - t0) * 1000
            )


class ToolRegistry:
    """Registry pattern from OpenJarvis — decorator-based tool registration."""

    _tools: dict[str, type[BaseTool]] = {}

    @classmethod
    def register(cls, tool_id: str) -> Callable[[type[BaseTool]], type[BaseTool]]:
        """Decorator to register a tool class."""
        def decorator(tool_class: type[BaseTool]) -> type[BaseTool]:
            tool_class.tool_id = tool_id
            cls._tools[tool_id] = tool_class
            return tool_class
        return decorator

    @classmethod
    def get(cls, tool_id: str) -> Optional[type[BaseTool]]:
        """Get a registered tool class by ID."""
        return cls._tools.get(tool_id)

    @classmethod
    def list_tools(cls) -> list[str]:
        """List all registered tool IDs."""
        return list(cls._tools.keys())

    @classmethod
    def create_instance(cls, tool_id: str, **kwargs: Any) -> Optional[BaseTool]:
        """Create a tool instance by ID."""
        tool_class = cls.get(tool_id)
        if tool_class:
            return tool_class(**kwargs)
        return None
