# FRIDAY Conventions

Project-specific rules that apply on top of global code standards.

## Architecture invariants

- **Two processes, one tool surface.** `server.py` exposes tools over MCP (Streamable HTTP, :8000). `agent_friday.py` is the LiveKit voice loop and consumes that same MCP server. Never duplicate tools in the agent — register once via `friday/tools/*.py`.
- **Tools live in `friday/tools/<area>.py`**, each exporting `def register(mcp): ...`. `friday/tools/__init__.py` imports and calls them.
- **Core primitives live in `friday/core/`** (orchestrator, a2a, memory_manager, persistence, base_tool, result, skill_registry). Tools may import from core; core must not import from tools.
- **Config is centralized** in `friday/config.py`. New env var → add to both `.env.example` and `Config` class.

## Python style

- Max **30 lines/function**, **300 lines/file**. If you hit either, split.
- Type hints on every public function. Prefer `from __future__ import annotations`.
- F-strings, list comprehensions, walrus `:=` where it improves clarity.
- `async def` for anything that awaits IO. Don't mix sync and async inside one tool.
- Errors: never `except: pass`. Log with `logger.warning` or raise. Tools return `ToolResult`/`Result` on failure, not a bare exception.
- WHY comments only — the code says what, the comment says why.

## MCP tool authoring

1. Add decorated function with `@mcp.tool()` inside `register(mcp)`.
2. Docstring first line is what the LLM sees — write it for the LLM, not for humans.
3. Keyless fallbacks preferred. If a premium API is used, degrade gracefully when the key is missing.
4. Return strings or JSON-serializable dicts. No raw bytes, no custom classes.

## Security gates

- Shell exec honors `SHELL_EXEC_ENABLED` and `SHELL_BLOCKED_COMMANDS` from config.
- Code exec honors `CODE_EXEC_ENABLED`.
- File tools are sandboxed to `FRIDAY_FILE_ROOT` (defaults to `FRIDAY_HOME`).
- A2A server only binds when `A2A_ENABLED=true`.

## Git

- Commit per logical unit (per-file where sensible). Imperative messages.
- Small PRs — target ~118 lines. Squash merge.
- Never commit `.env`, token JSONs, or `~/.friday/` contents.
