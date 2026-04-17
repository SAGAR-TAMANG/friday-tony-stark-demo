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
import logging
import subprocess

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.llm import mcp

# Plugins
from livekit.plugins import google as lk_google, openai as lk_openai, sarvam, silero

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# VOICE_MODE selects the audio architecture:
#   "pipeline"         — STT → LLM → TTS chain (robust, ~1.5s round-trip)
#   "realtime_gemini"  — Gemini Live (speech-to-speech, ~300ms)
#   "realtime_openai"  — OpenAI Realtime (speech-to-speech, ~300ms)
VOICE_MODE = os.getenv("VOICE_MODE", "pipeline")

STT_PROVIDER = os.getenv("STT_PROVIDER", "sarvam")   # "sarvam" | "whisper" | "openai"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")   # "gemini" | "openai" | "ollama"
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")   # "openai" | "sarvam"

# April-2026 current model IDs. Bump these as new models ship.
GEMINI_LLM_MODEL   = os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-pro")
OPENAI_LLM_MODEL   = os.getenv("OPENAI_LLM_MODEL", "gpt-4.1")
OLLAMA_LLM_MODEL   = os.getenv("OLLAMA_LLM_MODEL", "llama3.1:8b")
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
GEMINI_REALTIME_MODEL = os.getenv("GEMINI_REALTIME_MODEL", "gemini-2.5-flash-live")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")

OPENAI_STT_MODEL   = os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe")
OPENAI_TTS_MODEL   = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")  # steerable voice
OPENAI_TTS_VOICE   = os.getenv("OPENAI_TTS_VOICE", "ash")              # calm, dry, confident
TTS_SPEED          = float(os.getenv("TTS_SPEED", "1.1"))

SARVAM_TTS_LANGUAGE = "en-IN"
SARVAM_TTS_SPEAKER  = "rahul"

# MCP server location & transport — must match server.py
MCP_TRANSPORT   = os.getenv("MCP_TRANSPORT", "streamable-http")  # "streamable-http" | "sse"
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8000"))
MCP_SERVER_HOST = os.getenv("MCP_SERVER_HOST", "127.0.0.1")

# Opt-in: bootstrap friday.core (memory + persistence + orchestrator) on session start.
# When false (default), the voice agent behaves exactly as before.
USE_ORCHESTRATOR = os.getenv("USE_ORCHESTRATOR", "false").lower() == "true"

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

### get_stock_quote / get_market_overview — Live Market Data
Call these whenever the user asks about the markets, a specific ticker, or indices.
- "What's Tesla doing?" → get_stock_quote("TSLA")
- "How's the market?" → get_market_overview()
- Never fabricate prices. If the tool fails, say so plainly: "Market feed's down right now, boss."
- Keep the spoken summary to one or two sentences: price, direction, headline cause if obvious.

### get_crypto_price — Crypto Quotes
- "Bitcoin?" / "How's ETH?" → get_crypto_price("BTC") / get_crypto_price("ETH")
- Same rule: never make up prices.

### get_weather / get_forecast — Weather
- "Weather in Mumbai?" → get_weather("Mumbai")
- "Will it rain tomorrow?" → get_forecast(location, days=2)

### search_web — Real-Time Web Search
- "Search for latest Anthropic news." / "Look up X." → search_web(query)
- Summarize the top two or three hits in a sentence. Never read URLs aloud.

### notify_user — Push Notification
- "Ping my phone about the 4pm meeting." → notify_user(title, priority, body)

---

## Greeting

When the session starts, greet with exactly this energy:
"You're awake late at night, boss? What are you up to?"

Warm. Slightly curious. Very FRIDAY.

---

## Behavioral Rules

1. Call tools silently and immediately — never say "I'm going to call..." Just do it.
2. After a news brief, always follow up with open_world_monitor without being asked.
3. Keep all spoken responses short — two to four sentences maximum.
4. No bullet points, no markdown, no lists. You are speaking, not writing.
5. Stay in character. You are F.R.I.D.A.Y. You are not an AI assistant — you are Stark's AI. Act like it.
6. Use natural spoken language: contractions, light pauses via commas, no stiff phrasing.
7. Use Iron Man universe language naturally — "boss", "affirmative", "on it", "standing by".
8. If a tool fails, report it calmly: "News feed's unresponsive right now, boss. Want me to try again?"

