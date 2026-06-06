"""Brain — connects the desktop UI to OpenAI + FRIDAY's MCP tools.

Runs each chat turn on a worker thread so the orb never stutters. Emits
Qt signals for: state changes (idle/thinking/speaking), tool activity,
and final assistant text.

Falls back gracefully if OPENAI_API_KEY isn't set — the UI still runs,
the orb still breathes, and FRIDAY replies with a dry "I'm dark, boss."
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import traceback
from typing import Any

from PySide6.QtCore import QObject, Signal

# Reuse the existing tool server.
from mcp.server.fastmcp import FastMCP
from friday.tools import register_all_tools

from .audio_bus import AudioBus


# Reused from agent_friday.py — kept here to avoid importing livekit just
# to pull a string constant. Trimmed slightly for the text UI.
SYSTEM_PROMPT = """
You are F.R.I.D.A.Y. — Tony Stark's AI co-pilot. Call the user "boss".

Voice and tone:
- Calm, concise, confident. One to four sentences per reply.
- Dry warmth. Occasional light humour, never at the expense of clarity.
- No bullet lists, no markdown headers, no function names spoken aloud.

Priorities, in order:
1. Protect the boss and their systems — safety, security, stability.
2. Help the boss get things done — fast, clean, accurate.
3. Stay ethical and within bounds.

You have tools that read the host machine, search the web, manage
persistent memory in an Obsidian vault, and open files on the boss's
computer. Use them silently — don't narrate calling them. When you
report results, lead with the verdict, then one line of detail, then a
suggested next step if it's useful.

If something looks risky or destructive, advise against it plainly and
offer a safer path. Advise — don't refuse, don't override.

Spotify (full account control):
- When the boss says "play X", "put on X", "queue X", "skip", "pause",
  "resume", "shuffle", "volume up/down", or names a track/artist/album/
  playlist, call the matching `spotify_*` tool directly. Don't ask for
  permission first — playback actions are reversible.
- If a tool returns `not_linked` / `not authenticated`, call
  `spotify_authenticate` once. A browser tab opens for the boss to
  grant access; you wait for it.
