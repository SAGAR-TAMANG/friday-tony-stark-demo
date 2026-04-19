"""
Calendar tools — Google Calendar (cross-platform; AppleScript version from
Desktop/jarvis/calendar_access.py is macOS-only and not portable).

Lazy-imports google-api-python-client so the server boots even when the
optional `calendar` extra is not installed.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _load_service() -> Any | None:
    creds_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
    token_path = os.getenv("GOOGLE_CALENDAR_TOKEN_JSON", "friday_calendar_token.json")
    if not creds_path or not os.path.exists(creds_path):
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _list_events_sync(hours: int) -> list[dict[str, Any]]:
    service = _load_service()
    if not service:
        return []
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)
    resp = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=cutoff.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=20,
    ).execute()
    return resp.get("items", [])


def _format_event(e: dict[str, Any]) -> str:
    start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "")
    title = e.get("summary", "(no title)")
    location = e.get("location", "")
    # Trim ISO string for voice friendliness.
    when = start.replace("T", " ")[:16] if start else "?"
    tail = f" @ {location}" if location else ""
    return f"[{when}] {title}{tail}"


def register(mcp):

    @mcp.tool()
    async def get_todays_events() -> str:
        """Today's remaining calendar events from the user's primary Google Calendar."""
        events = await asyncio.to_thread(_list_events_sync, 24)
        if not events:
            if not os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON"):
                return "Calendar not configured, boss — set GOOGLE_CALENDAR_CREDENTIALS_JSON."
            return "Your calendar's clear for today, boss."
        lines = ["Today's schedule:"] + [f"  {_format_event(e)}" for e in events[:10]]
        return "\n".join(lines)

    @mcp.tool()
    async def get_upcoming_events(hours: int = 4) -> str:
        """Events in the next N hours (default 4)."""
        events = await asyncio.to_thread(_list_events_sync, max(1, min(int(hours), 168)))
        if not events:
            return f"Nothing on the books for the next {hours} hours, boss."
        lines = [f"Upcoming ({hours}h):"] + [f"  {_format_event(e)}" for e in events[:10]]
        return "\n".join(lines)
