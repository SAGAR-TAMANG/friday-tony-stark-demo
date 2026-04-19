---
name: friday-tool-author
description: Add a new MCP tool to FRIDAY in three steps. Use this skill whenever the user says "add a tool" or "expose X as a tool" for the FRIDAY voice agent.
---

# Add a tool to FRIDAY

## 1. Pick or create a file

Tools live in `friday/tools/<area>.py`. Existing areas: `web`, `news`, `finance`, `weather`, `notify`, `calendar`, `mail`, `memory`, `system`, `utils`, `shell`, `browser`, `git`, `code_runner`. If your tool fits an area, edit that file. Otherwise create `friday/tools/<new_area>.py`.

## 2. Write the tool

```python
# friday/tools/<area>.py
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def my_tool(arg: str) -> str:
        """One-line description the LLM will see.

        Longer explanation for humans.
        """
        # Keep under 30 lines. Graceful fallback when keys missing.
        return f"result for {arg}"
```

Rules:
- First line of docstring is LLM-visible. Write it for the LLM.
- Return str or JSON-serializable dict only.
- If you use an env-gated API key, read it from `friday.config.config.X_API_KEY`.
- Degrade silently when keys are absent — don't raise.

## 3. Register it

If you created a new file, add one line in `friday/tools/__init__.py`:

```python
from . import <new_area>
...
<new_area>.register(mcp)
```

## 4. Verify

```bash
python -m py_compile friday/tools/<area>.py
uv run friday  # should list the new tool in the startup log
```

That's it. No voice-agent changes needed — the agent discovers tools via MCP at session start.
