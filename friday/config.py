"""
Configuration — load environment variables and app-wide settings.
Every tool reads its own key lazily, but this class is the canonical list.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SERVER_NAME: str = os.getenv("SERVER_NAME", "Friday")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # MCP transport — "streamable-http" (default) or legacy "sse".
    MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "streamable-http")
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8000"))
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "127.0.0.1")

    # Voice mode — "pipeline" | "realtime_gemini" | "realtime_openai".
    VOICE_MODE: str = os.getenv("VOICE_MODE", "pipeline")

    # Provider keys (pipeline voice stack).
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")

    # Web search fallback chain.
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")

    # News (all optional; GDELT + public RSS work keyless).
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")

    # Finance (optional premium fallback; yfinance + CoinGecko are keyless).
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")

    # Weather (optional; Open-Meteo works keyless).
    OPENWEATHERMAP_API_KEY: str = os.getenv("OPENWEATHERMAP_API_KEY", "")

    # Push notifications.
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Google OAuth (calendar + mail share the same client-secret pattern).
    GMAIL_CREDENTIALS_JSON: str = os.getenv("GMAIL_CREDENTIALS_JSON", "")
    GMAIL_TOKEN_JSON: str = os.getenv("GMAIL_TOKEN_JSON", "friday_gmail_token.json")
    GOOGLE_CALENDAR_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
    GOOGLE_CALENDAR_TOKEN_JSON: str = os.getenv(
        "GOOGLE_CALENDAR_TOKEN_JSON", "friday_calendar_token.json"
    )

    # Persistent memory file.
    FRIDAY_MEMORY_PATH: str = os.getenv(
        "FRIDAY_MEMORY_PATH", os.path.expanduser("~/.friday/memory.json")
    )

    # FRIDAY home directory for all data
    FRIDAY_HOME: str = os.getenv("FRIDAY_HOME", os.path.expanduser("~/.friday"))

    # SQLite databases
    FRIDAY_DB_PATH: str = os.getenv("FRIDAY_DB_PATH", os.path.expanduser("~/.friday/databases"))

    # Security settings
    SHELL_EXEC_ENABLED: bool = os.getenv("SHELL_EXEC_ENABLED", "true").lower() == "true"
    SHELL_BLOCKED_COMMANDS: str = os.getenv("SHELL_BLOCKED_COMMANDS", "rm -rf /,rm -rf /*,dd if=/dev/zero")

    # A2A Protocol settings
    A2A_ENABLED: bool = os.getenv("A2A_ENABLED", "false").lower() == "true"
    A2A_PORT: int = int(os.getenv("A2A_PORT", "8001"))

    # File-tool sandbox root (defaults to FRIDAY_HOME).
    FRIDAY_FILE_ROOT: str = os.getenv(
        "FRIDAY_FILE_ROOT", os.getenv("FRIDAY_HOME", os.path.expanduser("~/.friday"))
    )

    # Code-runner gate — off by default; opt-in only.
    CODE_EXEC_ENABLED: bool = os.getenv("CODE_EXEC_ENABLED", "false").lower() == "true"

    # DB tool writes — read-only by default.
    DB_WRITE_ENABLED: bool = os.getenv("DB_WRITE_ENABLED", "false").lower() == "true"

    # Orchestrator model selection (planner + executor split for cost/latency tuning).
    PLANNER_MODEL: str = os.getenv("PLANNER_MODEL", "gemini-2.5-pro")
    EXECUTOR_MODEL: str = os.getenv("EXECUTOR_MODEL", "gemini-2.5-flash")

    # Memory backend — "json" (default, no deps) | "faiss" | "chroma".
    MEMORY_BACKEND: str = os.getenv("MEMORY_BACKEND", "json")

    # Voice-agent opt-in: route through orchestrator instead of direct LLM.
    USE_ORCHESTRATOR: bool = os.getenv("USE_ORCHESTRATOR", "false").lower() == "true"


config = Config()
