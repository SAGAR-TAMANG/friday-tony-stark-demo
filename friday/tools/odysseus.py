"""Odysseus admin bridge tools with explicit propose / confirm gating."""

from __future__ import annotations

import os
import time
import uuid
import webbrowser
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from friday.desktop import events


load_dotenv()

PENDING_TTL_SECONDS = 180
DEFAULT_TIMEOUT_S = 20.0
MAX_RESULT_CHARS = 6000
PENDING_ODYSSEUS_ACTIONS: dict[str, "PendingOdysseusAction"] = {}


@dataclass(frozen=True)
class ActionSpec:
    name: str
    method: str
    path: str
    risk: str
    description: str
    payload: str = "json"  # json | form | query | none | browser
    required: tuple[str, ...] = ()


@dataclass
class PendingOdysseusAction:
    action_id: str
    action: str
    params: dict[str, Any]
    reason: str
    summary: str
    target: str
    risk: str
    created_at: float


ACTION_CATALOG: dict[str, ActionSpec] = {
    "health.status": ActionSpec("health.status", "GET", "/api/health", "read", "Check Odysseus liveness.", "none"),
    "ready.status": ActionSpec("ready.status", "GET", "/api/ready", "read", "Check Odysseus readiness.", "none"),
    "runtime.status": ActionSpec("runtime.status", "GET", "/api/runtime", "read", "Read Odysseus runtime details.", "none"),
    "version.status": ActionSpec("version.status", "GET", "/api/version", "read", "Read Odysseus version.", "none"),
    "models.list": ActionSpec("models.list", "GET", "/api/models", "read", "List available Odysseus models.", "none"),
    "providers.status": ActionSpec("providers.status", "GET", "/api/providers", "admin_read", "Read provider/admin status.", "none"),
    "search.providers": ActionSpec("search.providers", "GET", "/api/search/providers", "read", "List search providers.", "none"),
    "search.web": ActionSpec("search.web", "POST", "/api/search", "external_read", "Run Odysseus web search.", "json", ("query",)),
    "chat.ask": ActionSpec("chat.ask", "POST", "/api/chat", "llm", "Ask Odysseus chat.", "json", ("message",)),
    "memory.list": ActionSpec("memory.list", "GET", "/api/memory", "read", "List Odysseus memories.", "none"),
    "memory.search": ActionSpec("memory.search", "POST", "/api/memory/search", "read", "Search Odysseus memory.", "form", ("query",)),
    "memory.add": ActionSpec("memory.add", "POST", "/api/memory/add", "write", "Add Odysseus memory.", "json", ("text",)),
    "notes.list": ActionSpec("notes.list", "GET", "/api/notes", "read", "List Odysseus notes.", "query"),
    "notes.create": ActionSpec("notes.create", "POST", "/api/notes", "write", "Create Odysseus note.", "json", ("title",)),
    "notes.get": ActionSpec("notes.get", "GET", "/api/notes/{note_id}", "read", "Read Odysseus note.", "none", ("note_id",)),
    "notes.update": ActionSpec("notes.update", "PUT", "/api/notes/{note_id}", "write", "Update Odysseus note.", "json", ("note_id",)),
    "tasks.list": ActionSpec("tasks.list", "GET", "/api/tasks", "read", "List Odysseus tasks.", "query"),
    "tasks.create": ActionSpec("tasks.create", "POST", "/api/tasks", "write", "Create Odysseus task.", "json", ("prompt",)),
    "open.panel": ActionSpec("open.panel", "OPEN", "/{panel}", "local_ui", "Open an Odysseus panel.", "browser", ("panel",)),
}


def clear_pending_actions() -> None:
    PENDING_ODYSSEUS_ACTIONS.clear()


def _emit_activity(detail: str, kind: str = "info") -> None:
    try:
        events.append_event("activity", tool="odysseus", detail=detail[:240], kind=kind)
    except Exception:
        pass


def _base_url() -> str:
    raw = os.getenv("ODYSSEUS_BASE_URL", "http://127.0.0.1:7870").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("ODYSSEUS_BASE_URL must be http or https.")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Odysseus bridge only allows localhost targets.")
    return raw


