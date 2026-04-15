"""
F.R.I.D.A.Y. -- project status & quick-start helper.

Usage:
  python main.py           # print project status
  python main.py server    # alias: start the MCP server
  python main.py voice     # alias: start the voice agent
"""

import sys
import subprocess


_BANNER = r"""
  _____  _____  _____  _____    _    __   __
 |  ___||  _  ||_   _||  _  |  / \  \ \ / /
 | |_   | |_| |  | |  | | | | / _ \  \ V /
 |  _|  |    /   | |  | |_| |/ ___ \  | |
 |_|    |_|\_\   |_|  |_____/_/   \_\ |_|

 Fully Responsive Intelligent Digital Assistant for You
"""

_STATUS = """
 COMPONENTS
 --------------------------------------
  MCP Server  :  uv run friday          (SSE on :8000)
  Voice Agent :  uv run friday_voice    (LiveKit dev mode)

 TOOLS ONLINE
 --------------------------------------
  web       get_world_news, search_web, fetch_url, open_world_monitor
  system    get_current_time, get_system_info, get_system_diagnostics
  weather   get_weather
  finance   get_stock_price, get_market_overview
  tickets   create_ticket, list_tickets
  reminders add_reminder, list_reminders, clear_reminders
  utils     calculate, format_json, word_count

 QUICK START
 --------------------------------------
  1. cp .env.example .env  ->  fill in API keys
  2. uv sync               ->  install deps
  3. uv run friday         ->  start MCP server  (terminal 1)
  4. uv run friday_voice   ->  start voice agent (terminal 2)
  5. Open https://agents-playground.livekit.io and connect
"""


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        pass


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "server":
        _run(["uv", "run", "friday"])
    elif arg == "voice":
        _run(["uv", "run", "friday_voice"])
    else:
        print(_BANNER)
        print(_STATUS)


if __name__ == "__main__":
    main()
