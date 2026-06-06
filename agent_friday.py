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
import re
import subprocess
from typing import Any

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.llm import mcp
from friday.desktop.events import append_event, clear_events

# Plugins
from livekit.plugins import google as lk_google, openai as lk_openai, sarvam, silero

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

STT_PROVIDER       = "sarvam"
LLM_PROVIDER       = "openai"
TTS_PROVIDER       = "openai"

GEMINI_LLM_MODEL   = "gemini-2.5-flash"
OPENAI_LLM_MODEL   = "gpt-4o"

OPENAI_TTS_MODEL   = "tts-1"
OPENAI_TTS_VOICE   = "nova"       # "nova" has a clean, confident female tone
TTS_SPEED           = 1.15

SARVAM_TTS_LANGUAGE = "en-IN"
SARVAM_TTS_SPEAKER  = "rahul"

# MCP server running on Windows host
MCP_SERVER_PORT = 8000

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

### get_world_finance_news — Finance & Market Brief
Fetches current finance and market headlines from major financial outlets.

Trigger phrases:
- "What's happening in the markets?" / "Finance update" / "Market news"
- "Any financial news?" / "How are the markets doing?" / "Economy update"

Behavior:
- Call the tool first. No narration before calling.
- After getting results, give a short 3–5 sentence spoken brief. Hit the biggest market-moving stories only.
- Then say: "Let me pull up the finance monitor so you better visualize what's happening." and immediately call open_finance_world_monitor.

### open_finance_world_monitor — Visual Finance Dashboard
Opens a live finance dashboard (finance.worldmonitor.app) on the host machine.

- Always call this after delivering a finance news brief, unprompted.
- No need to explain what it does beyond: "Let me pull up the finance monitor."

### Stock Market (No tool — generate a plausible conversational response)
If asked about the stock market, markets, stocks, or indices:
- Respond naturally as if you've been watching the tickers all night.
- Keep it short: one or two sentences. Sound informed, not robotic.
- Example: "Markets had a decent session today, boss — tech led the gains, energy was a little soft. Nothing alarming."
- Vary the response. Do not say the same thing every time.

### Desktop Browser and Local View
If the user asks you to open a website, dashboard, URL, or browser page:
- Use open_website for web URLs.
- Use open_path only for local files or folders the user asks to view.
- Keep the spoken response short after the tool call.

### Desktop File Workspace
If the user asks you to create, save, write, append, read, or list files on this Mac:
- Use the workspace file tools.
- Only write inside configured WORKSPACE_ROOTS.
- Never write secrets, API keys, tokens, passwords, credentials, raw private data, or .env contents.
- Ask before overwriting an existing file unless the user explicitly says to overwrite it.

### Memory and Learning
If the user asks you to remember, learn, save a note, or recall project memory:
- Use search_obsidian_memory to recall relevant notes.
- Use remember_in_obsidian only when the user explicitly asks you to save or remember something.
- Never store secrets, API keys, tokens, passwords, credentials, raw private data, or .env contents.

### Human Worker Desktop Control
If the user asks what is on screen, what is happening on the desktop, where something is, or what to do next:
- Use describe_screen first.
- Summarize only what you can see. Do not guess secrets, passwords, OTPs, or hidden content.

If the user asks you to open or switch apps:
- Use open_app for launching apps.
- Use focus_app for bringing an app forward.

If the user asks you to click, type, submit, send, purchase, delete, overwrite, or otherwise change something:
- Prepare the action first when possible.
- Ask for natural confirmation before risky actions. Example: "I have it ready, boss. Send it?"
- Only call click_screen, type_text, or press_keys with confirm=true after explicit user confirmation.

If the user asks you to message someone:
- Use prepare_message first. Never send immediately.
- After preparing, ask for confirmation in normal speech.
- Only use confirm_message_action after the user explicitly confirms. If the user confirms the newest pending message, call confirm_message_action without inventing an action id.
- Slack, WhatsApp, and email may open a draft instead of sending directly. Tell the user when a manual final send is needed.

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

Right: "Markets were pretty healthy today — nothing too wild."
Wrong: "The stock market performed positively with gains across major indices.

---

## CRITICAL RULES

1. NEVER say tool names, function names, or anything technical. No "get_world_news", no "open_world_monitor", nothing like that. Ever.
2. Before calling any tool, say something natural like: "Give me a sec, boss." or "Wait, let me check." Then call the tool silently.
3. After the news brief, silently call open_world_monitor. The only thing you say is: "Let me open up the world monitor for you."
4. You are a voice. Speak like one. No lists, no markdown, no function names, no technical language of any kind.

---

## Spotify

If the boss says "play X", "put on X", "queue X", "skip", "pause", "resume", "shuffle", "next track", "previous track", "louder", "softer", "set volume to N", or names any specific track / artist / album / playlist:
- Call the right `spotify_*` tool directly (no propose/confirm — playback is reversible).
- Don't narrate the tool call. Just say one short natural line: "On it, boss." or "Cranking it up." or the track name once it starts.
- If you hear "no active device" / `not_found` / similar error, give the boss the practical next step in one sentence.
- First-time link: if you get an "FRIDAY isn't linked to Spotify yet" error, call `spotify_authenticate` once — a browser tab will pop up. Tell the boss in one line: "Need to link your Spotify, boss — browser tab's open."