def _bridge_token() -> str:
    token = os.getenv("ODYSSEUS_BRIDGE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("ODYSSEUS_BRIDGE_TOKEN is not configured.")
    return token


def _spec_for(action: str) -> ActionSpec:
    key = str(action or "").strip()
    spec = ACTION_CATALOG.get(key)
    if not spec:
        raise ValueError(f"Unsupported Odysseus action: {action}")
    return spec


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError("Odysseus action params must be an object.")
    return dict(params)


def _resolve_path(spec: ActionSpec, params: dict[str, Any]) -> str:
    for key in spec.required:
        if key not in params or params[key] in (None, ""):
            raise ValueError(f"Missing required Odysseus param: {key}")
    path = spec.path
    for key in tuple(params):
        token = "{" + key + "}"
        if token in path:
            path = path.replace(token, str(params[key]).strip())
    return path


def _target_for(spec: ActionSpec, params: dict[str, Any]) -> str:
    if spec.payload == "browser":
        return f"OPEN {_base_url()}{_resolve_path(spec, params)}"
    return f"{spec.method} {_resolve_path(spec, params)}"


def _prune_expired() -> None:
    now = time.time()
    expired = [
        action_id
        for action_id, action in PENDING_ODYSSEUS_ACTIONS.items()
        if now - action.created_at > PENDING_TTL_SECONDS
    ]
    for action_id in expired:
        PENDING_ODYSSEUS_ACTIONS.pop(action_id, None)


def _latest_pending_action_id() -> str:
    _prune_expired()
    if not PENDING_ODYSSEUS_ACTIONS:
        raise KeyError("No pending Odysseus action found.")
    return max(PENDING_ODYSSEUS_ACTIONS.values(), key=lambda action: action.created_at).action_id


def _truncate(value: Any) -> Any:
    text = str(value)
    if len(text) <= MAX_RESULT_CHARS:
        return value
    return text[:MAX_RESULT_CHARS] + f"\n...[truncated {len(text) - MAX_RESULT_CHARS} chars]"


def _request_params(spec: ActionSpec, params: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in params.items() if "{" + k + "}" not in spec.path}
    if spec.name == "tasks.create":
        payload.setdefault("trigger_type", "schedule")
        payload.setdefault("schedule", "once")
    return payload


def propose_odysseus_action(action: str, params: dict[str, Any] | None = None, reason: str = "") -> dict:
    """Stage an Odysseus action. This never calls Odysseus."""
    spec = _spec_for(action)
    clean = _clean_params(params)
    target = _target_for(spec, clean)
    action_id = uuid.uuid4().hex
    summary = f"{spec.description} Target: {target}"
    pending = PendingOdysseusAction(
        action_id=action_id,
        action=spec.name,
        params=clean,
        reason=str(reason or "").strip(),
        summary=summary,
        target=target,
        risk=spec.risk,
        created_at=time.time(),
    )
    PENDING_ODYSSEUS_ACTIONS[action_id] = pending
    _emit_activity(f"pending {spec.name} -> {target}", "info")
    return {
        "status": "pending_confirmation",
        "action_id": action_id,
        "action": spec.name,
        "risk": spec.risk,
        "target": target,
        "summary": summary,
        "reason": pending.reason,
        "expires_in_seconds": PENDING_TTL_SECONDS,
    }


def confirm_odysseus_action(action_id: str | None = None) -> dict:
    """Execute the newest pending Odysseus action, or a specific action id."""
    if not action_id:
        action_id = _latest_pending_action_id()
    pending = PENDING_ODYSSEUS_ACTIONS.get(action_id)
    if pending is None:
        raise KeyError(f"No pending Odysseus action found: {action_id}")
    if time.time() - pending.created_at > PENDING_TTL_SECONDS:
        PENDING_ODYSSEUS_ACTIONS.pop(action_id, None)
        raise TimeoutError(f"Pending Odysseus action expired: {action_id}")

    spec = _spec_for(pending.action)
    try:
        result = _execute_odysseus_action(spec, pending.params)
    except Exception as exc:
        PENDING_ODYSSEUS_ACTIONS.pop(action_id, None)
        _emit_activity(f"error {pending.action}: {exc}", "err")
        return {
            "status": "error",
            "action_id": action_id,
            "action": pending.action,
            "target": pending.target,
            "error": str(exc),
        }

    PENDING_ODYSSEUS_ACTIONS.pop(action_id, None)
    _emit_activity(f"executed {pending.action} -> {pending.target}", "ok")
    return {
        "status": "executed",
        "action_id": action_id,
        "action": pending.action,
        "target": pending.target,
        "summary": pending.summary,
        "result": _truncate(result),
    }


def cancel_odysseus_action(action_id: str | None = None) -> dict:
    if not action_id:
        try:
            action_id = _latest_pending_action_id()
        except KeyError:
            return {"status": "noop", "reason": "no pending Odysseus action"}
    removed = PENDING_ODYSSEUS_ACTIONS.pop(action_id, None)
    if removed:
        _emit_activity(f"cancelled {removed.action}", "info")
    return {
        "status": "cancelled" if removed else "noop",
        "action_id": action_id,
    }


def _execute_odysseus_action(spec: ActionSpec, params: dict[str, Any]) -> Any:
    if spec.payload == "browser":
        panel = str(params.get("panel") or "home").strip().lower()
        events.append_event("odysseus_panel", panel=panel)
        return {"opened_in_hud": panel}
    return _send_odysseus_request(spec, params)


def _send_odysseus_request(spec: ActionSpec, params: dict[str, Any]) -> Any:
    path = _resolve_path(spec, params)
    url = _base_url() + path
    headers = {
        "Authorization": f"Bearer {_bridge_token()}",
        "X-Friday-Bridge": "1",
    }
    kwargs: dict[str, Any] = {"headers": headers, "timeout": DEFAULT_TIMEOUT_S}
    if spec.payload == "json":
        kwargs["json"] = _request_params(spec, params)
    elif spec.payload == "form":
        kwargs["data"] = _request_params(spec, params)
    elif spec.payload == "query":
        kwargs["params"] = params
    with httpx.Client() as client:
        response = client.request(spec.method, url, **kwargs)
    try:
        body = response.json()
    except Exception:
        body = response.text
    if response.status_code >= 400:
        raise RuntimeError(f"Odysseus returned HTTP {response.status_code}: {_truncate(body)}")
    return body


def register(mcp):
    @mcp.tool()
    def propose_odysseus(action: str, params: dict | None = None, reason: str = "") -> dict:
        """Stage an Odysseus action for explicit user confirmation. Never executes immediately."""
        return propose_odysseus_action(action=action, params=params, reason=reason)

    @mcp.tool()
    def confirm_odysseus(action_id: str | None = None) -> dict:
        """Execute the newest confirmed Odysseus action, or the action matching action_id."""
        return confirm_odysseus_action(action_id=action_id)

    @mcp.tool()
    def cancel_odysseus(action_id: str | None = None) -> dict:
        """Cancel a pending Odysseus proposal."""
        return cancel_odysseus_action(action_id=action_id)
