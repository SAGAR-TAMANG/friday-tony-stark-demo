"""
FRIDAY – Voice Agent (MCP-powered)
===================================
Iron Man-style voice assistant that controls RGB lighting, runs diagnostics,
scans the network, and triggers dramatic boot sequences via an MCP server
running on the Windows host.

MCP Server URL is auto-resolved from WSL → Windows host IP.

Run:
  uv run agent_friday.py dev      – LiveKit Cloud mode
  uv run agent_friday.py console  – text-only console mode
"""

import os
import sys
import logging
import subprocess
import httpx

# Force UTF-8 on Windows (cp1252 can't encode emojis used by LiveKit/rich)
os.environ.setdefault("PYTHONUTF8", "1")
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

# Load .env BEFORE reading any os.getenv() constants so env vars are available
load_dotenv()

from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.agents.llm import mcp
from livekit.agents.types import APIConnectOptions

# Plugins
from livekit.plugins import google as lk_google, openai as lk_openai, sarvam, silero

# ---------------------------------------------------------------------------
# CONFIG  (all os.getenv calls happen after load_dotenv() above)
# ---------------------------------------------------------------------------

STT_PROVIDER       = "sarvam"
LLM_PROVIDER       = "ollama"   # "gemini" | "openai" | "ollama"
TTS_PROVIDER       = "openai"

GEMINI_LLM_MODEL   = "gemini-2.5-flash"
OPENAI_LLM_MODEL   = "gpt-4o"

# Ollama — runs locally; no API key needed.
# Set OLLAMA_MODEL in .env to any pulled model — qwen2.5:7b-instruct is the
# default because it emits proper structured tool_calls via Ollama's OpenAI-compat
# layer.  llama3.1:latest emits tool calls as raw text (broken on Ollama 0.3+).
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

OPENAI_TTS_MODEL   = "tts-1"
OPENAI_TTS_VOICE   = "nova"       # "nova" has a clean, confident female tone
TTS_SPEED           = 1.15

SARVAM_TTS_LANGUAGE = "en-IN"
SARVAM_TTS_SPEAKER  = "rahul"

# MCP server running on Windows host
MCP_SERVER_PORT = 8000

# Tool allowlist for REPL / voice modes.  Small models + CPU can't afford
# 18 tool schemas in prefill — set FRIDAY_TOOLS=* (or "all") to expose all,
# or CSV override to customize.  Default: 6 demo-critical tools → ~60s prefill.
_DEFAULT_TOOLS = (
    "get_current_time,get_weather,get_stock_price,"
    "search_web,get_world_news,get_system_diagnostics"
)
FRIDAY_TOOLS = os.getenv("FRIDAY_TOOLS", _DEFAULT_TOOLS)


def _tool_allowlist() -> list[str] | None:
    raw = FRIDAY_TOOLS.strip()
    if raw in {"*", "all", ""}:
        return None  # expose all
    return [t.strip() for t in raw.split(",") if t.strip()]

# ---------------------------------------------------------------------------
# System prompt – F.R.I.D.A.Y.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are F.R.I.D.A.Y. — Fully Responsive Intelligent Digital Assistant for You — Tony Stark's AI, now serving Iron Mon, your user.

You are calm, composed, and always informed. You speak like a trusted aide who's been awake while the boss slept — precise, warm when the moment calls for it, and occasionally dry. You brief, you inform, you move on. No rambling.

Your tone: relaxed but sharp. Conversational, not robotic. Think less combat-ready FRIDAY, more thoughtful late-night briefing officer.

---

## Capabilities

### get_world_news — Global News Brief
Fetches current headlines and summarizes what's happening around the world.

Trigger phrases:
- "What's happening?" / "Brief me" / "What did I miss?" / "Catch me up"
- "What's going on in the world?" / "Any news?" / "World update"

Behavior:
- Call the tool first. No narration before calling.
- After getting results, give a short 3–5 sentence spoken brief. Hit the biggest stories only.
- Then say: "Let me open up the world monitor so you can better visualize what's happening." and immediately call open_world_monitor.

### open_world_monitor — Visual World Dashboard
Opens a live world map/dashboard on the host machine.