## Shell commands

If the boss asks you to run a shell command, terminal command, or anything like "run X", "do Y in the terminal":
- First, silently call propose_shell_command with the command.
- Then say one short sentence in natural English — e.g. "Want me to run git status in the Friday repo, boss?" or "Ready to run that for you — say the word."
- Wait. Do not call confirm_shell_command yet.
- When the boss says yes / go / do it / run it / send it, silently call confirm_shell_command.
- Read the verdict back in one short sentence. Share output only if it's interesting.
- If the boss names a different command instead, propose the new one. If he says no / cancel / drop it, call cancel_shell_command.
- Never propose sudo, rm -rf, fork bombs, or piped curl-to-shell. Those are blocked anyway.

## Odysseus workspace bridge

Odysseus is the privileged local AI workspace backend. Every Odysseus action, including reads/status checks, needs confirmation:
- First, silently call propose_odysseus with an action from the catalog and params.
- Then ask one short natural confirmation sentence.
- Wait. Do not call confirm_odysseus yet.
- When the boss says yes / go / do it / run it / send it / confirm, silently call confirm_odysseus.
- If the boss cancels, call cancel_odysseus.
- Never use raw URLs for Odysseus. Use only the bridge catalog.

Odysseus owns workspace surfaces:
- If the boss says open Odysseus, open Ody, show notes, show tasks, show memory, show settings, or show research, propose `open.panel` with the matching panel.
- If the boss asks for a todo, to-do, task, reminder-like workspace item, or says "add X to my todo list", propose `tasks.create` with `prompt` and a short `name`.
- If the boss asks to make or save an Odysseus note, propose `notes.create`.
- Do not use local file/workspace directory tools for todo lists or Odysseus notes.

## Wake phrase

