"""Shell command MCP tools — propose / confirm broker.

FRIDAY proposes a shell command; the user says yes (in chat); FRIDAY
confirms. Mirrors the propose/confirm pattern used by
``friday.tools.messaging`` so the agent's UX is consistent across
risky surfaces.

Safety layers, top to bottom:

1. **Argv[0] allowlist.** Only a small set of read-mostly binaries
   are accepted as the program (`git status`, `ls`, `cat`, `rg`, …).
   Anything not on the list is rejected before we even look at args.
   This is the primary defence — a regex denylist was previously the
   first line of defence, and was bypassable via interpreter shells
   (`python -c '...'`, `osascript -e '...'`, `bash -c '...'`,
   `env sh`, `ssh user@host '...'`, …). The allowlist removes that
   whole class of bypass.
2. **Argv[0] hard-reject.** A redundant explicit blocklist of
   interpreters and privilege-escalation tools so that even if the
   allowlist is widened by a misguided env override, those entries
   cannot be added.
3. **Denylist patterns.** Belt-and-suspenders rejection of dangerous
   *argument* fragments (`rm -rf /`, redirects into block devices,
   command substitution syntax, env-var-prefix injection, etc.).
4. **Secret pattern reject** — refuses commands whose text looks
   like it's echoing an API key or token (reuses
   ``friday.tools.desktop.SECRET_PATTERNS``).
5. **Confirm gate** — ``confirm_shell_command`` must be called after
   ``propose_shell_command`` returns ``pending_confirmation``. The
   boss confirms verbally / textually per his stated UX preference;
   for a stronger out-of-band gate set
   ``FRIDAY_SHELL_REQUIRE_MODAL=1`` (reserved for future UI work).
6. **Fixed sandbox cwd** — commands run from
   ``$WORKSPACE_ROOTS[0]/friday-shell`` by default, created on demand.
   Override with ``FRIDAY_SHELL_CWD``.
7. **Timeout + capture** — 20s hard timeout, stdout/stderr captured
   and truncated to 4 KB each.

This tool is **not** a substitute for a real sandbox. Even with an
argv[0] allowlist, allowed binaries can still read files the caller
can read (`cat ~/.ssh/id_rsa`) or write inside the cwd. Treat it as a
convenience layer with a low blast radius, not as containment.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from friday.tools.desktop import (
    SECRET_PATTERNS,
    _configured_workspace_roots,
)


PENDING_TTL_SECONDS = 90
PENDING_SHELL_ACTIONS: dict[str, "PendingShell"] = {}

DEFAULT_TIMEOUT_S = 20
MAX_OUTPUT_CHARS = 4000

# Argv[0] allowlist — programs FRIDAY is allowed to invoke. Read-mostly
# tools the boss would plausibly ask about during normal work. Override
# via ``FRIDAY_SHELL_ALLOWLIST="git,ls,…"`` if you really mean it; the
# hard-block list below still applies on top.
DEFAULT_ALLOWLIST = frozenset({
    # File / dir inspection
    "ls", "cat", "head", "tail", "wc", "stat", "file", "tree",
    "pwd", "echo", "date", "uname", "hostname", "whoami",
    # Search
    "grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "locate",
    # VCS (read-only)
    "git",
    # Python toolchain (read-only)
    "uv", "pip", "pipx",
    # Project tooling (read-only)
    "make", "npm", "pnpm", "yarn",
    # Inspection
    "which", "type", "df", "du", "lsof", "ps", "top",
    # Misc text
    "diff", "sort", "uniq", "cut", "awk", "sed",
    "tr", "tee", "column", "jq", "yq",
})

# Argv[0] hard-block — interpreters, privilege-escalators, remote
# shells, and anything that can re-launch arbitrary code with its own
# argument grammar. This wins over the allowlist unconditionally.
HARD_BLOCKED_PROGS = frozenset({
    "bash", "sh", "zsh", "ksh", "fish", "dash", "csh", "tcsh",
    "python", "python2", "python3", "perl", "ruby", "node",
    "deno", "osascript", "bun", "lua", "php", "groovy",
    "env", "xargs", "exec", "eval",
    "sudo", "doas", "pkexec", "su",
    "ssh", "scp", "sftp", "rsync",
    "nc", "ncat", "socat", "telnet",
    "kill", "killall", "pkill",
})

DENYLIST_PATTERNS = (
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\brm\s+(-[a-z]*r[a-z]*\s+)?(/\s*|/\s*$|/\s+[a-z*])", re.IGNORECASE),
    re.compile(r"\brm\s+-rf?\s+/", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r":\(\)\s*\{", re.IGNORECASE),               # :(){:|:&};:
    re.compile(r">\s*/dev/(sd|nvme|disk)", re.IGNORECASE),
    re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b", re.IGNORECASE),
    re.compile(r"\bchown\b|\bchmod\b\s+777", re.IGNORECASE),
    re.compile(r"\bcurl\b[^|]*\|\s*(sh|bash|zsh)\b", re.IGNORECASE),
    re.compile(r"\bwget\b[^|]*\|\s*(sh|bash|zsh)\b", re.IGNORECASE),
    # Command substitution and process subs that shlex wouldn't catch.
    re.compile(r"\$\("),
    re.compile(r"<\("),
)


def _effective_allowlist() -> frozenset[str]:
    raw = os.getenv("FRIDAY_SHELL_ALLOWLIST", "").strip()
    if not raw:
        return DEFAULT_ALLOWLIST
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    # Hard-blocked progs can never enter the allowlist via env.
    return frozenset(parts - HARD_BLOCKED_PROGS)


def _normalised_prog(argv0: str) -> str:
    """Return the basename of argv[0], stripped, lowercased.

    Rejects absolute paths and any program containing path separators —
    we want callers to use the bare program name so the allowlist /
    blocklist matches survive ``/usr/bin/bash`` vs ``bash`` games.
    """
    if not argv0:
        raise ValueError("Empty program.")
    if "/" in argv0 or "\\" in argv0:
        raise PermissionError(
            "Reference the program by name, not a path — `git`, not `/usr/bin/git`."
        )
    if "=" in argv0:
        # Bash-style env-var prefix: FOO=bar cmd. shlex puts the whole
        # `FOO=bar` chunk in argv[0]; we never want to execute that.
        raise PermissionError("Environment-variable prefixes aren't allowed in shell commands.")
    return argv0.strip().lower()


@dataclass
class PendingShell:
    action_id: str
    command: str
    cwd: str
    reason: str
    created_at: float


def _reject_secret_command(command: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(command):
            raise ValueError("Refusing to run a command that looks like it embeds a secret.")


def _reject_denylisted(command: str) -> None:
    stripped = command.strip()
    if not stripped:
        raise ValueError("Empty command.")
    for pat in DENYLIST_PATTERNS:
        if pat.search(stripped):
            raise PermissionError(
                "That command is on the hard-refusal list, boss — not happening."
            )
    # No shell metacharacters. Even though we exec via argv (shell=False),
    # we still refuse these so the LLM can't trick the boss into
    # confirming what looks like a single command but is actually two.
    if any(token in stripped for token in (";", "&&", "||", "`", "$(", ">&", "|", ">", "<")):
        raise ValueError(
            "Chained / piped / redirected commands aren't supported. "
            "Propose one command at a time."
        )


def _enforce_allowlist(argv0: str) -> str:
    prog = _normalised_prog(argv0)
    if prog in HARD_BLOCKED_PROGS:
        raise PermissionError(
            f"`{prog}` is hard-blocked — interpreters and privilege escalators are never allowed."
        )
    allow = _effective_allowlist()
    if prog not in allow:
        raise PermissionError(
            f"`{prog}` isn't on the shell allowlist. Allowed: {sorted(allow)[:14]}…"
        )
    return prog


def _prune_expired() -> None:
    now = time.time()
    expired = [
        aid for aid, act in PENDING_SHELL_ACTIONS.items()
        if now - act.created_at > PENDING_TTL_SECONDS
    ]
    for aid in expired:
        PENDING_SHELL_ACTIONS.pop(aid, None)


def _latest_pending_id() -> str:
    _prune_expired()
    if not PENDING_SHELL_ACTIONS:
        raise KeyError("No pending shell command.")
    return max(
        PENDING_SHELL_ACTIONS.values(),
        key=lambda a: a.created_at,
    ).action_id


def _truncate(s: str) -> str:
    if len(s) <= MAX_OUTPUT_CHARS:
        return s
    return s[:MAX_OUTPUT_CHARS] + f"\n…[truncated {len(s) - MAX_OUTPUT_CHARS} chars]"


def _resolve_cwd() -> str:
    """Return the shell sandbox directory, creating it if needed.

    Tightened from ``WORKSPACE_ROOTS[0]`` (which can be the user's $HOME)
    to a dedicated subdir so a wayward `cat * > x` or relative-path
    write has a very small blast radius. Override with
    ``FRIDAY_SHELL_CWD``.
    """
    override = os.getenv("FRIDAY_SHELL_CWD", "").strip()
    if override:
        target = Path(override).expanduser().resolve()
    else:
        roots = _configured_workspace_roots()
        target = (roots[0] / "friday-shell").resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PermissionError(f"Cannot create shell sandbox dir: {exc}")
    return str(target)


def propose_shell(command: str, reason: str = "") -> dict:
    """Validate + register a pending shell command. Does NOT run it."""
    command = command.strip()
    _reject_secret_command(command)
    _reject_denylisted(command)
    # Try a dry parse so we fail early on malformed quoting.
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Could not parse command: {exc}")
    if not argv:
        raise ValueError("Empty command.")

    # Allowlist + hard-block gate. Final defence before we stage anything.
    prog = _enforce_allowlist(argv[0])

    action_id = uuid.uuid4().hex
    cwd = _resolve_cwd()
    PENDING_SHELL_ACTIONS[action_id] = PendingShell(
        action_id=action_id,
        command=command,
        cwd=cwd,
        reason=reason.strip(),
        created_at=time.time(),
    )
    return {
        "status": "pending_confirmation",
        "action_id": action_id,
        "command": command,
        "program": prog,
        "cwd": cwd,
        "reason": reason.strip(),
        "expires_in_seconds": PENDING_TTL_SECONDS,
    }


def confirm_shell(action_id: str | None = None) -> dict:
    """Run the most recent pending command (or the one identified by id)."""
    if not action_id:
        action_id = _latest_pending_id()

    action = PENDING_SHELL_ACTIONS.get(action_id)
    if action is None:
        raise KeyError(f"No pending shell command: {action_id}")
    if time.time() - action.created_at > PENDING_TTL_SECONDS:
        PENDING_SHELL_ACTIONS.pop(action_id, None)
        raise TimeoutError(f"Pending shell command expired: {action_id}")

    argv = shlex.split(action.command)
    # Re-validate at confirm time. If the allowlist tightened between
    # propose and confirm, the staged command is rejected.
    try:
        _enforce_allowlist(argv[0])
        _reject_denylisted(action.command)
    except (PermissionError, ValueError) as exc:
        PENDING_SHELL_ACTIONS.pop(action_id, None)
        return {
            "status": "blocked",
            "action_id": action_id,
            "command": action.command,
            "error": str(exc),
        }
    start = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=action.cwd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_S,
            check=False,
        )
        out, err, rc = result.stdout, result.stderr, result.returncode
        timed_out = False
    except FileNotFoundError as exc:
        PENDING_SHELL_ACTIONS.pop(action_id, None)
        return {
            "status": "error",
            "action_id": action_id,
            "command": action.command,
            "error": f"Command not found: {exc.filename}",
            "duration_s": round(time.monotonic() - start, 3),
        }
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if exc.stdout else ""
        err = exc.stderr.decode("utf-8", "replace") if exc.stderr else ""
        rc = -1
        timed_out = True
    finally:
        PENDING_SHELL_ACTIONS.pop(action_id, None)

    return {
        "status": "executed" if not timed_out else "timeout",
        "action_id": action_id,
        "command": action.command,
        "cwd": action.cwd,
        "returncode": rc,
        "stdout": _truncate(out or ""),
        "stderr": _truncate(err or ""),
        "duration_s": round(time.monotonic() - start, 3),
        "timed_out": timed_out,
    }


def cancel_shell(action_id: str | None = None) -> dict:
    if not action_id:
        try:
            action_id = _latest_pending_id()
        except KeyError:
            return {"status": "noop", "reason": "no pending shell command"}
    removed = PENDING_SHELL_ACTIONS.pop(action_id, None)
    return {
        "status": "cancelled" if removed else "noop",
        "action_id": action_id,
    }


def register(mcp):
    @mcp.tool()
    def propose_shell_command(command: str, reason: str = "") -> dict:
        """
        Stage a shell command for the boss to confirm. Use BEFORE running
        anything. Returns a pending action_id; call confirm_shell_command
        after the boss says yes / go / run it.
        """
        return propose_shell(command=command, reason=reason)

    @mcp.tool()
    def confirm_shell_command(action_id: str | None = None) -> dict:
        """
        Run the most recently proposed shell command. Captures stdout +
        stderr (truncated), 20s hard timeout, runs from WORKSPACE_ROOTS[0].
        """
        return confirm_shell(action_id=action_id)

    @mcp.tool()
    def cancel_shell_command(action_id: str | None = None) -> dict:
        """Drop a pending shell proposal without running it."""
        return cancel_shell(action_id=action_id)
