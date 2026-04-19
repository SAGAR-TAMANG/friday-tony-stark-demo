"""
Ticket tools — create and list tasks via Supabase REST API.
Gracefully no-ops when SUPABASE_URL / SUPABASE_API_KEY are not configured.
"""

import os
from datetime import datetime, timezone

import httpx


def _base_url() -> str:
    return os.getenv("SUPABASE_URL", "").rstrip("/")


def _headers() -> dict:
    key = os.getenv("SUPABASE_API_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _is_configured() -> bool:
    return bool(_base_url() and os.getenv("SUPABASE_API_KEY"))


def register(mcp):

    @mcp.tool()
    async def create_ticket(title: str, description: str = "", priority: str = "medium") -> str:
        """
        Log a new task or ticket into the Supabase ticketing system.
        Priority options: low | medium | high.
        Use when the boss asks to note something, create a task, or log an issue.
        """
        if not _is_configured():
            return "Ticketing system offline — Supabase credentials not set, sir."

        payload = {
            "title": title,
            "description": description,
            "priority": priority,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                f"{_base_url()}/tickets", json=payload, headers=_headers()
            )
            resp.raise_for_status()

        return f"Ticket logged: '{title}' — {priority} priority. On your list, boss."

    @mcp.tool()
    async def list_tickets(status: str = "open") -> str:
        """
        Retrieve tasks from the Supabase ticketing system.
        Status: open | closed | all.
        Use when the boss asks what's on the list, open tasks, or pending items.
        """
        if not _is_configured():
            return "Ticketing system offline — Supabase credentials not set, sir."

        params = {} if status == "all" else {"status": f"eq.{status}"}
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{_base_url()}/tickets", params=params, headers=_headers()
            )
            resp.raise_for_status()
            tickets = resp.json()

        if not tickets:
            return f"No {status} tickets, sir. Clean slate."

        lines = [f"### {status.upper()} TICKETS ({len(tickets)})"]
        for t in tickets[:10]:
            pri = t.get("priority", "?").upper()
            title = t.get("title", "Untitled")
            lines.append(f"- [{pri}] {title}")
        return "\n".join(lines)