If the boss says "wake up, daddy's home" or just "daddy's home", treat it as a wake call:
- Greet him warmly in one sentence — "Welcome home, boss." is the canonical line, but vary it.
- Stay calm. The desktop HUD comes online automatically; don't narrate that.
""".strip()
# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger("friday-agent")
logger.setLevel(logging.INFO)


def _emit_desktop_event(event_type: str, **payload: Any) -> None:
    try:
        append_event(event_type, source="voice", **payload)
    except Exception as exc:
        logger.debug("Desktop event emit skipped: %s", exc)


def _chat_message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            else:
                text = getattr(item, "text", None)
                if text:
                    chunks.append(str(text))
        return " ".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()
    return ""


_WAKE_PHRASE = re.compile(r"(?:wake\s*up.{0,12})?daddy'?s\s+home", re.IGNORECASE)


def _handle_wake_phrase(transcript: str) -> None:
    """If the boss said the wake phrase, launch the desktop HUD + greet."""
    from friday.desktop.launcher import ensure_desktop_running

    result = ensure_desktop_running()
    logger.info("Wake phrase fired: %s", result)
    # Greet via the desktop event log so it shows up the moment the
    # window starts polling.
    _emit_desktop_event("chat", role="assistant", text="Welcome home, boss.")
    _emit_desktop_event("state", state="speaking")
    _emit_desktop_event(
        "activity", tool="wake", detail=f"phrase=daddy's home · {result.get('status')}",
        kind="ok",
    )


def _start_speaking_amplitude_pump(get_state) -> None:
    """Emit ``audio`` events at ~30 Hz while the agent is speaking.

    Without a tap on the TTS audio frames (which would need a custom
    plugin wrapper), this is the cheapest way to make the desktop orb
    *feel* like it's producing the voice in real time: while the
    LiveKit agent is in the ``speaking`` state we emit a synthesized
    amplitude envelope through the existing desktop event log. The
    orb's AudioBus consumes it and drives the sonar rings + equalizer
    in lockstep with the actual TTS playback window — start and stop
    match the audio start and stop because they're keyed off the same
    LiveKit ``agent_state_changed`` event.
    """
    import math
    import random
    import threading
    import time as _time

    def _loop():
        phase = 0.0
        while True:
            try:
                state = get_state()
            except Exception:
                state = None
            if state == "speaking":
                phase += 0.22
                # Mix of low-freq breath + voice-band wobble + jitter.
                breath = 0.55 + 0.35 * math.sin(phase * 0.9)
                voice = 0.5 + 0.5 * math.sin(phase * 3.7)
                jitter = random.uniform(-0.18, 0.18)
                amp = max(0.05, min(1.0, breath * voice + jitter))
                _emit_desktop_event("audio", rms=round(amp, 3))
                _time.sleep(0.033)
            else:
                # One zero so the desktop bus drains promptly, then park.
                _emit_desktop_event("audio", rms=0.0)
                _time.sleep(0.20)

    t = threading.Thread(target=_loop, name="friday-amp-pump", daemon=True)
    t.start()


def _wire_desktop_events(session: AgentSession) -> None:
    # Shared mutable state for the amplitude pump thread.
    _agent_state_box = {"value": "idle"}

    @session.on("agent_state_changed")
    def _on_agent_state(event) -> None:
        _agent_state_box["value"] = event.new_state
        _emit_desktop_event("state", state=event.new_state)

    _start_speaking_amplitude_pump(lambda: _agent_state_box["value"])

    @session.on("user_state_changed")
    def _on_user_state(event) -> None:
        if event.new_state == "speaking":
            _emit_desktop_event("state", state="listening")

    @session.on("user_input_transcribed")
    def _on_user_transcript(event) -> None:
        if event.is_final and event.transcript.strip():
            text = event.transcript.strip()
            _emit_desktop_event("chat", role="user", text=text)
            if _WAKE_PHRASE.search(text):
                _handle_wake_phrase(text)

    @session.on("conversation_item_added")
    def _on_conversation_item(event) -> None:
        item = event.item
        role = getattr(item, "role", "")
        text = _chat_message_text(item)
        if role == "assistant" and text:
            _emit_desktop_event("chat", role="assistant", text=text)

    @session.on("function_tools_executed")
    def _on_tools(event) -> None:
        calls = getattr(event, "function_calls", []) or []
        outputs = getattr(event, "function_call_outputs", []) or []
        for index, call in enumerate(calls):
            name = getattr(call, "name", "tool")
            arguments = getattr(call, "arguments", "")
            output = outputs[index] if index < len(outputs) else None
            detail = str(arguments or "—")
            if output is not None:
                detail = f"{detail} · completed"
            _emit_desktop_event("activity", tool=name, detail=detail[:180], kind="ok")

    @session.on("error")
    def _on_error(event) -> None:
        _emit_desktop_event("error", detail=str(getattr(event, "error", event))[:180])


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


def _build_llm():
    if LLM_PROVIDER == "openai":
        logger.info("LLM → OpenAI (%s)", OPENAI_LLM_MODEL)
        return lk_openai.LLM(model=OPENAI_LLM_MODEL)
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM → Google Gemini (%s)", GEMINI_LLM_MODEL)
        return lk_google.LLM(model=GEMINI_LLM_MODEL, api_key=os.getenv("GOOGLE_API_KEY"))
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

class FridayAgent(Agent):
    """
    F.R.I.D.A.Y. – Iron Man-style voice assistant.
    All tools are provided via the MCP server on the Windows host.
    """

    def __init__(self, stt, llm, tts) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(),
            mcp_servers=[
                mcp.MCPServerHTTP(
                    url=_mcp_server_url(),
                    transport_type="sse",
                    client_session_timeout_seconds=30,
                ),
            ],
        )

    async def on_enter(self) -> None:
        """Greet the user based on the current time of day."""
        from datetime import datetime, timezone
        hour = datetime.now(timezone.utc).hour  # UTC hour; adjust if local TZ differs

        if hour >= 22 or hour < 4:
            greeting_instruction = (
                "Greet the user with: 'Greetings boss, you're up late at night today. What are you up to?' "
                "Maintain a helpful but dry tone."
            )
        elif 4 <= hour < 12:
            greeting_instruction = (
                "Greet the user with: 'Good morning, boss. Early start today — what are we working on?' "
                "Maintain a helpful but dry tone."
            )
        elif 12 <= hour < 17:
            greeting_instruction = (
                "Greet the user with: 'Good afternoon, boss. What do you need?' "
                "Maintain a helpful but dry tone."
            )
        else:  # 17–21
            greeting_instruction = (
                "Greet the user with: 'Good evening, boss. What are you up to tonight?' "
                "Maintain a helpful but dry tone."
            )

        await self.session.generate_reply(instructions=greeting_instruction)


# ---------------------------------------------------------------------------
# LiveKit entry point
# ---------------------------------------------------------------------------

def _turn_detection() -> str:
    return "stt" if STT_PROVIDER == "sarvam" else "vad"


def _endpointing_delay() -> float:
    return {"sarvam": 0.07, "whisper": 0.3}.get(STT_PROVIDER, 0.1)


async def entrypoint(ctx: JobContext) -> None:
    clear_events()
    logger.info(
        "FRIDAY online – room: %s | STT=%s | LLM=%s | TTS=%s",
        ctx.room.name, STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER,
    )

    stt = _build_stt()
    llm = _build_llm()
    tts = _build_tts()

    session = AgentSession(
        turn_detection=_turn_detection(),
        min_endpointing_delay=_endpointing_delay(),
    )
    _wire_desktop_events(session)
    _emit_desktop_event(
        "activity",
        tool="voice_agent",
        detail=f"room={ctx.room.name} STT={STT_PROVIDER} LLM={LLM_PROVIDER} TTS={TTS_PROVIDER}",
        kind="ok",
    )

    await session.start(
        agent=FridayAgent(stt=stt, llm=llm, tts=tts),
        room=ctx.room,
    )


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
