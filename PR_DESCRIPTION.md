# FRIDAY — Tool Calling, Voice I/O, and Streaming TTS

End-to-end upgrade of the FRIDAY voice agent: the model now calls MCP tools, speaks over Windows SAPI, accepts mic input via Whisper STT, and — new — streams TTS sentence-by-sentence so the user hears the first reply ~3-5s after asking instead of waiting 15-60s.

## What's new

### Tool calling (`145c66f`, `82fb15d`)
- `friday_mcp.py` — MCP tool bridge that discovers tools from the running fastmcp server, filters by allowlist, and exposes them as LiveKit `RawFunctionTool` objects.
- `_chat_with_tools` in `agent_friday.py` — drives a tool-calling loop: streams text + tool-call deltas, dispatches tool calls through the MCP client, appends `FunctionCall`/`FunctionCallOutput` items to the chat context, re-invokes `llm.chat()`. Capped at 4 iterations.
- `FRIDAY_TOOLS` env var — CSV allowlist (default: 6 demo-critical tools to keep prefill ~60s on CPU). `FRIDAY_TOOLS=*` exposes all 18.
- Tool result formatting via `structured_content` with single-key `"result"` envelope unwrap — clean JSON, no ugly `Output(result=...)` dataclass repr.

### Text REPL mode (`5a227f8`, `6b7e6a3`)
- New `repl` subcommand bypasses LiveKit's console loop for pure text Ollama chat. Instant greeting, no mic/speaker init.
- Fixed Ollama timeout storms — 600s httpx read timeout + `APIConnectOptions(timeout=600.0)` — 7B models on CPU need it.

### Voice mode (`1cab2a3`)
- New `voice` subcommand — text-in, voice-out via a persistent Windows SAPI PowerShell daemon (amortized ~5s .NET JIT, then each utterance is one stdin line).
- Zero cloud keys required for audio.

### Full voice mode (`c1b5555`, `85b5058`, `dff3edf`)
- New `fullvoice` subcommand — mic → STT → LLM → TTS → speaker.
- `friday_stt.py` — faster-whisper `tiny.en` (int8 CPU, ~75MB), cached across turns. Two-Enter PTT gate. Silence/noise early-exit avoids feeding empty audio to Whisper.

### Prewarm & tool-call reliability (`c6404f7`)
- `_prewarm_llm` — primes Ollama's KV prefix cache with system prompt + tool schemas so the first real turn reuses ~2000-2500 tokens of prefill. Drains the stream to completion (early break caused cache-commit issues on Ollama's side).
- Ran in parallel with TTS greeting in voice mode, serial in REPL.
- Default model bumped to `qwen2.5:7b-instruct` — `llama3.2:1b` emits tool calls as free text (broken on Ollama's OpenAI-compat layer).
- Documented `get_current_time` in `SYSTEM_PROMPT` + added catch-all behavioral rule: "For ANY question requiring live data, call the tool. Never answer from training memory."

### Streaming TTS (`cb0db0d`)
- New: sentence-by-sentence speech dispatch while generation continues.
- Producer/consumer pattern — `on_text` callback pushes tokens into an `asyncio.Queue`; background `_speak_streaming` task drains it, buffers until sentence boundary (`.!?` + whitespace), sends each sentence to the SAPI daemon.
- Both Ollama HTTP stream and SAPI subprocess are async I/O — they genuinely interleave at the event loop.
- Tool-call markers (`[tool: …]`) filtered from TTS queue — display-only.

## Usage

```bash
# Start MCP server (one-time)
uv run python server.py

# Pick your mode
uv run python agent_friday.py repl        # text in, text out
uv run python agent_friday.py voice       # text in, voice out
uv run python agent_friday.py fullvoice   # mic in, voice out

# Optional: expose all 18 tools (slower prefill)
FRIDAY_TOOLS=* uv run python agent_friday.py voice
```

## Testing notes

- Requires Ollama running with `qwen2.5:7b-instruct` (or set `OLLAMA_MODEL` to another tool-capable model — `qwen2.5-coder:7b`, `llama3.1:latest` also work).
- First turn on cold cache: ~60s. Subsequent turns: ~3-8s to first audible word.
- On Windows with R:\models Ollama config, mount R: before launching or Ollama will fail with `mkdir R:\models: The system cannot find the path specified`.

## Commits

```
cb0db0d feat(voice): stream TTS sentence-by-sentence as LLM generates
f469466 chore: update uv.lock for faster-whisper/sounddevice/numpy deps
c6404f7 fix(tool-calling): default qwen2.5:7b, document get_current_time, enforce live-data rule
dff3edf add STT deps for fullvoice mode
85b5058 add fullvoice subcommand — mic -> STT -> LLM -> TTS
c1b5555 add mic-based STT module for fullvoice mode
82fb15d wire MCP tool calling into REPL and voice modes
145c66f add MCP tool bridge for REPL and voice modes
1cab2a3 feat(voice): add local TTS subcommand — FRIDAY speaks her replies
5a227f8 feat(repl): add text REPL subcommand bypassing LiveKit console
6b7e6a3 fix(ollama): stop LLM timeout storms + instant greeting
35d9957 fix: replace Unicode box-drawing chars in main.py with ASCII
36330bb feat: add Ollama as a local LLM provider
```