---

## Tone Reference

Right: "Looks like it's been a busy night out there, boss. Let me pull that up for you."
Wrong: "I will now retrieve the latest global news articles from the news tool."

Right: "S&P's up a quarter percent, boss — tech's carrying it. Nothing dramatic."  (after calling the tool)
Wrong: "The stock market performed positively with gains across major indices."

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

load_dotenv()

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
    # FastMCP streamable-http mounts at /mcp; legacy SSE mounts at /sse.
    path = "/mcp" if MCP_TRANSPORT == "streamable-http" else "/sse"
    override = os.getenv("MCP_SERVER_URL", "").strip()
    url = override or f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{path}"
    logger.info("MCP Server URL: %s | transport=%s", url, MCP_TRANSPORT)
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
    if STT_PROVIDER == "openai":
        logger.info("STT → OpenAI %s", OPENAI_STT_MODEL)
        return lk_openai.STT(model=OPENAI_STT_MODEL)
    if STT_PROVIDER == "whisper":
        logger.info("STT → OpenAI Whisper (legacy)")
        return lk_openai.STT(model="whisper-1")
    raise ValueError(f"Unknown STT_PROVIDER: {STT_PROVIDER!r}")


def _build_llm():
    if LLM_PROVIDER == "openai":
        logger.info("LLM → OpenAI (%s)", OPENAI_LLM_MODEL)
        return lk_openai.LLM(model=OPENAI_LLM_MODEL)
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM → Google Gemini (%s)", GEMINI_LLM_MODEL)
        return lk_google.LLM(model=GEMINI_LLM_MODEL, api_key=os.getenv("GOOGLE_API_KEY"))
    elif LLM_PROVIDER == "ollama":
        logger.info("LLM → Ollama (%s @ %s)", OLLAMA_LLM_MODEL, OLLAMA_BASE_URL)
        return lk_openai.LLM.with_ollama(model=OLLAMA_LLM_MODEL, base_url=OLLAMA_BASE_URL)
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
        tts_kwargs = {"model": OPENAI_TTS_MODEL, "voice": OPENAI_TTS_VOICE, "speed": TTS_SPEED}
        # gpt-4o-mini-tts accepts `instructions` to steer delivery; older models don't.
        if OPENAI_TTS_MODEL.startswith("gpt-4o-mini-tts"):
            tts_kwargs["instructions"] = (
                "Speak like F.R.I.D.A.Y. — calm, composed, dry wit. "
                "Measured pace. Warm but precise. British-tinged."
            )
        return lk_openai.TTS(**tts_kwargs)
    else:
        raise ValueError(f"Unknown TTS_PROVIDER: {TTS_PROVIDER!r}")


def _build_realtime():
    """Return a speech-to-speech RealtimeModel for ~300ms latency voice."""
    if VOICE_MODE == "realtime_gemini":
        logger.info("Realtime → Gemini Live (%s)", GEMINI_REALTIME_MODEL)
        return lk_google.beta.realtime.RealtimeModel(
            model=GEMINI_REALTIME_MODEL,
            voice="Puck",
            temperature=0.7,
            instructions=SYSTEM_PROMPT,
        )
    if VOICE_MODE == "realtime_openai":
        from livekit.plugins.openai import realtime as lk_openai_rt
        logger.info("Realtime → OpenAI (%s)", OPENAI_REALTIME_MODEL)
        return lk_openai_rt.RealtimeModel(
            model=OPENAI_REALTIME_MODEL,
            voice="verse",
            instructions=SYSTEM_PROMPT,
        )
    raise ValueError(f"_build_realtime called with VOICE_MODE={VOICE_MODE!r}")


def _lazy_noise_cancellation():
    """Return the noise_cancellation plugin module if installed, else None."""
    try:
        from livekit.plugins import noise_cancellation  # type: ignore
        return noise_cancellation
    except ImportError:
        logger.info("noise_cancellation plugin not installed — skipping BVC.")
        return None


