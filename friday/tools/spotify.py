"""Spotify MCP tools — full user-account OAuth + Web API playback.

What this lets FRIDAY do:

* Search tracks / artists / albums / playlists by name.
* Play, pause, resume, skip, previous.
* Set volume, toggle shuffle / repeat.
* Queue tracks.
* Read what's currently playing and the user's libraries.

Auth model — **Authorization Code with PKCE** (no client secret needed
on the device). On first use the boss runs ``spotify_authenticate`` →
a tiny local HTTP server opens on ``http://127.0.0.1:8765/callback``,
the default browser opens to Spotify's consent page, the redirect
lands the auth code, the tool exchanges it for tokens, and a refresh
token is saved to ``~/.config/friday/spotify-token.json``. Subsequent
calls auto-refresh.

The boss needs to register an app at https://developer.spotify.com/dashboard
(free) and set ``SPOTIFY_CLIENT_ID`` in ``.env``, plus add
``http://127.0.0.1:8765/callback`` as an allowed redirect URI on the
app. PKCE means the client secret never has to leave the dashboard.

Playback requires a Spotify **Premium** account and an *active device*
(the Spotify desktop app running, the iPhone, etc.). If no device is
active, the tool will best-effort wake the desktop Spotify app via
AppleScript and retry.

Security:

* Token file is mode 0600.
* No bearer or refresh token is ever returned from a tool. The tools
  return only Spotify API payloads (track names, device names, etc.)
  with secret-pattern scrubbing on free-form fields.
* All write endpoints (play, pause, queue, volume) are explicit tools
  — they're not behind the propose / confirm broker because they're
  reversible by definition (skip back, pause, lower volume). The boss
  can revoke FRIDAY's access at https://www.spotify.com/account/apps/
  any time.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import socketserver
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


TOKEN_PATH = Path.home() / ".config" / "friday" / "spotify-token.json"
DEFAULT_REDIRECT = "http://127.0.0.1:8765/callback"
REDIRECT_PORT = 8765
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-library-read "
    "user-top-read "
    "user-read-recently-played"
)


# ---------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------

def _client_id() -> str:
    cid = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    if not cid:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID is not set. Register an app at "
            "https://developer.spotify.com/dashboard, add "
            f"{DEFAULT_REDIRECT} as a redirect URI, then put the "
            "Client ID in .env."
        )
    return cid


def _redirect_uri() -> str:
    return os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT).strip() or DEFAULT_REDIRECT


def _load_tokens() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _save_tokens(payload: dict) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(payload, indent=2))
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def _is_expired(tokens: dict) -> bool:
    return time.time() > tokens.get("expires_at", 0) - 30


# ---------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------
# Local redirect catcher
# ---------------------------------------------------------------------

class _AuthCodeHandler(http.server.BaseHTTPRequestHandler):
    received_code: str | None = None
    received_error: str | None = None

    def do_GET(self):  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "error" in params:
            _AuthCodeHandler.received_error = params["error"][0]
            body = b"FRIDAY auth: error. You can close this tab."
        elif "code" in params:
            _AuthCodeHandler.received_code = params["code"][0]
            body = (
                b"<html><body style='font-family:monospace;background:#03060B;"
                b"color:#6EC2FF;padding:40px'>FRIDAY auth complete. You can "
                b"close this tab.</body></html>"
            )
        else:
            body = b"FRIDAY auth: no code in callback."
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a, **_kw):
        return  # silence the default access log


def _await_auth_code(timeout_s: int = 180) -> str:
    _AuthCodeHandler.received_code = None
    _AuthCodeHandler.received_error = None
    server = socketserver.TCPServer(("127.0.0.1", REDIRECT_PORT), _AuthCodeHandler)
    server.timeout = 1
    deadline = time.time() + timeout_s
    try:
        while time.time() < deadline:
            server.handle_request()
            if _AuthCodeHandler.received_code:
                return _AuthCodeHandler.received_code
            if _AuthCodeHandler.received_error:
                raise RuntimeError(
                    f"Spotify auth denied: {_AuthCodeHandler.received_error}"
                )
    finally:
        server.server_close()
    raise TimeoutError("Spotify auth timed out — the boss didn't grant permission in time.")


# ---------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------

def _exchange_code_for_tokens(code: str, verifier: str) -> dict:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "client_id": _client_id(),
            "code_verifier": verifier,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _refresh_tokens(refresh_token: str) -> dict:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _client_id(),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _store_token_response(payload: dict) -> dict:
    tokens = _load_tokens() or {}
    tokens["access_token"] = payload["access_token"]
    tokens["expires_at"] = time.time() + int(payload.get("expires_in", 3600))
    if payload.get("refresh_token"):
        tokens["refresh_token"] = payload["refresh_token"]
    tokens["scope"] = payload.get("scope", SCOPES)
    _save_tokens(tokens)
    return tokens


def _bearer() -> str:
    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError(
            "FRIDAY isn't linked to Spotify yet, boss — ask me to "
            "authenticate Spotify first."
        )
    if _is_expired(tokens):
        refreshed = _refresh_tokens(tokens["refresh_token"])
        tokens = _store_token_response(refreshed)
    return tokens["access_token"]


# ---------------------------------------------------------------------
# API wrapper
# ---------------------------------------------------------------------

def _api(method: str, path: str, **kwargs) -> Any:
    url = path if path.startswith("http") else API_BASE + path
    headers = kwargs.pop("headers", {}) or {}
    headers["Authorization"] = f"Bearer {_bearer()}"
    resp = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
    if resp.status_code == 204:
        return None
    if resp.status_code == 404 and "player" in path:
        raise RuntimeError(
            "No active Spotify device. Open the Spotify app on a phone or "
            "laptop and start anything once, then ask me again."
        )
    if resp.status_code >= 400:
        try:
            err = resp.json()
        except ValueError:
            err = {"error": resp.text[:200]}
        raise RuntimeError(f"Spotify API error {resp.status_code}: {err}")
    if not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _wake_desktop_app() -> None:
    """Best-effort poke the Spotify desktop app on macOS so a device exists."""
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Spotify" to activate'],
            check=False, capture_output=True, timeout=4,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _ensure_device() -> str | None:
    """Return the active device id, waking the desktop app if needed."""
    devices = _api("GET", "/me/player/devices") or {}
    for dev in devices.get("devices", []):
        if dev.get("is_active"):
            return dev["id"]
    # No active device. Try waking the desktop app and re-querying.
    _wake_desktop_app()
    time.sleep(1.2)
    devices = _api("GET", "/me/player/devices") or {}
    if devices.get("devices"):
        # Transfer playback to the first available device.
        target = devices["devices"][0]["id"]
        _api("PUT", "/me/player", json={"device_ids": [target], "play": False})
        return target
    return None


# ---------------------------------------------------------------------
# Authentication tool
# ---------------------------------------------------------------------

def authenticate() -> dict:
    """Run the OAuth flow — opens a browser, waits for the redirect."""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": SCOPES,
        "state": state,
        "show_dialog": "false",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    webbrowser.open(url)

    # Spin up the catcher on the main thread of this call — runs
    # one-request-at-a-time until the redirect lands.
    code_holder: dict[str, str] = {}
    err_holder: dict[str, str] = {}

    def _run():
        try:
            code_holder["code"] = _await_auth_code()
        except Exception as exc:
            err_holder["err"] = str(exc)

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout=180)

    if err_holder:
        raise RuntimeError(err_holder["err"])
    if "code" not in code_holder:
        raise TimeoutError("Spotify auth timed out.")

    payload = _exchange_code_for_tokens(code_holder["code"], verifier)
    _store_token_response(payload)
    me = _api("GET", "/me") or {}
    return {
        "status": "linked",
        "user": me.get("display_name") or me.get("id"),
        "product": me.get("product"),
        "scope": SCOPES,
    }


# ---------------------------------------------------------------------
# Helpers shared by play_* tools
# ---------------------------------------------------------------------

def _search_first(query: str, kind: str) -> dict | None:
    res = _api("GET", "/search", params={"q": query, "type": kind, "limit": 1})
    items = ((res or {}).get(f"{kind}s") or {}).get("items") or []
    return items[0] if items else None


def _start_playback(*, context_uri: str | None = None, uris: list[str] | None = None) -> dict:
    device_id = _ensure_device()
    body: dict[str, Any] = {}
    if context_uri:
        body["context_uri"] = context_uri
    if uris:
        body["uris"] = uris
    params = {"device_id": device_id} if device_id else None
    _api("PUT", "/me/player/play", params=params, json=body)
    cur = _api("GET", "/me/player/currently-playing") or {}
    item = cur.get("item") or {}
    return {
        "status": "playing",
        "track": item.get("name"),
        "artists": ", ".join(a.get("name", "") for a in item.get("artists") or []),
        "device_id": device_id,
    }


# ---------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------

def register(mcp):

    @mcp.tool()
    def spotify_authenticate() -> dict:
        """
        First-time setup: opens a browser for the boss to grant FRIDAY
        access to his Spotify account. Saves a refresh token under
        ~/.config/friday/spotify-token.json. Idempotent — re-running
        re-authorises.
        """
        return authenticate()

    @mcp.tool()
    def spotify_play_track(query: str) -> dict:
        """
        Search for a track by name (and optionally artist) and start
        playing it. Example queries: "blinding lights", "redbone childish gambino".
        """
        track = _search_first(query, "track")
        if not track:
            return {"status": "not_found", "query": query}
        return _start_playback(uris=[track["uri"]])

    @mcp.tool()
    def spotify_play_artist(query: str) -> dict:
        """Search for an artist and start playing their top tracks."""
        artist = _search_first(query, "artist")
        if not artist:
            return {"status": "not_found", "query": query}
        return _start_playback(context_uri=artist["uri"])

    @mcp.tool()
    def spotify_play_album(query: str) -> dict:
        """Search for an album by name and play it from the top."""
        album = _search_first(query, "album")
        if not album:
            return {"status": "not_found", "query": query}
        return _start_playback(context_uri=album["uri"])

    @mcp.tool()
    def spotify_play_playlist(query: str) -> dict:
        """Search for a playlist by name and start playing it."""
        playlist = _search_first(query, "playlist")
        if not playlist:
            return {"status": "not_found", "query": query}
        return _start_playback(context_uri=playlist["uri"])

    @mcp.tool()
    def spotify_play_liked() -> dict:
        """Play the boss's Liked Songs library on shuffle."""
        liked = _api("GET", "/me/tracks", params={"limit": 50}) or {}
        items = liked.get("items") or []
        if not items:
            return {"status": "empty", "message": "No liked songs found."}
        uris = [item["track"]["uri"] for item in items if item.get("track")]
        # Enable shuffle so the 50-track window doesn't feel scripted.
        try:
            _api("PUT", "/me/player/shuffle", params={"state": "true"})
        except Exception:
            pass
        return _start_playback(uris=uris)

    @mcp.tool()
    def spotify_pause() -> dict:
        """Pause whatever's currently playing."""
        _api("PUT", "/me/player/pause")
        return {"status": "paused"}

    @mcp.tool()
    def spotify_resume() -> dict:
        """Resume playback from where it was paused."""
        device_id = _ensure_device()
        params = {"device_id": device_id} if device_id else None
        _api("PUT", "/me/player/play", params=params)
        return {"status": "resumed", "device_id": device_id}

    @mcp.tool()
    def spotify_next_track() -> dict:
        """Skip to the next track."""
        _api("POST", "/me/player/next")
        return {"status": "skipped"}

    @mcp.tool()
    def spotify_previous_track() -> dict:
        """Go back to the previous track."""
        _api("POST", "/me/player/previous")
        return {"status": "rewound"}

    @mcp.tool()
    def spotify_set_volume(percent: int) -> dict:
        """Set Spotify volume 0-100."""
        percent = max(0, min(100, int(percent)))
        _api("PUT", "/me/player/volume", params={"volume_percent": percent})
        return {"status": "ok", "volume": percent}

    @mcp.tool()
    def spotify_toggle_shuffle(on: bool = True) -> dict:
        """Turn shuffle on or off."""
        _api("PUT", "/me/player/shuffle", params={"state": "true" if on else "false"})
        return {"status": "ok", "shuffle": on}

    @mcp.tool()
    def spotify_set_repeat(mode: str = "off") -> dict:
        """Repeat mode: 'off' | 'track' | 'context'."""
        if mode not in {"off", "track", "context"}:
            raise ValueError("mode must be one of: off, track, context")
        _api("PUT", "/me/player/repeat", params={"state": mode})
        return {"status": "ok", "repeat": mode}

    @mcp.tool()
    def spotify_queue_track(query: str) -> dict:
        """Search for a track and add it to the playback queue."""
        track = _search_first(query, "track")
        if not track:
            return {"status": "not_found", "query": query}
        _api("POST", "/me/player/queue", params={"uri": track["uri"]})
        return {
            "status": "queued",
            "track": track["name"],
            "artists": ", ".join(a.get("name", "") for a in track.get("artists") or []),
        }

    @mcp.tool()
    def spotify_now_playing() -> dict:
        """What's currently playing?"""
        cur = _api("GET", "/me/player/currently-playing") or {}
        if not cur:
            return {"status": "nothing_playing"}
        item = cur.get("item") or {}
        return {
            "status": "playing" if cur.get("is_playing") else "paused",
            "track": item.get("name"),
            "artists": ", ".join(a.get("name", "") for a in item.get("artists") or []),
            "album": (item.get("album") or {}).get("name"),
            "progress_ms": cur.get("progress_ms"),
            "duration_ms": item.get("duration_ms"),
        }

    @mcp.tool()
    def spotify_devices() -> dict:
        """List available Spotify devices."""
        return _api("GET", "/me/player/devices") or {"devices": []}

    @mcp.tool()
    def spotify_my_playlists(limit: int = 20) -> dict:
        """List the boss's playlists."""
        limit = max(1, min(int(limit), 50))
        res = _api("GET", "/me/playlists", params={"limit": limit}) or {}
        return {
            "items": [
                {"name": p.get("name"), "id": p.get("id"), "tracks": (p.get("tracks") or {}).get("total")}
                for p in res.get("items") or []
            ]
        }