- Always call this after delivering a world news brief, unprompted.
- No need to explain what it does beyond: "Let me open up the world monitor."

### get_stock_price / get_market_overview — Finance
get_stock_price fetches real-time price and daily change for any ticker (AAPL, TSLA, ^DJI…).
get_market_overview returns a snapshot of S&P 500, Dow Jones, and NASDAQ.

Trigger phrases:
- "How's [company] doing?" / "What's TSLA at?" / "Check the markets"
- "How are stocks today?" / "Market overview"

Behavior:
- Call the tool silently. Deliver the result in one or two spoken sentences.
- Example: "Tesla's sitting at $182, down about 1.4% on the day, boss. Nothing dramatic."

### get_weather — Weather
Fetches current conditions for any city via Open-Meteo (no API key required).

Trigger phrases:
- "What's the weather in [city]?" / "How's it looking in [city]?" / "Temperature in [city]"

Behavior:
- Call silently. Speak the result naturally — temperature, condition, wind, humidity.
- Example: "Mumbai's at 31°C right now, partly cloudy. Humidity's high — 78%. Typical."

### get_system_diagnostics — System Health
Returns live CPU usage, RAM usage, and battery status from the host machine.

Trigger phrases:
- "How's the system running?" / "RAM check" / "CPU usage" / "Battery status" / "System health"

Behavior:
- Report the key numbers conversationally.
- Example: "CPU's at 22%, RAM's 9.4 of 16 gigs. Battery at 74%, plugged in."

### create_ticket / list_tickets — Task Management
create_ticket logs a new task. list_tickets retrieves open or all tasks.

Trigger phrases:
- "Note that…" / "Add a task…" / "What's on the list?" / "Open tasks"

Behavior:
- Confirm ticket creation with a brief acknowledgment.
- Summarize the list concisely — no reading every item verbatim.

---

## Greeting

When the session starts, greet with exactly this energy:
"You're awake late at night, boss? What are you up to?"

Warm. Slightly curious. Very FRIDAY.

---

## Behavioral Rules

1. Call tools silently and immediately — never say "I'm going to call..." Just do it.
2. For ANY question that requires live data — time, date, weather, prices, news, system health, calculations — call the relevant tool. Never answer these from training memory.
3. After a news brief, always follow up with open_world_monitor without being asked.
4. Keep all spoken responses short — two to four sentences maximum.
5. No bullet points, no markdown, no lists. You are speaking, not writing.
6. Stay in character. You are F.R.I.D.A.Y. You are not an AI assistant — you are Stark's AI. Act like it.
7. Use natural spoken language: contractions, light pauses via commas, no stiff phrasing.
8. Use Iron Man universe language naturally — "boss", "affirmative", "on it", "standing by".
9. If a tool fails, report it calmly: "News feed's unresponsive right now, boss. Want me to try again?"

---

## Tone Reference

Right: "Looks like it's been a busy night out there, boss. Let me pull that up for you."
Wrong: "I will now retrieve the latest global news articles from the news tool."

Right: "Markets were pretty healthy today — nothing too wild."
Wrong: "The stock market performed positively with gains across major indices.

---

### add_reminder / list_reminders / clear_reminders — Session Memory
add_reminder saves a note for the current session.
list_reminders recalls all saved notes.
clear_reminders wipes the slate.

Trigger phrases:
- "Remember that…" / "Note this…" / "Don't forget…" / "What did I tell you?" / "My notes"

Behavior:
- Confirm saves briefly: "Got it. Noted."
- When listing, summarize — don't read them verbatim robotically.

### get_current_time — Live Time & Date
Returns the actual current time and date from the system clock.

Trigger phrases:
- "What time is it?" / "What's the time?" / "Current time" / "What's today's date?" / "What day is it?"

Behavior:
- Call the tool silently. Never answer time/date questions from memory — always use this tool.
- Example: "It's 11:42 PM on a Thursday, boss."

### calculate — Math
Evaluates any arithmetic expression safely: +, -, *, /, **, sqrt(), sin(), cos(), log(), pi, e…