def _lazy_turn_detector():
    """Return MultilingualModel class if turn-detector plugin is installed."""
    try:
        from livekit.plugins.turn_detector.multilingual import MultilingualModel  # type: ignore
        return MultilingualModel
    except ImportError:
        logger.info("turn_detector plugin not installed — using VAD heuristic.")
        return None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FridayAgent(Agent):
    """
    F.R.I.D.A.Y. – Iron Man-style voice assistant.
    Works in two modes:
      - pipeline:  stt + llm + tts + vad  (classic)
      - realtime:  realtime_llm only      (speech-to-speech)
    All tools are provided via the MCP server on the Windows host.
    """

    def __init__(self, *, realtime_llm=None, stt=None, llm=None, tts=None) -> None:
        mcp_servers = [
            mcp.MCPServerHTTP(
                url=_mcp_server_url(),
                transport_type=MCP_TRANSPORT,
                client_session_timeout_seconds=30,
            ),
        ]
        if realtime_llm is not None:
            super().__init__(
                instructions=SYSTEM_PROMPT,
                llm=realtime_llm,
                mcp_servers=mcp_servers,
            )
        else:
            super().__init__(
                instructions=SYSTEM_PROMPT,
                stt=stt,
                llm=llm,
                tts=tts,
                vad=silero.VAD.load(),
                mcp_servers=mcp_servers,
            )

    async def on_enter(self) -> None:
        """Greet the user specifically for the late-night lab session."""
        await self.session.generate_reply(
            instructions=(
                "Greet the user exactly with: 'Greetings boss, you're awake late at night today. What you up to?' "
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


def _maybe_bootstrap_core() -> None:
    """Boot friday.core subsystems when USE_ORCHESTRATOR=true. No-op otherwise."""
    if not USE_ORCHESTRATOR:
        return
    # Lazy imports so the default voice path never pays the core cost.
    try:
        from pathlib import Path
        from friday.config import config
        from friday.core import (
            AgentOrchestrator, DatabaseManager, MemoryManager, DEFAULT_AGENTS,
        )
    except ImportError as exc:
        logger.warning("USE_ORCHESTRATOR=true but friday.core import failed: %s", exc)
        return
    home = Path(config.FRIDAY_HOME).expanduser()
    memory = MemoryManager(
        episodes_path=home / "episodes",
        memory_file=Path(config.FRIDAY_MEMORY_PATH).expanduser(),
    )
    db = DatabaseManager(base_path=config.FRIDAY_DB_PATH)
    orch = AgentOrchestrator(memory_manager=memory, db_manager=db)
    for agent_def in DEFAULT_AGENTS.values():
        orch.register_agent(agent_def)
    logger.info("Orchestrator online | agents=%d home=%s", len(orch.agents), home)


async def entrypoint(ctx: JobContext) -> None:
    logger.info("FRIDAY online – room: %s | VOICE_MODE=%s", ctx.room.name, VOICE_MODE)
    _maybe_bootstrap_core()

    if VOICE_MODE.startswith("realtime"):
        agent = FridayAgent(realtime_llm=_build_realtime())
        session = AgentSession()
    else:
        logger.info("Pipeline | STT=%s LLM=%s TTS=%s", STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER)
        agent = FridayAgent(stt=_build_stt(), llm=_build_llm(), tts=_build_tts())
        turn_model = _lazy_turn_detector()
        session = AgentSession(
            turn_detection=turn_model() if turn_model else _turn_detection(),
            min_endpointing_delay=_endpointing_delay(),
        )

    start_kwargs = {"agent": agent, "room": ctx.room}
    nc = _lazy_noise_cancellation()
    if nc is not None:
        from livekit.agents.voice import RoomInputOptions
        start_kwargs["room_input_options"] = RoomInputOptions(noise_cancellation=nc.BVC())
        logger.info("Noise cancellation: BVC enabled.")

    await session.start(**start_kwargs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

def dev():
    """Wrapper to run the agent in dev mode automatically."""
    import sys
    # If no command was provided, inject 'dev'
    if len(sys.argv) == 1:
        sys.argv.append("dev")
    main()

if __name__ == "__main__":
    main()