# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Package manager: [`uv`](https://github.com/astral-sh/uv). Python ≥ 3.11.

```bash
uv sync                  # create .venv and install all deps from uv.lock
cp .env.example .env     # then fill in keys (see "Required env" below)
```

Run the two processes (both must be running at the same time):

```bash
uv run friday            # Terminal 1 — FastMCP server on http://127.0.0.1:8000/sse
uv run friday_voice      # Terminal 2 — LiveKit voice agent (dev mode, auto-injected)
```

- `friday` → `server:main` (declared in `pyproject.toml [project.scripts]`).
- `friday_voice` → `agent_friday:dev`, which injects `dev` into `sys.argv` if missing and forwards to LiveKit's `cli.run_app`. To run a different LiveKit subcommand, call `uv run agent_friday.py <subcommand>` directly (e.g. `console` for text-only).

There is no test suite, linter, or build step configured. `main.py` is an unused "hello" stub — not wired to any console script.

## Required env (.env)

Defaults assume Sarvam STT + Gemini LLM + OpenAI TTS, so these are all required to run the voice agent:

- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `SARVAM_API_KEY`
- `GOOGLE_API_KEY` (used directly in `agent_friday.py:_build_llm`)
- `OPENAI_API_KEY`

Optional / only needed if you flip provider switches: `GROQ_API_KEY`, `DEEPGRAM_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`. README mentions `SUPABASE_URL` / `SUPABASE_API_KEY` for a ticketing tool that does not exist in the code.

## Architecture

Two cooperating Python processes communicating over MCP/SSE:

```
Mic ─► STT (Sarvam Saaras v3) ─► LLM (Gemini 2.5 Flash) ◄──► MCP Server (FastMCP/SSE)
                                       │                          ├─ get_world_news
                                       ▼                          ├─ get_world_finance_news
                                  TTS (OpenAI nova)               ├─ open_world_monitor
                                       │                          ├─ open_finance_world_monitor
                                       ▼                          ├─ fetch_url
                                  LiveKit room ─► Speaker         └─ system / utils tools
```

**`server.py` — MCP server entry.** Builds `FastMCP(name=config.SERVER_NAME, …)`, calls `register_all_tools(mcp)`, `register_all_prompts(mcp)`, `register_all_resources(mcp)`, then `mcp.run(transport='sse')`. The three `register_all_*` functions live in `friday/{tools,prompts,resources}/__init__.py` and simply fan out to each submodule's `register(mcp)`.

**`agent_friday.py` — LiveKit voice agent entry.** Top of file holds provider switches (`STT_PROVIDER`, `LLM_PROVIDER`, `TTS_PROVIDER`) and the FRIDAY `SYSTEM_PROMPT`. `entrypoint(ctx)` builds STT/LLM/TTS via `_build_stt/_build_llm/_build_tts`, constructs `AgentSession` with `turn_detection` and `min_endpointing_delay` chosen by `_turn_detection()` / `_endpointing_delay()` (Sarvam → `"stt"` + 0.07s, Whisper → `"vad"` + 0.3s), then starts `FridayAgent`. The agent registers a single `mcp.MCPServerHTTP` pointing at `_mcp_server_url()` — currently hardcoded to `http://127.0.0.1:8000/sse`. WSL-gateway and Cloudflare tunnel URL paths are present but commented out.

**`FridayAgent.on_enter`** generates a greeting reply branched on UTC hour (22–04, 04–12, 12–17, 17–21). This overrides the "session start" greeting described in `SYSTEM_PROMPT`.

**Tools (`friday/tools/`)** — each module exposes `register(mcp)` and uses `@mcp.tool()`:
- `web.py`: async RSS aggregators (`get_world_news`, `get_world_finance_news`) that `httpx`-fetch hardcoded feed lists in parallel via `asyncio.gather`, parse XML with `ElementTree`, strip HTML from descriptions, return top 12 formatted as a "BRIEFING (LIVE)" string. Also `fetch_url`, `open_world_monitor`, `open_finance_world_monitor` (browser launchers via `webbrowser.open`), and `search_web` — a stub returning `[stub] Search results for: {query}`.
- `system.py`: `get_current_time`, `get_system_info`.
- `utils.py`: `format_json`, `word_count`.

