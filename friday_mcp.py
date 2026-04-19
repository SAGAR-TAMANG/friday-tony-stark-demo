"""
MCP tool bridge for FRIDAY's REPL / voice modes.

Connects to the fastmcp server over SSE, lists tools, and wraps each as a
LiveKit `RawFunctionTool` so the LLM receives a proper function-calling
schema.  Actual dispatch is manual (via `dispatch()`), because the REPL
drives `llm.chat()` directly rather than going through `AgentSession`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp import Client
from livekit.agents.llm import function_tool

log = logging.getLogger("friday.mcp")


async def open_mcp(url: str, *, allow: list[str] | None = None):
    """
    Connect to the MCP server and return (client, tools, dispatch).

    - `client` is an already-entered fastmcp.Client (caller must `await client.close()`).
    - `tools` is a list of LiveKit RawFunctionTool objects, ready to pass to llm.chat().
    - `dispatch(name, args_json)` returns the tool result as a string.
    - `allow` optionally restricts tool exposure to the LLM.  Tools outside the
      allowlist are still dispatchable (if the LLM names them), just not offered.
      Default: expose everything.  WHY: prefilling 18 tool schemas on a 7B CPU
      model costs ~170s; trimming to 6 brings that to ~60s for a responsive demo.
    """
    client = Client(url)
    await client.__aenter__()  # keep open for the life of the REPL

    mcp_tools = await client.list_tools()
    log.info("connected to MCP: %d tools", len(mcp_tools))

    if allow:
        allow_set = set(allow)
        exposed = [t for t in mcp_tools if t.name in allow_set]
        missing = allow_set - {t.name for t in mcp_tools}
        if missing:
            log.warning("allowlist references unknown tools: %s", sorted(missing))
        log.info("exposing %d/%d tools to the LLM", len(exposed), len(mcp_tools))
    else:
        exposed = mcp_tools

    lk_tools = [_wrap(t) for t in exposed]

    async def dispatch(name: str, args_json: str) -> str:
        # OpenAI streams arguments as a JSON string — parse to kwargs.
        try:
            kwargs = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError as exc:
            return f"[tool-call error: bad JSON args: {exc}]"

        try:
            result = await client.call_tool(name, kwargs)
        except Exception as exc:  # surface to the model so it can retry
            return f"[tool '{name}' failed: {exc}]"

        return _format_result(result)

    return client, lk_tools, dispatch


def _wrap(mcp_tool: Any):
    """Convert one MCP Tool → LiveKit RawFunctionTool."""
    schema = {
        "name": mcp_tool.name,
        "description": (mcp_tool.description or "").strip() or mcp_tool.name,
        "parameters": mcp_tool.inputSchema or {"type": "object", "properties": {}},
    }

    # Wrapper body is never called — we dispatch manually in _chat_with_tools.
    # LiveKit's raw_schema path only needs the schema; the function is a stub.
    async def _stub(**_kwargs: Any) -> str:
        return "[dispatched manually]"

    _stub.__name__ = mcp_tool.name
    return function_tool(_stub, raw_schema=schema)


def _format_result(result: Any) -> str:
    """
    fastmcp.call_tool returns a CallToolResult with three payload channels:
      - structured_content: already-parsed JSON dict (cleanest for the LLM)
      - content: list of TextContent blocks (human-readable fallback)
      - data:   dynamic dataclass wrapper (looks pretty but has no model_dump)
    Prefer structured_content; fall back to concatenated text.
    """
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        # Many MCP tools return {"result": <actual>}; unwrap that one level
        # so the LLM sees the value directly instead of {"result": "..."}.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            structured = structured["result"]
        try:
            return json.dumps(structured, default=str)[:4000]
        except (TypeError, ValueError):
            pass

    content = getattr(result, "content", None)
    if content:
        parts = [text for block in content if (text := getattr(block, "text", None))]
        if parts:
            return "\n".join(parts)[:4000]

    return str(result)[:4000]
