"""
Notification tools — push messages to the user's phone/desktop.
Currently supports Telegram (adapted from Desktop/jarvis/telegram_notify.py).
"""

import os

import httpx

PRIORITY_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}


def _telegram_creds() -> tuple[str, str]:
    return os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")


async def _send_telegram(text: str) -> bool:
    token, chat_id = _telegram_creds()
    if not token or not chat_id:
        return False
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    return r.status_code == 200


def register(mcp):

    @mcp.tool()
    async def notify_user(title: str, priority: str = "medium", body: str = "") -> str:
        """
        Send a push notification to the user (currently Telegram).
        Priority: 'critical' | 'high' | 'medium' | 'low'.
        """
        emoji = PRIORITY_EMOJI.get(priority.lower(), "🔵")
        msg = f"{emoji} {title}"
        if body:
            msg += f"\n\n{body}"
        ok = await _send_telegram(msg)
        if not ok:
            token, _ = _telegram_creds()
            if not token:
                return "Notification channel not configured, boss — add TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID."
            return "Notification failed, boss."
        return f"Notification sent: {title}"

    @mcp.tool()
    async def send_morning_briefing(summary: str) -> str:
        """Push a formatted morning briefing (summary of tasks, calendar, weather)."""
        msg = f"☀️ Morning Briefing\n\n{summary}"
        ok = await _send_telegram(msg)
        return "Briefing sent." if ok else "Briefing failed — check Telegram config."