**Persona contract.** `SYSTEM_PROMPT` in `agent_friday.py` forbids speaking tool/function names aloud and requires that every news brief silently call `open_world_monitor` (or the finance equivalent) immediately after, with the only voice line being "Let me open up the world monitor for you." Behavior changes to tool ordering or naming must keep this contract intact.

**Config surface is split.** `friday/config.py:Config` only reads `SERVER_NAME`, `DEBUG`, `OPENAI_API_KEY`, `SEARCH_API_KEY`. Everything else (LiveKit creds, `GOOGLE_API_KEY`, Sarvam, etc.) is consumed directly by `agent_friday.py` or by the LiveKit plugins via env. There is no central settings object.

## Adding a tool

1. Create or edit a module in `friday/tools/`.
2. Define `def register(mcp): ...` and decorate handlers with `@mcp.tool()`.
3. Import and call `register(mcp)` from `friday/tools/__init__.py:register_all_tools`.
4. If the LLM should invoke it, also describe trigger phrases and post-call behavior in `SYSTEM_PROMPT` (in `agent_friday.py`). The voice agent reads tools at MCP session start, so restart `uv run friday_voice` after changes.

The same pattern applies to prompts (`friday/prompts/`) and resources (`friday/resources/`).

## Known gaps / dead code

- `friday/tools/web.py:search_web` is a stub.
- README documents a Supabase ticketing tool — not implemented.
- `agent_friday.py` module docstring mentions RGB lighting, diagnostics, and network-scan tools — none of those are registered.
- `_get_windows_host_ip()` and the Cloudflare tunnel URL branch in `_mcp_server_url()` are dead. If running the server on Windows while the agent runs in WSL, re-enable the gateway branch and bind FastMCP to `0.0.0.0`.
- `main.py` is an unused leftover.

## Vault First, Vault Ask (SecBrain memory)

This project's persistent cross-session memory lives in SecBrain at:
`/Users/dhruvsmac/Desktop/SecBrain/projects/friday-tony-stark-demo/`

Inherit the global Vault First, Vault Ask rules from `~/.claude/CLAUDE.md`. For meaningful work:

1. Read `projects/friday-tony-stark-demo/index.md` first.
2. Then `overview.md`, latest `log.md` entries, and `status/recent-changes.md`.
3. Open relevant entity / concept / source notes (e.g. [[FRIDAY Persona]], [[Voice Agent Component]], [[MCP Server Component]], [[Provider Stack]], [[FastMCP SSE Transport]]).
4. Verify wiki claims against the actual code in this repo. Source notes are immutable inputs; the compiled wiki is the working knowledge.

**Vault writes.** Never auto-save. Before any vault write, ask: "Do you want me to save this thread/work into Obsidian?" Only write if explicitly approved or asked this turn. When approved, update: source/output → affected entities/concepts → backlinks → `index.md` → `log.md` → `status/recent-changes.md`. Maintain bidirectional `[[wikilinks]]`, aliases, and `See Also`. Never store API keys, LiveKit secrets, `.env` contents, or raw user data in the vault.



## Open threads worth picking up

In rough priority order:

1. **Voice input in the desktop app.** Currently text-only. Add a mic
   button that drives the same `Brain.send()` path via Whisper (already
   in the OpenAI client) or Sarvam STT (already a dep).
2. **Amplitude-reactive speaking ripple.** The orb has a `speaking`
   state with a high-frequency rim wobble, but it's faked. If we add
   real TTS playback, drive the wobble from the audio amplitude.
3. **Persist desktop chat into memory at session end.** The voice agent
   has no session memory yet either — both could call `save_memory`
   with a session summary on close.
4. **A real integration if the user authorizes it.** Jira and Slack are
   the highest-leverage ones from the spec, but only build with their
   credentials in hand.

---

## A note on this handoff

This file was written by a previous Claude session running on Claude
Code on the web. That session built everything described above and
handed the code over via zip. The web session and your local CLI
session don't share conversation history — only the working tree and
this file. Treat this CLAUDE.md as the entire briefing.
