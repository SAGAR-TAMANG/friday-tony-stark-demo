"""Shell execution tool — from OpenJarvis with safety constraints."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from friday.core.base_tool import BaseTool, ToolRegistry, ToolResult

# Security limits
_MAX_OUTPUT_BYTES = 102_400  # 100KB
_MAX_TIMEOUT = 300  # 5 minutes
_DEFAULT_TIMEOUT = 30
_BASE_ENV_KEYS = ("PATH", "HOME", "USER", "LANG", "TERM", "SYSTEMROOT", "COMPUTERNAME")


@ToolRegistry.register("shell_exec")
class ShellExecTool(BaseTool):
    """Execute shell commands with sanitised environment."""

    tool_id = "shell_exec"
    is_local = True

    def __init__(self, allowed_commands: list[str] | None = None) -> None:
        """Initialize with optional allowlist.

        Args:
            allowed_commands: List of allowed command prefixes. If None, all allowed.
        """
        self.allowed_commands = allowed_commands or []
        self.blocked_commands = {"rm -rf /", "rm -rf /*", ":(){ :|:& };:", "dd if=/dev/zero"}

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return stdout/stderr. "
            "Runs with a minimal environment for security. "
            "Timeout capped at 300s. Use for: git operations, file listing, "
            "package installation, system diagnostics."
        )

    def run(self, command: str = "", timeout: int = _DEFAULT_TIMEOUT, working_dir: str = "") -> ToolResult:
        """Execute shell command with safety constraints.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds (default 30, max 300)
            working_dir: Working directory for the command
        """
        if not command:
            return ToolResult(tool_name=self.name, success=False, error="No command provided")

        # Check blocked commands
        cmd_lower = command.lower().strip()
        for blocked in self.blocked_commands:
            if blocked in cmd_lower:
                return ToolResult(tool_name=self.name, success=False, error=f"Command blocked for security: {blocked}")

        # Validate timeout
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT
        timeout = max(1, min(timeout, _MAX_TIMEOUT))

        # Validate working directory
        cwd = None
        if working_dir:
            wd_path = Path(working_dir)
            if not wd_path.exists():
                return ToolResult(tool_name=self.name, success=False, error=f"Working directory does not exist: {working_dir}")
            if not wd_path.is_dir():
                return ToolResult(tool_name=self.name, success=False, error=f"Path is not a directory: {working_dir}")
            cwd = str(wd_path.resolve())

        # Build sanitized environment
        env: dict[str, str] = {}
        for key in _BASE_ENV_KEYS:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val

        # Execute
        t0 = __import__("time").time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            elapsed_ms = (__import__("time").time() - t0) * 1000

            # Truncate output
            stdout = result.stdout
            stderr = result.stderr
            if len(stdout) > _MAX_OUTPUT_BYTES:
                stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... (stdout truncated)"
            if len(stderr) > _MAX_OUTPUT_BYTES:
                stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... (stderr truncated)"

            # Format output
            sections: list[str] = []
            if stdout:
                sections.append(f"=== STDOUT ===\n{stdout}")
            if stderr:
                sections.append(f"=== STDERR ===\n{stderr}")
            content = "\n\n".join(sections) if sections else "(no output)"

            return ToolResult(
                tool_name=self.name,
                success=result.returncode == 0,
                content=content,
                elapsed_ms=elapsed_ms,
                metadata={"returncode": result.returncode, "cwd": cwd or os.getcwd()},
            )

        except subprocess.TimeoutExpired:
            elapsed_ms = (__import__("time").time() - t0) * 1000
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Command timed out after {timeout}s",
                elapsed_ms=elapsed_ms,
            )
        except PermissionError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Permission denied: {exc}",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Execution error: {exc}",
            )


def register(mcp):
    """Register shell tools with MCP server."""
    tool = ShellExecTool()

    @mcp.tool()
    async def shell_exec(command: str, timeout: int = 30, working_dir: str = "") -> str:
        """Execute a shell command safely. Returns stdout/stderr.

        Args:
            command: Shell command to execute (e.g., "ls -la", "git status")
            timeout: Maximum execution time in seconds (default: 30, max: 300)
            working_dir: Directory to run command in (default: current directory)
        """
        result = tool.run(command=command, timeout=timeout, working_dir=working_dir)
        return result.formatted