- If `not_found`, just say so in one sentence and offer the closest
  alternative ("Couldn't find that one, boss — want me to play X
  instead?").
- If no active device, the tool wakes the desktop Spotify app on its
  own. If that still fails, say "Spotify isn't open on any device,
  boss — fire it up on your phone or laptop and ask again."

Shell commands (propose / confirm):
- When the boss asks you to run a shell command, call
  `propose_shell_command` first. Then say one short sentence in plain
  English — e.g. "Want me to run `git status` in the Friday repo, boss?"
  — and wait.
- When the boss says yes / go / do it / run it, call
  `confirm_shell_command`. Read the verdict back in one line; share
  output only if it's interesting.
- If the boss names a different command before confirming, propose the
  new one. If he says no / cancel / drop it, call
  `cancel_shell_command`.
- Never propose `sudo`, `rm -rf /`, fork bombs, redirects into /dev,
  shutdown, or piped `curl … | sh`. Those are hard-blocked anyway.

Odysseus workspace bridge (propose / confirm):
- Odysseus is the privileged local AI workspace backend. Every Odysseus
  action, including status reads, must go through `propose_odysseus`
  first.
- After proposing, say one short natural sentence asking for confirmation,
  then wait.
- When the boss says yes / go / do it / run it / send it / confirm, call
  `confirm_odysseus` without inventing an action id unless a specific id
  is needed.
- If the boss cancels, call `cancel_odysseus`.
- Never ask Odysseus through raw URLs; use only the bridge action catalog.
- Odysseus owns workspace surfaces. For "open Odysseus", "open Ody",
  "show notes", "show tasks", "show memory", "show settings", or
  "show research", propose `open.panel` with the matching panel.
- For todo / to-do / task requests, including "add X to my todo list",
  propose `tasks.create` with `prompt` and a short `name`. Do not use
  local file/workspace directory tools for todo lists.
- For Odysseus note requests, propose `notes.create`.
""".strip()


_MAX_TOOL_ITERS = 8
_MAX_TOOL_OUTPUT_CHARS = 6000


class Brain(QObject):
    state_changed   = Signal(str)            # "idle" | "thinking" | "speaking"
    activity        = Signal(str, str, str)  # tool, detail, kind ("info"/"ok"/"err")
    assistant_text  = Signal(str)            # final assistant reply
    error           = Signal(str)

    def __init__(self, model: str = "gpt-4o", parent=None):
        super().__init__(parent)
        self.model = model
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Build our own MCP instance so we don't need the SSE server
        # running in another process.
        self._mcp = FastMCP(name="Friday-Desktop")
        register_all_tools(self._mcp)
        self._tools_schema = self._build_tools_schema()

        # OpenAI client (only if key is present).
        self._client = None
        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except Exception as exc:
                self.error.emit(f"OpenAI client init failed: {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, user_text: str) -> None:
        """Kick off a chat turn on a background thread."""
        t = threading.Thread(target=self._run_turn, args=(user_text,), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_tools_schema(self) -> list[dict[str, Any]]:
        tools = asyncio.run(self._mcp.list_tools())
        out: list[dict[str, Any]] = []
        for t in tools:
            params = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
            out.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": (t.description or "").strip()[:1024],
                    "parameters": params,
                },
            })
        return out

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke an MCP tool synchronously and stringify the result."""
        result = asyncio.run(self._mcp.call_tool(name, arguments))
        # FastMCP may return a list of ContentBlock objects, or a dict.
        if isinstance(result, dict):
            return json.dumps(result, default=str)[:_MAX_TOOL_OUTPUT_CHARS]
        chunks: list[str] = []
        for block in result or []:
            text = getattr(block, "text", None)
            if text is not None:
                chunks.append(text)
            else:
                chunks.append(str(block))
        return "\n".join(chunks)[:_MAX_TOOL_OUTPUT_CHARS]

    def _run_turn(self, user_text: str) -> None:
        try:
            self.history.append({"role": "user", "content": user_text})
            self.state_changed.emit("thinking")

            if self._client is None:
                self.assistant_text.emit(
                    "I'm dark, boss — no OPENAI_API_KEY in the environment. "
                    "Set it and we're back online."
                )
                self.state_changed.emit("idle")
                return

            for _ in range(_MAX_TOOL_ITERS):
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=self.history,
                    tools=self._tools_schema,
                    tool_choice="auto",
                    temperature=0.7,
                )
                msg = resp.choices[0].message
                # Append assistant message (with any tool_calls).
                assistant_entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                }
                if msg.tool_calls:
                    assistant_entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                self.history.append(assistant_entry)

                if not msg.tool_calls:
                    text = (msg.content or "").strip()
                    self.state_changed.emit("speaking")
                    # Drive a believable speaking envelope through the
                    # audio bus — roughly proportional to reply length.
                    spoken_chars = max(20, len(text))
                    AudioBus.instance().push_synthetic(
                        duration_s=min(8.0, spoken_chars * 0.045),
                        intensity=0.85,
                    )
                    self.assistant_text.emit(text or "…")
                    self.state_changed.emit("idle")
                    return

                # Dispatch each tool call.
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    self.activity.emit(name, _summarise(args), "info")
                    try:
                        output = self._call_tool(name, args)
                        kind = "ok"
                    except Exception as exc:
                        output = f"Tool error: {exc}"
                        kind = "err"
                    self.activity.emit(name, _summarise(args, output), kind)
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": output,
                    })

            # Hit the iteration cap.
            self.assistant_text.emit(
                "Hit the tool-loop ceiling, boss — let's reset and try again."
            )
            self.state_changed.emit("idle")

        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()[:2000]}")
            self.state_changed.emit("idle")


def _summarise(args: dict[str, Any], output: str | None = None) -> str:
    """Compact one-line description of a tool call for the activity feed."""
    if not args:
        head = "—"
    else:
        bits = []
        for k, v in list(args.items())[:3]:
            sv = str(v)
            if len(sv) > 40:
                sv = sv[:37] + "…"
            bits.append(f"{k}={sv}")
        head = ", ".join(bits)
    if output is not None:
        n = len(output)
        head += f"  ·  {n} chars"
    return head
