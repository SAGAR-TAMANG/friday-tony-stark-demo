# CLAUDE.md — FRIDAY

Guidance for Claude Code when working in this repo.

## Architecture at a glance

Two cooperating processes, one shared tool surface:

- **`uv run friday`** → `server.py` starts a FastMCP server on `:8000/mcp` (Streamable HTTP).
- **`uv run friday_voice`** → `agent_friday.py` runs the LiveKit voice loop. Modes: `pipeline` (STT→LLM→TTS), `realtime_gemini`, `realtime_openai`.

Both share tools declared in `friday/tools/*.py`. Core primitives (orchestrator, A2A bus, memory, persistence, skill registry) live in `friday/core/`. Config is centralized in `friday/config.py`; every env var has a keyless fallback where possible.

## Entry points

```bash
uv sync
uv run friday          # MCP server (must start first)
uv run friday_voice    # Voice agent (separate terminal)
```

## Adding a tool

Use the `friday-tool-author` skill (`.claude/skills/friday-tool-author/SKILL.md`) or:

1. Create/edit `friday/tools/<area>.py` with a `register(mcp)` function and `@mcp.tool()`-decorated callables.
2. If the file is new, import and call `register(mcp)` in `friday/tools/__init__.py`.
3. `python -m py_compile friday/tools/<area>.py` + restart the server.

## Adding a subagent

Drop a new file into `.claude/agents/<name>.md` with a frontmatter block (`name`, `description`, optional `tools`). Keep prompts under 50 lines. See `mcp-builder.md` or `code-reviewer.md` for reference.

## Conventions

See `.claude/rules/friday-conventions.md`. Key points: max 30 lines/function, 300 lines/file, type hints everywhere, no reverse imports (tools may import core; core may not import tools), every new env var goes into both `.env.example` and `Config`.

## Security gates

- `SHELL_EXEC_ENABLED` + `SHELL_BLOCKED_COMMANDS` — shell tool.
- `CODE_EXEC_ENABLED` — python runner.
- `FRIDAY_FILE_ROOT` — file tools sandbox (defaults to `FRIDAY_HOME`).
- `A2A_ENABLED` + `A2A_PORT` — agent-to-agent server.

## References

- `ARCHITECTURE.md` — deep layer-by-layer overview.
- `INTEGRATION.md` — notes on what was ported from SUPER AGI, OpenJarvis, agency-agents, CCBP, aios-local, Desktop/jarvis.
- `.env.example` — every configurable knob.
