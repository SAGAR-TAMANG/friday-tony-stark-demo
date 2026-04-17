"""Git operations tool — from OpenJarvis git_tool.py."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from friday.core.base_tool import BaseTool, ToolRegistry, ToolResult


@ToolRegistry.register("git_status")
class GitStatusTool(BaseTool):
    """Get git repository status."""

    tool_id = "git_status"
    is_local = True

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Get git repository status: current branch, modified files, staged changes, and untracked files."

    def run(self, repo_path: str = "") -> ToolResult:
        """Get git status for a repository."""
        path = Path(repo_path).resolve() if repo_path else self.repo_path

        try:
            import subprocess

            # Check if git repo
            git_dir = path / ".git"
            if not git_dir.exists():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Not a git repository: {path}"
                )

            # Get branch
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(path),
                capture_output=True,
                text=True
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

            # Get status
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(path),
                capture_output=True,
                text=True
            )

            lines = [f"On branch: {branch}", ""]

            if status_result.stdout:
                lines.append("Changes:")
                for line in status_result.stdout.strip().split("\n"):
                    if line:
                        status = line[:2]
                        file = line[3:]
                        lines.append(f"  [{status}] {file}")
            else:
                lines.append("Working tree clean")

            return ToolResult(
                tool_name=self.name,
                success=True,
                content="\n".join(lines),
                metadata={"branch": branch, "repo": str(path)}
            )

        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc))


@ToolRegistry.register("git_diff")
class GitDiffTool(BaseTool):
    """Show git diff for changes."""

    tool_id = "git_diff"
    is_local = True

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Show diff of unstaged changes in a git repository."

    def run(self, repo_path: str = "", staged: bool = False) -> ToolResult:
        """Get git diff."""
        path = Path(repo_path).resolve() if repo_path else self.repo_path

        try:
            import subprocess

            cmd = ["git", "diff", "--cached"] if staged else ["git", "diff"]
            result = subprocess.run(
                cmd,
                cwd=str(path),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=result.stderr or "Failed to get diff"
                )

            diff = result.stdout.strip()
            if not diff:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content="No changes to show" if not staged else "No staged changes"
                )

            # Truncate if too long
            if len(diff) > 10000:
                diff = diff[:10000] + "\n... (truncated)"

            return ToolResult(
                tool_name=self.name,
                success=True,
                content=diff,
                metadata={"staged": staged, "repo": str(path)}
            )

        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc))


@ToolRegistry.register("git_log")
class GitLogTool(BaseTool):
    """Show recent git commits."""

    tool_id = "git_log"
    is_local = True

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show recent git commit history with messages and hashes."

    def run(self, repo_path: str = "", n: int = 10) -> ToolResult:
        """Get git log."""
        path = Path(repo_path).resolve() if repo_path else self.repo_path

        try:
            import subprocess

            result = subprocess.run(
                ["git", "log", f"-{n}", "--oneline", "--format=%h|%an|%ar|%s"],
                cwd=str(path),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=result.stderr or "Failed to get log"
                )

            lines = [f"Last {n} commits:\n"]
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        lines.append(f"  {parts[0]} — {parts[3][:60]}")
                        lines.append(f"     by {parts[1]}, {parts[2]}")

            return ToolResult(
                tool_name=self.name,
                success=True,
                content="\n".join(lines),
                metadata={"repo": str(path), "count": n}
            )

        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc))


def register(mcp):
    """Register git tools with MCP server."""
    status = GitStatusTool()
    diff = GitDiffTool()
    log = GitLogTool()

    @mcp.tool()
    async def git_status(repo_path: str = ".") -> str:
        """Get git repository status: branch, modified files, staged changes.

        Args:
            repo_path: Path to git repository (default: current directory)
        """
        result = status.run(repo_path=repo_path)
        return result.formatted

    @mcp.tool()
    async def git_diff(repo_path: str = ".", staged: bool = False) -> str:
        """Show diff of changes in a git repository.

        Args:
            repo_path: Path to git repository (default: current directory)
            staged: Show staged changes instead of unstaged
        """
        result = diff.run(repo_path=repo_path, staged=staged)
        return result.formatted

    @mcp.tool()
    async def git_log(repo_path: str = ".", n: int = 10) -> str:
        """Show recent git commits.

        Args:
            repo_path: Path to git repository (default: current directory)
            n: Number of commits to show (default: 10)
        """
        result = log.run(repo_path=repo_path, n=n)
        return result.formatted
