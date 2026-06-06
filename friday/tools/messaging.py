"""
Messaging tools with an explicit confirmation broker for risky sends.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
import webbrowser
from dataclasses import dataclass
from urllib.parse import quote

from dotenv import load_dotenv

from friday.tools.desktop import _reject_secret_content


load_dotenv()

PENDING_TTL_SECONDS = 600
SUPPORTED_CHANNELS = {"messages", "imessage", "sms", "whatsapp", "slack", "email", "mail"}
PENDING_ACTIONS: dict[str, "PendingAction"] = {}


@dataclass
class PendingAction:
    action_id: str
    summary: str
    risk: str
    created_at: float
    payload: dict


def clear_pending_actions() -> None:
    PENDING_ACTIONS.clear()


def _normalize_channel(channel: str) -> str:
    normalized = channel.strip().lower()
    if normalized not in SUPPORTED_CHANNELS:
        raise ValueError(f"Unsupported message channel: {channel}")
    if normalized in {"imessage", "sms"}:
        return "messages"
    if normalized == "mail":
        return "email"
    return normalized


def _validate_message(recipient: str, message: str) -> tuple[str, str]:
    clean_recipient = recipient.strip()
    clean_message = message.strip()
    if not clean_recipient:
        raise ValueError("Recipient is required.")
    if not clean_message:
        raise ValueError("Message is required.")
    _reject_secret_content(clean_recipient)
    _reject_secret_content(clean_message)
    return clean_recipient, clean_message


def _apple_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], check=True)


def _osascript_output(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _prune_expired() -> None:
    now = time.time()
    expired = [
        action_id
        for action_id, action in PENDING_ACTIONS.items()
        if now - action.created_at > PENDING_TTL_SECONDS
    ]
    for action_id in expired:
        PENDING_ACTIONS.pop(action_id, None)


def prepare_outbound_message(channel: str, recipient: str, message: str) -> dict:
    normalized_channel = _normalize_channel(channel)
    clean_recipient, clean_message = _validate_message(recipient, message)
    action_id = uuid.uuid4().hex
    summary = f"Send {normalized_channel} message to {clean_recipient}: {clean_message}"
    action = PendingAction(
        action_id=action_id,
        summary=summary,
        risk="send_message",
        created_at=time.time(),
        payload={
            "channel": normalized_channel,
            "recipient": clean_recipient,
            "message": clean_message,
        },
    )
    PENDING_ACTIONS[action_id] = action
    return {
        "status": "pending_confirmation",
        "action_id": action_id,
        "risk": action.risk,
        "summary": summary,
        "expires_in_seconds": PENDING_TTL_SECONDS,
    }


def _latest_pending_action_id() -> str:
    _prune_expired()
    if not PENDING_ACTIONS:
        raise KeyError("No pending message action found.")
    return max(PENDING_ACTIONS.values(), key=lambda action: action.created_at).action_id


def confirm_pending_action(action_id: str | None = None) -> dict:
    if not action_id:
        action_id = _latest_pending_action_id()

    action = PENDING_ACTIONS.get(action_id)
    if action is None:
        raise KeyError(f"No pending action found: {action_id}")

    if time.time() - action.created_at > PENDING_TTL_SECONDS:
        PENDING_ACTIONS.pop(action_id, None)
        raise TimeoutError(f"Pending action expired: {action_id}")

    _prune_expired()
    result = _execute_message_action(action.payload)
    PENDING_ACTIONS.pop(action_id, None)
    return {
        "status": "executed",
        "action_id": action_id,
        "summary": action.summary,
        "result": result,
    }


def _execute_message_action(payload: dict) -> str:
    channel = payload["channel"]
    recipient = payload["recipient"]
    message = payload["message"]
    if channel == "messages":
        return _send_apple_message(recipient, message)
    if channel == "whatsapp":
        return _open_whatsapp_draft(recipient, message)
    if channel == "slack":
        return _open_slack_draft(recipient, message)
    if channel == "email":
        return _open_email_draft(recipient, message)
    raise ValueError(f"Unsupported message channel: {channel}")


def _looks_like_direct_handle(recipient: str) -> bool:
    return "@" in recipient or bool(_digits_and_plus(recipient))


def _lookup_contact_handle(recipient: str) -> str | None:
    script = f'''
tell application "Contacts"
    set targetName to "{_apple_string(recipient)}"
    set matches to every person whose name contains targetName
    if (count of matches) is 0 then return ""

    repeat with targetPerson in matches
        repeat with targetPhone in phones of targetPerson
            set phoneLabel to (label of targetPhone) as text
            set phoneValue to (value of targetPhone) as text
            if phoneLabel contains "mobile" or phoneLabel contains "iPhone" then return phoneValue
        end repeat
    end repeat

    repeat with targetPerson in matches
        if (count of phones of targetPerson) > 0 then return (value of item 1 of phones of targetPerson) as text
    end repeat

    repeat with targetPerson in matches
        if (count of emails of targetPerson) > 0 then return (value of item 1 of emails of targetPerson) as text
    end repeat

    return ""
end tell
'''
    try:
        handle = _osascript_output(script)
    except Exception:
        return None
    return handle.strip() or None


def _send_apple_message(recipient: str, message: str) -> str:
    handle = recipient
    if not _looks_like_direct_handle(recipient):
        handle = _lookup_contact_handle(recipient) or recipient
    return _send_messages_handle(handle, message)


def _send_messages_handle(recipient: str, message: str) -> str:
    errors = []
    for service_type, label in (("iMessage", "iMessage"), ("SMS", "SMS")):
        script = _messages_send_script(service_type, recipient, message)
        try:
            _osascript(script)
            return f"Sent through Apple Messages ({label})."
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    return _open_messages_draft(recipient, message, errors)


def _messages_send_script(service_type: str, recipient: str, message: str) -> str:
    script = f'''
tell application "Messages"
    set targetBuddy to "{_apple_string(recipient)}"
    set targetService to 1st service whose service type = {service_type}
    send "{_apple_string(message)}" to buddy targetBuddy of targetService
end tell
'''
    return script


def _open_messages_draft(recipient: str, message: str, errors: list[str]) -> str:
    url = f"sms:{quote(recipient, safe='+@')}&body={quote(message)}"
    webbrowser.open(url)
    error_text = "; ".join(errors)[:240]
    return (
        "Opened Messages draft because direct send failed. "
        "Review and press Send in Messages. "
        f"Direct-send error: {error_text}"
    )


def _digits_and_plus(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", value)
    return cleaned


def _open_whatsapp_draft(recipient: str, message: str) -> str:
    phone = _digits_and_plus(recipient)
    encoded = quote(message)
    if phone:
        url = f"whatsapp://send?phone={quote(phone)}&text={encoded}"
    else:
        url = f"whatsapp://send?text={encoded}"
    webbrowser.open(url)
    return "Opened WhatsApp draft. Review and send from WhatsApp."


def _open_slack_draft(recipient: str, message: str) -> str:
    query = quote(f"{recipient} {message}")
    webbrowser.open(f"slack://search/{query}")
    return "Opened Slack draft/search target. Review and send from Slack."


def _open_email_draft(recipient: str, message: str) -> str:
    subject = quote(os.getenv("FRIDAY_EMAIL_SUBJECT", "Message from FRIDAY"))
    body = quote(message)
    webbrowser.open(f"mailto:{quote(recipient)}?subject={subject}&body={body}")
    return "Opened email draft. Review and send from Mail."


def register(mcp):
    @mcp.tool()
    def prepare_message(channel: str, recipient: str, message: str) -> dict:
        """Prepare a message for confirmation. This never sends immediately."""
        return prepare_outbound_message(channel=channel, recipient=recipient, message=message)

    @mcp.tool()
    def confirm_message_action(action_id: str | None = None) -> dict:
        """Execute a previously prepared message after explicit confirmation. If action_id is omitted, executes the newest pending message."""
        return confirm_pending_action(action_id=action_id)
