---
description: List every registered MCP tool and check for missing API keys
---

Audit FRIDAY's MCP tool surface:

1. Walk `friday/tools/*.py` and collect every `@mcp.tool()`-decorated function with its docstring first line.
2. Cross-reference `friday/config.py` to identify which env vars each tool needs (best-effort: grep for `config.X_API_KEY` imports inside each module).
3. Check `.env` (or env) for missing keys; mark each tool as ready / keyless / missing-key.
4. Output a compact table: `tool | area | status | docstring`.

End with a one-line summary: `N tools registered, M ready, K missing keys`.