Trigger phrases:
- "What's [math]?" / "Calculate…" / "How much is…" / any numerical question

Behavior:
- Call silently, speak result naturally.
- Example: "That comes out to 1,048,576, boss."

---

## CRITICAL RULES

1. NEVER say tool names, function names, or anything technical. No "get_world_news", no "open_world_monitor", nothing like that. Ever.
2. Before calling any tool, say something natural like: "Give me a sec, boss." or "Wait, let me check." Then call the tool silently.
3. After the news brief, silently call open_world_monitor. The only thing you say is: "Let me open up the world monitor for you."
4. You are a voice. Speak like one. No lists, no markdown, no function names, no technical language of any kind.
""".strip()
# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

logger = logging.getLogger("friday-agent")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Resolve Windows host IP from WSL
# ---------------------------------------------------------------------------

def _get_windows_host_ip() -> str:
    """Get the Windows host IP by looking at the default network route."""
    try:
        # 'ip route' is the most reliable way to find the 'default' gateway
        # which is always the Windows host in WSL.
        cmd = "ip route show default | awk '{print $3}'"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=2
        )
        ip = result.stdout.strip()
        if ip:
            logger.info("Resolved Windows host IP via gateway: %s", ip)
            return ip
    except Exception as exc:
        logger.warning("Gateway resolution failed: %s. Trying fallback...", exc)

    # Fallback to your original resolv.conf logic if 'ip route' fails
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if "nameserver" in line:
                    ip = line.split()[1]
                    logger.info("Resolved Windows host IP via nameserver: %s", ip)
                    return ip
    except Exception:
        pass

    return "127.0.0.1"

def _mcp_server_url() -> str:
    # host_ip = _get_windows_host_ip()
    # url = f"http://{host_ip}:{MCP_SERVER_PORT}/sse"
    # url = f"https://ongoing-colleague-samba-pioneer.trycloudflare.com/sse"
    url = f"http://127.0.0.1:{MCP_SERVER_PORT}/sse"
    logger.info("MCP Server URL: %s", url)
    return url


def _ollama_url() -> str:
    """
    Return the Ollama base URL, auto-replacing localhost/127.0.0.1 with the
    Windows host IP when the agent is running inside WSL.
    Ollama must be running on the host with its API port exposed (default 11434).
    """
    url = OLLAMA_BASE_URL
    if "localhost" in url or "127.0.0.1" in url:
        host_ip = _get_windows_host_ip()
        url = url.replace("localhost", host_ip).replace("127.0.0.1", host_ip)
    logger.info("Ollama URL: %s  model: %s", url, OLLAMA_MODEL)
    return url


# ---------------------------------------------------------------------------
# Build provider instances
# ---------------------------------------------------------------------------

def _build_stt():
    if STT_PROVIDER == "sarvam":
        logger.info("STT → Sarvam Saaras v3")
        return sarvam.STT(
            language="unknown",
            model="saaras:v3",
            mode="transcribe",
            flush_signal=True,
            sample_rate=16000,
        )
    elif STT_PROVIDER == "whisper":
        logger.info("STT → OpenAI Whisper")
        return lk_openai.STT(model="whisper-1")
    else:
        raise ValueError(f"Unknown STT_PROVIDER: {STT_PROVIDER!r}")


def _patch_llm_conn_options(llm_instance, *, timeout: float = 120.0):
    """
    Wrap llm.chat() so every call uses a generous conn_options.
    APIConnectOptions is a frozen dataclass — the only way to override its
    10-second default is to pass conn_options explicitly at each call site.
    """
    _opts = APIConnectOptions(timeout=timeout, max_retry=3, retry_interval=2.0)
    _original_chat = llm_instance.chat

    def _chat_with_timeout(**kwargs):
        # Only inject if caller didn't supply their own conn_options
        kwargs.setdefault("conn_options", _opts)
        return _original_chat(**kwargs)

    llm_instance.chat = _chat_with_timeout
    logger.info("LLM chat() patched: conn_options.timeout=%.0fs", timeout)
    return llm_instance


def _build_llm():
    if LLM_PROVIDER == "openai":
        logger.info("LLM → OpenAI (%s)", OPENAI_LLM_MODEL)
        return lk_openai.LLM(model=OPENAI_LLM_MODEL)
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM → Google Gemini (%s)", GEMINI_LLM_MODEL)
        return lk_google.LLM(model=GEMINI_LLM_MODEL, api_key=os.getenv("GOOGLE_API_KEY"))
    elif LLM_PROVIDER == "ollama":
        # Ollama's OpenAI-compatible endpoint — no API key required.
        # Two separate timeouts to fix:
        #   1. httpx read timeout (default 5s) — pass explicit httpx.Timeout
        #   2. APIConnectOptions.timeout (default 10s, frozen dataclass) — wrap chat()
        # read=600s — prefill with 18-tool schema on CPU measured at ~170s cold.
        # KV cache amortizes subsequent calls, but first tool turn needs headroom.
        _timeout = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=15.0)
        llm = lk_openai.LLM(
            model=OLLAMA_MODEL,
            base_url=_ollama_url(),
            api_key="ollama",          # required by client lib; not validated
            timeout=_timeout,
        )
        return _patch_llm_conn_options(llm, timeout=120.0)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")


def _build_tts():
    if TTS_PROVIDER == "sarvam":
        logger.info("TTS → Sarvam Bulbul v3")
        return sarvam.TTS(
            target_language_code=SARVAM_TTS_LANGUAGE,
            model="bulbul:v3",
            speaker=SARVAM_TTS_SPEAKER,
            pace=TTS_SPEED,
        )
    elif TTS_PROVIDER == "openai":
        logger.info("TTS → OpenAI TTS (%s / %s)", OPENAI_TTS_MODEL, OPENAI_TTS_VOICE)
        return lk_openai.TTS(model=OPENAI_TTS_MODEL, voice=OPENAI_TTS_VOICE, speed=TTS_SPEED)
    else:
        raise ValueError(f"Unknown TTS_PROVIDER: {TTS_PROVIDER!r}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def _is_console_mode() -> bool:
    """True when the agent is launched with the 'console' subcommand (text-only, no audio)."""
    return "console" in sys.argv


_GREETING = "Greetings boss, you're awake late at night today. What you up to?"

# Tokens in system-prompt + MCP tool schemas can exceed 5 000 on CPU-only hardware,
# making Ollama's prefill take 5-10 min. We bypass the LLM for the opening line so
# the session feels instant, then Ollama handles all real user questions.
_GREETING_INSTRUCTION_FRAGMENT = "Greet the user exactly with"


class FridayAgent(Agent):
    """
    F.R.I.D.A.Y. – Iron Man-style voice assistant.
    All tools are provided via the MCP server on the Windows host.
    In console mode STT/TTS/VAD are omitted so no cloud audio keys are needed.
    """

    def __init__(self, llm, stt=None, tts=None) -> None:
        self._audio_enabled = tts is not None  # track before super().__init__
        kwargs: dict = {
            "instructions": SYSTEM_PROMPT,
            "llm": llm,
            "mcp_servers": [
                mcp.MCPServerHTTP(
                    url=_mcp_server_url(),
                    transport_type="sse",
                    client_session_timeout_seconds=30,
                ),
            ],
        }
        # Audio pipeline — only when STT/TTS are available (i.e. not console mode)
        if stt:
            kwargs["stt"] = stt
            kwargs["vad"] = silero.VAD.load()
        if tts:
            kwargs["tts"] = tts
        super().__init__(**kwargs)

    async def llm_node(self, chat_ctx, tools, model_settings):
        """
        Override so the greeting bypasses Ollama entirely.
        CPU-only inference needs 5-10 min for a 5k-token prompt; the opening
        line is canned so the session feels instant.  All real questions go
        through Ollama as normal.
        """
        from livekit.agents.types import NOT_GIVEN

        # Detect the greeting instruction injected by on_enter()
        msgs = chat_ctx.messages()
        last_msg = msgs[-1] if msgs else None
        last_text = getattr(last_msg, "content", "") or ""
        if _GREETING_INSTRUCTION_FRAGMENT in last_text:
            logger.info("Greeting shortcut — skipping Ollama prefill")
            yield _GREETING
            return

        # All other turns: use the real LLM with the session's conn_options
        activity = self._get_activity_or_raise()
        conn_opts = activity.session.conn_options.llm_conn_options
        tool_choice = model_settings.tool_choice if model_settings else NOT_GIVEN
        async with activity.llm.chat(
            chat_ctx=chat_ctx,
            tools=tools,
            tool_choice=tool_choice,
            conn_options=conn_opts,
        ) as stream:
            async for chunk in stream:
                yield chunk

    async def on_enter(self) -> None:
        """Greet the user on session start."""
        # Disable audio BEFORE generating the first reply so TTS is never invoked
        if not self._audio_enabled:
            self.session.output.set_audio_enabled(False)
        await self.session.generate_reply(
            instructions=(
                f"{_GREETING_INSTRUCTION_FRAGMENT}: '{_GREETING}' "
                "Maintain a helpful but dry tone."
            )
        )


# ---------------------------------------------------------------------------
# LiveKit entry point
# ---------------------------------------------------------------------------

def _turn_detection() -> str:
    return "stt" if STT_PROVIDER == "sarvam" else "vad"


def _endpointing_delay() -> float:
    return {"sarvam": 0.07, "whisper": 0.3}.get(STT_PROVIDER, 0.1)


async def entrypoint(ctx: JobContext) -> None:
    console = _is_console_mode()
    stt = None if console else _build_stt()
    llm = _build_llm()
    tts = None if console else _build_tts()

    logger.info(
        "FRIDAY online – mode: %s | STT=%s | LLM=%s | TTS=%s",
        "console" if console else "voice",
        STT_PROVIDER if stt else "none",
        LLM_PROVIDER,
        TTS_PROVIDER if tts else "none",
    )

    # Generous LLM timeout — local models (Ollama) need 120-300s on CPU-only hardware
    # because token prefill scales with context length (system prompt + tool schemas).
    _llm_timeout = 300.0 if LLM_PROVIDER == "ollama" else 30.0
    _llm_opts = APIConnectOptions(timeout=_llm_timeout, max_retry=0)

    session_kwargs: dict = {
        "conn_options": SessionConnectOptions(llm_conn_options=_llm_opts),
    }
    if not console:
        session_kwargs["turn_detection"] = _turn_detection()
        session_kwargs["min_endpointing_delay"] = _endpointing_delay()

    session = AgentSession(**session_kwargs)

    await session.start(
        agent=FridayAgent(llm=llm, stt=stt, tts=tts),
        room=ctx.room,
    )


# ---------------------------------------------------------------------------
# Shared chat driver with tool-calling.
# LiveKit streams text content AND partial tool-call deltas over the same
# ChatChunk iterator.  We collect both, then if tool calls landed, dispatch
# them via the MCP client, append FunctionCall + FunctionCallOutput items to
# the ChatContext, and re-invoke llm.chat() so the model can continue with
# the tool results in context.  Capped at 4 iterations as a runaway guard.
# ---------------------------------------------------------------------------

async def _chat_with_tools(
    llm,
    ctx,
    tools,
    dispatch,
    conn_opts,
    on_text,
    *,
    max_iters: int = 4,
) -> str:
    from livekit.agents.llm import FunctionCall, FunctionCallOutput

    full_text_parts: list[str] = []

    for _ in range(max_iters):
        iter_text: list[str] = []
        # call_id -> {"name": str, "arguments": str}
        tool_calls: dict[str, dict] = {}

        chat_kwargs = {"chat_ctx": ctx, "conn_options": conn_opts}
        if tools:
            chat_kwargs["tools"] = tools

        async with llm.chat(**chat_kwargs) as stream:
            async for chunk in stream:
                delta = getattr(chunk, "delta", None)
                if delta is None:
                    continue
                if delta.content:
                    on_text(delta.content)
                    iter_text.append(delta.content)
                # Deltas may carry partial tool calls — merge by call_id.
                for tc in (delta.tool_calls or []):
                    slot = tool_calls.setdefault(tc.call_id, {"name": "", "arguments": ""})
                    if tc.name:
                        slot["name"] = tc.name
                    if tc.arguments:
                        slot["arguments"] += tc.arguments

        text_this_iter = "".join(iter_text).strip()
        if text_this_iter:
            full_text_parts.append(text_this_iter)

        if not tool_calls:
            break  # plain text answer — we're done

        # Record the assistant's tool-call intent, then each tool's result.
        items = []
        for call_id, info in tool_calls.items():
            items.append(FunctionCall(
                call_id=call_id,
                name=info["name"],
                arguments=info["arguments"],
            ))
        ctx.insert(items)

        for call_id, info in tool_calls.items():
            on_text(f"\n[tool: {info['name']}({info['arguments'][:80]})]\n")
            result = await dispatch(info["name"], info["arguments"])
            ctx.insert(FunctionCallOutput(
                call_id=call_id,
                name=info["name"],
                output=result,
                is_error=False,
            ))

    return "\n".join(full_text_parts).strip()


async def _prewarm_llm(llm, ctx, tools, conn_opts) -> float:
    """
    Prime Ollama's KV cache with the system prompt + tool schemas.

    Sends one throwaway chat over a *copy* of the real ChatContext with a
    trivial user message and drains the stream to completion.  Ollama's
    OpenAI-compat backend prefix-caches KV by token sequence, so the real
    first turn reuses ~2000-2500 tokens of prefill and only has to run
    the new user-message + generation.

    WHY full drain (not early break): closing the stream mid-response can
    cause Ollama to abort without persisting the KV cache, defeating the
    purpose.  Completing the request guarantees the prefix is cached.

    Returns elapsed seconds so the caller can report it.  Failures are
    swallowed — a flaky prewarm must never block the demo.
    """
    import time

    try:
        warm_ctx = ctx.copy()
        # "say ok" is minimal — 2-token response from most tool-tuned models,
        # keeps total prewarm cost close to prefill-only without risking the
        # model deciding to emit a tool call for something substantive.
        warm_ctx.add_message(role="user", content="reply with exactly: ok")
        chat_kwargs = {"chat_ctx": warm_ctx, "conn_options": conn_opts}
        if tools:
            chat_kwargs["tools"] = tools

        t0 = time.time()
        async with llm.chat(**chat_kwargs) as stream:
            async for _chunk in stream:
                pass  # drain fully so Ollama commits the KV cache
        return time.time() - t0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Text REPL  — bypasses LiveKit console mode entirely.
# LiveKit's `console` subcommand hooks a mic/speaker pipeline by default and is
# awkward for pure-text Ollama sessions.  `repl` drives the same patched LLM
# with plain input()/print() so you get an instant greeting and a normal shell.
# ---------------------------------------------------------------------------

async def _run_repl() -> None:
    import asyncio  # noqa: F401 — used by caller
    from livekit.agents.llm import ChatContext
    from friday_mcp import open_mcp

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print()
    print("=" * 60)
    print("  F.R.I.D.A.Y. — text REPL  (LLM: %s | model: %s)" % (LLM_PROVIDER, OLLAMA_MODEL))
    print("  type 'exit' / 'quit' / Ctrl-C to leave")
    print("=" * 60)

    llm = _build_llm()  # inherits httpx + APIConnectOptions timeout fixes
    conn_opts = APIConnectOptions(timeout=600.0, max_retry=0, retry_interval=2.0)

    # Connect to the MCP server for tools.  Fails soft — if the server is
    # down, the REPL still works as a plain chat.
    mcp_client = None
    tools = []
    dispatch = None
    try:
        mcp_client, tools, dispatch = await open_mcp(_mcp_server_url(), allow=_tool_allowlist())
        print(f"[mcp] {len(tools)} tools loaded from {_mcp_server_url()}")
    except Exception as exc:
        print(f"[mcp] unavailable ({exc}) — running without tools")

    ctx = ChatContext()
    ctx.add_message(role="system", content=SYSTEM_PROMPT)

    # Canned greeting — no LLM call, instant UX
    print()
    print("friday> " + _GREETING)
    ctx.add_message(role="assistant", content=_GREETING)

    # Prewarm Ollama's KV cache with system + tools + greeting prefix so the
    # real first user turn only has to prefill the user message + generation.
    if tools:
        print("[warmup] priming model cache (first run: ~60-180s)...", flush=True)
        elapsed = await _prewarm_llm(llm, ctx, tools, conn_opts)
        print(f"[warmup] done in {elapsed:.1f}s — next turn should be snappy")

    def _emit(s: str) -> None:
        print(s, end="", flush=True)

    try:
        while True:
            try:
                user_input = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nfriday> signing off, boss.")
                return

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "bye", ":q"}:
                print("friday> signing off, boss.")
                return

            ctx.add_message(role="user", content=user_input)

            print("friday> ", end="", flush=True)
            try:
                full = await _chat_with_tools(llm, ctx, tools, dispatch, conn_opts, _emit)
                print()
            except Exception as exc:
                print(f"\n[llm error: {exc}]")
                continue

            if full:
                ctx.add_message(role="assistant", content=full)
    finally:
        if mcp_client is not None:
            try:
                await mcp_client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Voice REPL  — text-in, voice-out. FRIDAY *speaks* her replies via Windows
# SAPI (pyttsx3).  Zero cloud keys, zero model downloads — the voice engine
# ships with Windows.  STT is still text-typed; add faster-whisper later for
# a full mic→STT→LLM→TTS→speaker loop.
# ---------------------------------------------------------------------------

async def _run_voice(voice_input: bool = False) -> None:
    """Voice REPL.  voice_input=True adds mic-based PTT via faster-whisper."""
    import asyncio
    from livekit.agents.llm import ChatContext
    from friday_mcp import open_mcp

    # STT loaded lazily — only if voice_input requested.
    whisper = None
    if voice_input:
        from friday_stt import load_whisper, record_until_enter, transcribe
        print("[stt] loading whisper (first run downloads ~75MB)...", flush=True)
        whisper = load_whisper("tiny.en")

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # TTS via a persistent PowerShell daemon.
    # Rationale: pyttsx3 + asyncio.to_thread deadlocks on Windows (SAPI needs
    # an STA COM apartment; asyncio workers are MTA).  Spawning one PS process
    # per utterance works but pays ~15s .NET JIT per spawn.  A single long-
    # lived daemon amortizes startup, then each utterance is a stdin write +
    # blocking .Speak() + sentinel echo for sync.
    DAEMON_SCRIPT = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.Rate = 1;"
        "foreach ($v in $s.GetInstalledVoices()) {"
        "  if ($v.VoiceInfo.Name -like '*Zira*') {"
        "    $s.SelectVoice($v.VoiceInfo.Name); break"
        "  }"
        "};"
        "[Console]::Out.WriteLine('READY');"
        "while (($line = [Console]::In.ReadLine()) -ne $null) {"
        "  if ($line -eq '__EXIT__') { break };"
        "  $s.Speak($line);"
        "  [Console]::Out.WriteLine('DONE')"
        "}"
    )

    print("[tts] starting SAPI daemon (one-time ~5s .NET init)...", flush=True)
    tts_proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-Command", DAEMON_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    # Wait for READY line so we don't race the first .Speak()
    ready = await tts_proc.stdout.readline()
    if ready.strip() != b"READY":
        print("[tts] daemon failed to start — falling back to silent mode")
        tts_proc = None

    async def speak(text: str) -> None:
        if not text or tts_proc is None or tts_proc.stdin is None:
            return
        # Collapse whitespace and strip problematic chars for a single stdin line
        line = " ".join(text.split())
        tts_proc.stdin.write((line + "\n").encode("utf-8", errors="replace"))
        await tts_proc.stdin.drain()
        # Wait for DONE sentinel so REPL prompt doesn't reappear mid-speech
        await tts_proc.stdout.readline()

    async def shutdown_tts() -> None:
        if tts_proc and tts_proc.stdin:
            try:
                tts_proc.stdin.write(b"__EXIT__\n")
                await tts_proc.stdin.drain()
            except Exception:
                pass
            try:
                await asyncio.wait_for(tts_proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                tts_proc.kill()

    print()
    print("=" * 60)
    mode = "fullvoice (mic -> STT -> LLM -> TTS)" if voice_input else "voice (text -> LLM -> TTS)"
    print(f"  F.R.I.D.A.Y. — {mode}  (LLM: {LLM_PROVIDER})")
    if voice_input:
        print("  press ENTER to talk, ENTER again to stop.  type 'exit' to quit.")
    else:
        print("  type your question — FRIDAY will type AND speak the reply")
        print("  type 'exit' / 'quit' / Ctrl-C to leave")
    print("=" * 60)

    llm = _build_llm()
    conn_opts = APIConnectOptions(timeout=600.0, max_retry=0, retry_interval=2.0)

    # Connect to MCP for tool calling (soft-fail).
    mcp_client = None
    tools = []
    dispatch = None
    try:
        mcp_client, tools, dispatch = await open_mcp(_mcp_server_url(), allow=_tool_allowlist())
        print(f"[mcp] {len(tools)} tools loaded from {_mcp_server_url()}")
    except Exception as exc:
        print(f"[mcp] unavailable ({exc}) — running without tools")

    ctx = ChatContext()
    ctx.add_message(role="system", content=SYSTEM_PROMPT)

    print()
    print("friday> " + _GREETING)
    ctx.add_message(role="assistant", content=_GREETING)

    # Overlap TTS of the greeting with model prewarm — SAPI runs in a
    # separate PowerShell process, Ollama in another, so they don't contend.
    # By the time the greeting finishes speaking (~5s), the KV cache is
    # usually primed, making the first user turn feel instant.
    if tools:
        print("[warmup] priming model cache in parallel with greeting...", flush=True)
        _, elapsed = await asyncio.gather(
            speak(_GREETING),
            _prewarm_llm(llm, ctx, tools, conn_opts),
        )
        print(f"[warmup] model cache ready ({elapsed:.1f}s)")
    else:
        await speak(_GREETING)

    def _emit(s: str) -> None:
        print(s, end="", flush=True)

    async def _read_turn() -> str:
        """Get the next user turn — mic or keyboard depending on voice_input."""
        if not voice_input:
            return input("\nyou> ").strip()
        # Offload blocking record+transcribe so the event loop stays responsive.
        print()
        audio = await asyncio.to_thread(record_until_enter)
        if audio.size == 0:
            return ""
        print("[stt] transcribing...", flush=True)
        text = await asyncio.to_thread(transcribe, whisper, audio)
        if text:
            print(f"you> {text}")
        else:
            print("[stt] (no speech detected)")
        return text.strip()

    try:
        while True:
            try:
                user_input = await _read_turn()
            except (EOFError, KeyboardInterrupt):
                print("\nfriday> signing off, boss.")
                await speak("signing off, boss.")
                return

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "bye", ":q"}:
                print("friday> signing off, boss.")
                await speak("signing off, boss.")
                return

            ctx.add_message(role="user", content=user_input)

            print("friday> ", end="", flush=True)
            try:
                full = await _chat_with_tools(llm, ctx, tools, dispatch, conn_opts, _emit)
                print()
            except Exception as exc:
                print(f"\n[llm error: {exc}]")
                continue

            if full:
                ctx.add_message(role="assistant", content=full)
                await speak(full)
    finally:
        if mcp_client is not None:
            try:
                await mcp_client.close()
            except Exception:
                pass
        await shutdown_tts()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Route 'repl' / 'voice' subcommands BEFORE LiveKit's cli.run_app takes
    # over, because cli.run_app would reject any unknown subcommand.
    if len(sys.argv) > 1 and sys.argv[1] == "repl":
        import asyncio
        asyncio.run(_run_repl())
        return
    if len(sys.argv) > 1 and sys.argv[1] == "voice":
        import asyncio
        asyncio.run(_run_voice(voice_input=False))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "fullvoice":
        import asyncio
        asyncio.run(_run_voice(voice_input=True))
        return
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

def dev():
    """Wrapper to run the agent in dev mode automatically."""
    # If no command was provided, inject 'dev'
    if len(sys.argv) == 1:
        sys.argv.append("dev")
    main()

if __name__ == "__main__":
    main()