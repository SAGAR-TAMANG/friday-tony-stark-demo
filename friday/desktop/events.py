"""Shared JSONL event stream for the voice agent and desktop UI."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_EVENT_LOG = "/tmp/friday-desktop-events.jsonl"
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|token|password|secret|otp)\s*="),
)


@dataclass
class EventBatch:
    events: list[dict[str, Any]]
    offset: int


def event_log_path() -> Path:
    return Path(os.getenv("FRIDAY_DESKTOP_EVENT_LOG", DEFAULT_EVENT_LOG)).expanduser()


def _reject_secrets(value: Any) -> None:
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                raise ValueError("Refusing to write secret-like text to desktop event log.")
    elif isinstance(value, dict):
        for nested in value.values():
            _reject_secrets(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_secrets(nested)


def append_event(event_type: str, **payload: Any) -> dict[str, Any]:
    event = {
        "type": event_type,
        "ts": time.time(),
        "seq": time.time_ns(),
        **payload,
    }
    _reject_secrets(event)
    path = event_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def read_events_since(offset: int) -> EventBatch:
    path = event_log_path()
    if not path.exists():
        return EventBatch(events=[], offset=0)

    file_size = path.stat().st_size
    if offset > file_size:
        offset = 0

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        new_offset = handle.tell()
    return EventBatch(events=events, offset=new_offset)


def clear_events() -> None:
    path = event_log_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
