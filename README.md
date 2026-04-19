# F.R.I.D.A.Y. — Tony Stark Demo

> *"Fully Responsive Intelligent Digital Assistant for You"*

A Tony-Stark-inspired personal AI, split into two cooperating processes:

| Component | What it is |
|-----------|-----------|
| **MCP Server** (`uv run friday`) | A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes ten tool groups (news, finance, weather, search, notify, calendar, mail, memory, system, utils) over the current **Streamable HTTP** transport. |
| **Voice Agent** (`uv run friday_voice`) | A [LiveKit Agents 1.6+](https://github.com/livekit/agents) voice loop. Runs in **pipeline** (STT → LLM → TTS), **realtime_gemini**, or **realtime_openai** modes — all three see the same MCP tool set. |

Demo: [Instagram reel](https://www.instagram.com/p/DW2HjYtkwg_/)

[![Demo Video Guide](https://img.youtube.com/vi/mMY9swqe3BI/maxresdefault.jpg)](https://www.youtube.com/watch?v=mMY9swqe3BI)

---

## How it works

```
Microphone ──► [pipeline]  STT → LLM → TTS
           └─► [realtime]  speech-to-speech (Gemini Live / GPT Realtime)
                                 │
                                 ▼
                          MCP Server (FastMCP, Streamable HTTP :8000/mcp)
                                 ├─ search_web, fetch_url
                                 ├─ get_world_news, get_news_by_topic
                                 ├─ get_stock_quote, get_crypto_price
                                 ├─ get_weather, get_forecast
                                 ├─ notify_user, send_morning_briefing
                                 ├─ check_mail, send_mail
                                 ├─ get_todays_events, get_upcoming_events
                                 ├─ remember_fact, recall, forget
                                 └─ get_current_time, get_system_info, …
```

The voice agent connects to the MCP server at `http://127.0.0.1:8000/mcp`
(auto-resolved to the Windows host IP when running inside WSL).

---

## Project structure

```
friday-tony-stark-demo/
├── server.py             # uv run friday  → FastMCP server (streamable-http :8000)
├── agent_friday.py       # uv run friday_voice → LiveKit voice agent
├── pyproject.toml
├── .env.example          # copy → .env and fill in your keys
│
└── friday/               # MCP server package
    ├── config.py         # env-var loading & app-wide settings
    ├── tools/            # MCP tools (callable by the LLM)
    │   ├── web.py        # search_web, fetch_url, open_world_monitor
    │   ├── news.py       # get_world_news, get_news_by_topic, get_trending_events
    │   ├── finance.py    # get_stock_quote, get_market_overview, get_crypto_price
    │   ├── weather.py    # get_weather, get_forecast
    │   ├── notify.py     # notify_user, send_morning_briefing
    │   ├── calendar.py   # get_todays_events, get_upcoming_events
    │   ├── mail.py       # check_mail, send_mail
    │   ├── memory.py     # remember_fact, remember_event, recall, forget
    │   ├── system.py     # get_current_time, get_system_info
    │   └── utils.py      # format_json, word_count
    ├── prompts/          # MCP prompt templates (summarize, explain_code, …)
    └── resources/        # MCP resources (friday://info)
```

---

## Quick start

### 1. Prerequisites

- Python ≥ 3.11
- [`uv`](https://github.com/astral-sh/uv) — `pip install uv` or `curl -Lsf https://astral.sh/uv/install.sh | sh`
- A [LiveKit Cloud](https://cloud.livekit.io) project (free tier works)

### 2. Clone & install

```bash
git clone https://github.com/SAGAR-TAMANG/friday-tony-stark-demo.git
cd friday-tony-stark-demo
uv sync
```

### 3. Set up environment

```bash
cp .env.example .env
# Open .env and fill in your API keys — most tools have keyless defaults.
```

### 4. Run — two terminals

**Terminal 1 — MCP server** (must start first)

```bash
uv run friday
# [Friday] MCP server starting | transport=streamable-http  →  :8000/mcp
```

**Terminal 2 — Voice agent**

```bash
uv run friday_voice
```

Joins a LiveKit room. Open the
[LiveKit Agents Playground](https://agents-playground.livekit.io) and
connect to hear FRIDAY greet you.

---

## Voice modes

| `VOICE_MODE` | Pipeline | Latency | When to use |
|---|---|---|---|
| `pipeline` *(default)* | STT → LLM → TTS | ~1.5 s | Robust; most providers supported. |
| `realtime_gemini` | Gemini Live speech-to-speech | ~300 ms | Snappy conversation. |
| `realtime_openai` | OpenAI `gpt-realtime` | ~300 ms | Snappy; English-optimised. |

Switch modes with the `VOICE_MODE` env var — no code changes.

If `livekit-plugins-noise-cancellation` is installed, **BVC** denoising is
wired up automatically. If `livekit-plugins-turn-detector` is installed,
the semantic `MultilingualModel` replaces the VAD/STT turn heuristic.
Both are optional.

---

## Example prompts

- "Brief me." → `get_world_news` → automatic `open_world_monitor`.
- "What's Tesla doing?" → `get_stock_quote("TSLA")` *(real price, no hallucination)*.
- "Bitcoin?" → `get_crypto_price("BTC")`.
- "Weather in Mumbai?" → `get_weather("Mumbai")` via Open-Meteo.
- "Search for latest Anthropic news." → `search_web` via Tavily → Brave → DuckDuckGo.
- "What's on my schedule?" → `get_todays_events` (needs `GOOGLE_CALENDAR_CREDENTIALS_JSON`).
- "Any unread mail?" → `check_mail` (needs `GMAIL_CREDENTIALS_JSON`).
- "Remember I like black coffee." → `remember_fact`.
- "Ping my phone." → `notify_user` via Telegram.

---

## Environment variables

Full list in [`.env.example`](.env.example). Highlights:

| Variable | Required | Notes |
|---|---|---|
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | ✅ | From LiveKit Cloud dashboard. |
| `OPENAI_API_KEY` | ✅ (default TTS & realtime_openai) | platform.openai.com/api-keys |
| `GOOGLE_API_KEY` | ✅ (default LLM & realtime_gemini) | aistudio.google.com |
| `SARVAM_API_KEY` | ✅ (default STT) | dashboard.sarvam.ai |
| `MCP_TRANSPORT` | — | `streamable-http` (default) or legacy `sse`. |
| `VOICE_MODE` | — | `pipeline` \| `realtime_gemini` \| `realtime_openai`. |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | — | Upgrade `search_web` beyond DuckDuckGo. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | Enable `notify_user`. |
| `GMAIL_CREDENTIALS_JSON` / `GOOGLE_CALENDAR_CREDENTIALS_JSON` | — | Enable mail + calendar tools. |
| `FINNHUB_API_KEY` / `OPENWEATHERMAP_API_KEY` / `NEWSAPI_KEY` | — | Premium fallbacks; keyless defaults work fine. |

---

## Switching providers

Open `agent_friday.py` (or set env vars) and change:

```python
STT_PROVIDER = "sarvam"    # sarvam | openai | whisper
LLM_PROVIDER = "gemini"    # gemini | openai
TTS_PROVIDER = "openai"    # openai | sarvam
VOICE_MODE   = "pipeline"  # pipeline | realtime_gemini | realtime_openai
```

---

## Adding a new tool

1. Create or open a file in `friday/tools/`.
2. Define a `register(mcp)` function and decorate tools with `@mcp.tool()`.
3. Import the module and call `register(mcp)` in `friday/tools/__init__.py`.

The MCP server picks it up on next start.

---

## Tech stack

- **[FastMCP](https://github.com/jlowin/fastmcp)** (Streamable HTTP) — MCP server.
- **[LiveKit Agents 1.6+](https://github.com/livekit/agents)** — voice pipeline + realtime.
- **Sarvam Saaras v3** / **OpenAI `gpt-4o-transcribe`** — STT.
- **Google Gemini 2.5 Pro** / **OpenAI `gpt-4.1`** — LLM.
- **OpenAI `gpt-4o-mini-tts`** (steerable) / **Sarvam Bulbul v3** — TTS.
- **Realtime**: **Gemini Live** & **OpenAI `gpt-realtime`**.
- **Data backends**: GDELT 2.0, yfinance, CoinGecko, Open-Meteo, Telegram, Gmail, Google Calendar, Tavily/Brave/DuckDuckGo.

---

## License

MIT
