"""FRIDAY Core — base classes and utilities from OpenJarvis + SUPER AGI patterns."""

from .a2a import A2ABus, A2AClient, A2AMessage, get_a2a_bus
from .base_tool import BaseTool, ToolRegistry, ToolResult
from .memory_manager import MemoryManager
from .orchestrator import AgentDefinition, AgentOrchestrator, AgentTask, DEFAULT_AGENTS
from .persistence import DatabaseManager, TelemetryEvent, ExecutionTrace
from .result import Result, SuccessResult, ErrorResult
from .skill_registry import SkillManifest, SkillRegistry, get_skill_registry

__all__ = [
    # Results
    "Result", "SuccessResult", "ErrorResult",
    # Tools
    "BaseTool", "ToolRegistry", "ToolResult",
    # Memory
    "MemoryManager",
    # Persistence
    "DatabaseManager", "TelemetryEvent", "ExecutionTrace",
    # A2A
    "A2ABus", "A2AClient", "A2AMessage", "get_a2a_bus",
    # Skills
    "SkillManifest", "SkillRegistry", "get_skill_registry",
    # Orchestration
    "AgentDefinition", "AgentOrchestrator", "AgentTask", "DEFAULT_AGENTS",
]
