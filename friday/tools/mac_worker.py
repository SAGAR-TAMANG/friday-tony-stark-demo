"""
Mac worker tools for screen understanding and guarded desktop automation.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

DEFAULT_SCREENSHOT_DIR = "/tmp/friday-screens"
DEFAULT_VISION_MODEL = "gpt-4o"
CONFIRMATION_REQUIRED = "FRIDAY requires explicit confirmation before this action."
SAFE_KEY_ALIASES = {
    "return": "return",
    "enter": "return",
    "escape": "escape",
    "esc": "escape",
    "tab": "tab",
    "space": "space",
    "delete": "delete",
    "backspace": "delete",
}
SUPPORTED_MODIFIERS = {
    "cmd": "command down",
    "command": "command down",
    "shift": "shift down",
    "option": "option down",
    "alt": "option down",
    "control": "control down",
    "ctrl": "control down",
}
ALLOWED_COMBOS = {
    "cmd+l",
    "cmd+t",
    "cmd+w",
    "cmd+r",
    "cmd+c",
    "cmd+v",
    "cmd+a",
    "cmd+tab",
    "return",
    "enter",
    "escape",
    "esc",
    "tab",
    "space",
    "delete",
    "backspace",
}


def _require_confirmation(confirm: bool) -> None:
    required = os.getenv("FRIDAY_REQUIRE_CONFIRMATION", "true").lower() != "false"
    if required and not confirm:
        raise PermissionError(CONFIRMATION_REQUIRED)


def _safe_app_name(app_name: str) -> str:
    cleaned = app_name.strip()
    if not cleaned:
        raise ValueError("App name is required.")
    if any(char in cleaned for char in "\n\r\x00"):
        raise ValueError("App name contains invalid characters.")
    return cleaned


def _osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], check=True)


def _apple_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _screenshot_dir() -> Path:
    raw = os.getenv("FRIDAY_SCREENSHOT_DIR", DEFAULT_SCREENSHOT_DIR)
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _vision_model() -> str:
    return os.getenv("OPENAI_VISION_MODEL", DEFAULT_VISION_MODEL)


def open_application(app_name: str) -> str:
    app = _safe_app_name(app_name)
    subprocess.run(["open", "-a", app], check=True)
    return f"Opened {app}."


def focus_application(app_name: str) -> str:
    app = _safe_app_name(app_name)
    _osascript(f'tell application "{_apple_string(app)}" to activate')
    return f"Focused {app}."


def capture_screen_file() -> str:
    target = _screenshot_dir() / f"screen-{int(time.time() * 1000)}.png"
    subprocess.run(["screencapture", "-x", str(target)], check=True)
    return str(target)


def _image_data_url(path: str) -> str:
    data = Path(path).read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def describe_current_screen(prompt: str | None = None, client: OpenAI | None = None) -> dict:
    screenshot_path = capture_screen_file()
    request = prompt or (
        "Describe what is visible on this Mac screen. Identify active app, visible text, "
        "important UI controls, and next useful actions. Do not guess private secrets."
    )
    active_client = client or OpenAI()
    response = active_client.responses.create(
        model=_vision_model(),
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": request},
                {"type": "input_image", "image_url": _image_data_url(screenshot_path)},
            ],
        }],
    )
    return {
        "screenshot_path": screenshot_path,
        "description": response.output_text,
    }


def click_screen_point(x: int, y: int, confirm: bool = False) -> str:
    _require_confirmation(confirm)
    if x < 0 or y < 0:
        raise ValueError("Coordinates must be non-negative.")
    _osascript(f'tell application "System Events" to click at {{{int(x)}, {int(y)}}}')
    return f"Clicked screen point {int(x)}, {int(y)}."


def type_into_focused_app(text: str, confirm: bool = False) -> str:
    _require_confirmation(confirm)
    if not text:
        raise ValueError("Text is required.")
    _osascript(f'tell application "System Events" to keystroke "{_apple_string(text)}"')
    return "Typed text into the focused app."


def _normalize_combo(keys: str) -> str:
    return re.sub(r"\s+", "", keys.strip().lower())


def _combo_script(keys: str) -> str:
    combo = _normalize_combo(keys)
    if combo not in ALLOWED_COMBOS:
        raise ValueError(f"Unsupported key combo: {keys}")

    if "+" not in combo:
        key = SAFE_KEY_ALIASES[combo]
        if key in {"return", "escape", "tab", "space", "delete"}:
            return f'tell application "System Events" to key code ({_key_code(key)})'
        return f'tell application "System Events" to keystroke "{_apple_string(key)}"'

    parts = combo.split("+")
    key = parts[-1]
    modifiers = [SUPPORTED_MODIFIERS[part] for part in parts[:-1]]
    using = ", ".join(modifiers)
    if key == "tab":
        return f'tell application "System Events" to key code 48 using {{{using}}}'
    return f'tell application "System Events" to keystroke "{_apple_string(key)}" using {{{using}}}'


def _key_code(key: str) -> int:
    return {
        "return": 36,
        "escape": 53,
        "tab": 48,
        "space": 49,
        "delete": 51,
    }[key]


def press_key_combo(keys: str, confirm: bool = False) -> str:
    _require_confirmation(confirm)
    script = _combo_script(keys)
    _osascript(script)
    return f"Pressed {keys}."


def register(mcp):
    @mcp.tool()
    def open_app(app_name: str) -> str:
        """Open a Mac application by name."""
        return open_application(app_name)

    @mcp.tool()
    def focus_app(app_name: str) -> str:
        """Focus or activate a Mac application by name."""
        return focus_application(app_name)

    @mcp.tool()
    def capture_screen() -> dict:
        """Capture the current Mac screen to a PNG file."""
        path = capture_screen_file()
        return {"screenshot_path": path}

    @mcp.tool()
    def describe_screen(prompt: str | None = None) -> dict:
        """Capture and describe the current Mac screen using OpenAI vision."""
        return describe_current_screen(prompt=prompt)

    @mcp.tool()
    def click_screen(x: int, y: int, confirm: bool = False) -> str:
        """Click a screen coordinate. Requires explicit confirmation."""
        return click_screen_point(x=x, y=y, confirm=confirm)

    @mcp.tool()
    def type_text(text: str, confirm: bool = False) -> str:
        """Type text into the focused app. Requires explicit confirmation."""
        return type_into_focused_app(text=text, confirm=confirm)

    @mcp.tool()
    def press_keys(keys: str, confirm: bool = False) -> str:
        """Press a safe keyboard shortcut. Requires explicit confirmation."""
        return press_key_combo(keys=keys, confirm=confirm)
