"""Code execution tool — SUPER AGI pattern, sandboxed subprocess."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from friday.core.base_tool import BaseTool, ToolRegistry, ToolResult


@dataclass
class CodeResult:
    """Result of code execution."""
    code: str
    stdout: str
    stderr: str
    return_value: Any
    elapsed_ms: float
    success: bool
    error: Optional[str] = None

    @property
    def formatted(self) -> str:
        parts = []
        if self.stdout:
            parts.append(f"[stdout]\n{self.stdout.strip()}")
        if self.stderr:
            parts.append(f"[stderr]\n{self.stderr.strip()}")
        if self.return_value is not None:
            parts.append(f"[return]\n{self.return_value}")
        if self.error:
            parts.append(f"[error]\n{self.error}")
        if not parts:
            parts.append("[No output]")
        return "\n\n".join(parts)


# Blocked builtins for security
_BLOCKED_BUILTINS = frozenset({
    "open", "exec", "eval", "compile", "__import__",
    "input", "breakpoint", "exit", "quit",
})

_WRAPPER_TEMPLATE = textwrap.dedent("""
import sys, json, traceback, io

_output_capture = io.StringIO()
sys.stdout = _output_capture

_return_value = None
_error = None

try:
{code}
except Exception as _exc:
    _error = traceback.format_exc()
finally:
    sys.stdout = sys.__stdout__

_result = {
    "stdout": _output_capture.getvalue(),
    "return_value": repr(_return_value) if _return_value is not None else None,
    "error": _error,
}
print(json.dumps(_result))
""")


@ToolRegistry.register("run_code")
class CodeRunnerTool(BaseTool):
    """Execute Python code in a sandboxed subprocess."""

    tool_id = "run_code"
    is_local = True

    def __init__(self, timeout: int = 30, max_output_chars: int = 10000) -> None:
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a sandboxed subprocess. "
            "Returns stdout, stderr, and return value. "
            "Use for: calculations, data transformation, algorithmic tasks. "
            f"Timeout: {self.timeout}s."
        )

    def run(self, code: str = "", language: str = "python") -> ToolResult:
        """Execute code and return result."""
        if not code:
            return ToolResult(tool_name=self.name, success=False, error="No code provided")

        if language.lower() != "python":
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Language '{language}' not supported. Only Python available."
            )

        # Syntax check
        syntax_error = self._check_syntax(code)
        if syntax_error:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"SyntaxError: {syntax_error}"
            )

        return self._run_subprocess(code)

    def _check_syntax(self, code: str) -> Optional[str]:
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return str(e)

    def _run_subprocess(self, code: str) -> ToolResult:
        indented = textwrap.indent(code, "    ")
        wrapped = _WRAPPER_TEMPLATE.format(code=indented)

        t0 = __import__("time").time()
        tmp_path = ""

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(wrapped)
                tmp_path = f.name

            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            elapsed_ms = (__import__("time").time() - t0) * 1000

            raw_out = proc.stdout.strip()
            raw_err = proc.stderr.strip()

            # Parse JSON result
            result_data: dict = {}
            if raw_out:
                try:
                    last_line = raw_out.split("\n")[-1]
                    result_data = json.loads(last_line)
                    display_stdout = "\n".join(raw_out.split("\n")[:-1])
                except json.JSONDecodeError:
                    display_stdout = raw_out
            else:
                display_stdout = ""

            stdout = self._truncate(result_data.get("stdout", display_stdout))
            stderr = self._truncate(raw_err)
            error = result_data.get("error")
            return_value = result_data.get("return_value")

            content_parts = []
            if stdout:
                content_parts.append(f"=== STDOUT ===\n{stdout}")
            if stderr:
                content_parts.append(f"=== STDERR ===\n{stderr}")
            if return_value:
                content_parts.append(f"=== RETURN ===\n{return_value}")

            content = "\n\n".join(content_parts) if content_parts else "(no output)"

            return ToolResult(
                tool_name=self.name,
                success=error is None and proc.returncode == 0,
                content=content,
                elapsed_ms=elapsed_ms,
                metadata={"returncode": proc.returncode}
            )

        except subprocess.TimeoutExpired:
            elapsed_ms = (__import__("time").time() - t0) * 1000
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Execution timed out after {self.timeout}s",
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
            )
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _truncate(self, text: str) -> str:
        if len(text) > self.max_output_chars:
            return text[:self.max_output_chars] + "\n... [truncated]"
        return text


def register(mcp):
    """Register code runner with MCP server."""
    runner = CodeRunnerTool()

    @mcp.tool()
    async def run_code(code: str, language: str = "python") -> str:
        """Execute Python code safely in a sandboxed subprocess.

        Args:
            code: Python code to execute
            language: Programming language (currently only 'python' supported)

        Example:
            code="x = sum(range(100))\nprint(f'Sum: {x}')"
        """
        result = runner.run(code=code, language=language)
        return result.formatted
