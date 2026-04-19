"""
Mail tools — Gmail API (cross-platform; Desktop/jarvis mail_access.py is
AppleScript-only). Lazy imports keep the server bootable without the extra.
"""

import asyncio
import base64
import os
from email.message import EmailMessage
from typing import Any

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _gmail_service() -> Any | None:
    creds_path = os.getenv("GMAIL_CREDENTIALS_JSON", "")
    token_path = os.getenv("GMAIL_TOKEN_JSON", "friday_gmail_token.json")
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
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _list_recent_sync(n: int) -> list[dict[str, Any]]:
    service = _gmail_service()
    if not service:
        return []
    resp = service.users().messages().list(
        userId="me", maxResults=n, labelIds=["INBOX", "UNREAD"]
    ).execute()
    msg_ids = [m["id"] for m in resp.get("messages", [])]
    out = []
    for mid in msg_ids:
        m = service.users().messages().get(userId="me", id=mid, format="metadata",
                                           metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
        out.append({
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "snippet": m.get("snippet", "")[:180],
        })
    return out


def _send_sync(to: str, subject: str, body: str) -> bool:
    service = _gmail_service()
    if not service:
        return False
    msg = EmailMessage()
    msg.set_content(body)
    msg["To"] = to
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return True


def register(mcp):

    @mcp.tool()
    async def check_mail(limit: int = 5) -> str:
        """List the N most recent unread inbox emails (default 5)."""
        msgs = await asyncio.to_thread(_list_recent_sync, max(1, min(int(limit), 20)))
        if not msgs:
            if not os.getenv("GMAIL_CREDENTIALS_JSON"):
                return "Mail not configured, boss — set GMAIL_CREDENTIALS_JSON."
            return "Inbox zero, boss."
        lines = [f"Unread mail ({len(msgs)}):"]
        for m in msgs:
            lines.append(f"  • {m['from']} — {m['subject']}")
            if m["snippet"]:
                lines.append(f"    {m['snippet']}")
        return "\n".join(lines)

    @mcp.tool()
    async def send_mail(to: str, subject: str, body: str) -> str:
        """Send an email via the user's Gmail account."""
        ok = await asyncio.to_thread(_send_sync, to, subject, body)
        return f"Email sent to {to}." if ok else "Mail send failed — check GMAIL_CREDENTIALS_JSON."
