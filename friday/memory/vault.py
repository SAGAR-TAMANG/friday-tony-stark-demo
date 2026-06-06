"""
Vault primitives — resolve paths inside the Obsidian vault and read/write
notes safely. Every public function refuses to escape the vault root.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from friday.config import config


class VaultError(ValueError):
    """Raised when a caller asks for a path outside the vault."""


_SUBFOLDERS = ("Daily", "Profile", "People", "Projects", "Facts", "Preferences")


def vault_root() -> Path:
    """Return the Memory/ folder inside the configured vault, creating it
    plus the standard subfolders on first use."""
    root = Path(config.OBSIDIAN_VAULT_PATH).expanduser().resolve() / config.MEMORY_FOLDER
    for sub in _SUBFOLDERS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def safe_join(rel: str) -> Path:
    """Resolve `rel` against the vault root and refuse anything that
    escapes via `..` or absolute paths."""
    if not rel:
        raise VaultError("empty path")
    candidate = (vault_root() / rel).resolve()
    root = vault_root().resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise VaultError(f"path escapes vault: {rel!r}")
    return candidate


def read_note(rel: str) -> Optional[str]:
    """Return note contents or None if missing."""
    try:
        path = safe_join(rel)
    except VaultError:
        return None
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write_note(
    rel: str,
    body: str,
    frontmatter: Optional[dict] = None,
) -> Path:
    """Overwrite a note, optionally prepending YAML frontmatter."""
    path = safe_join(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _render_frontmatter(frontmatter) + body if frontmatter else body
    path.write_text(content, encoding="utf-8")
    return path


def append_note(rel: str, body: str, frontmatter: Optional[dict] = None) -> Path:
    """Append `body` to a note. If the note doesn't exist yet, create it
    with the given frontmatter."""
    path = safe_join(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() and frontmatter:
        path.write_text(_render_frontmatter(frontmatter), encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(body)
    return path


def list_notes(folder: str = "") -> list[str]:
    """Return note paths (vault-relative) under `folder`, recursive."""
    try:
        base = safe_join(folder) if folder else vault_root()
    except VaultError:
        return []
    if not base.is_dir():
        return []
    root = vault_root()
    out = []
    for p in sorted(base.rglob("*.md")):
        out.append(str(p.relative_to(root)))
    return out


def slugify(text: str) -> str:
    """Filename-safe slug from arbitrary text."""
    keep = []
    for ch in text.strip().lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_/":
            keep.append("-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60] or "note"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _render_frontmatter(data: dict) -> str:
    lines = ["---"]
    for k, v in data.items():
        if isinstance(v, list):
            rendered = "[" + ", ".join(str(x) for x in v) + "]"
        else:
            rendered = str(v)
        lines.append(f"{k}: {rendered}")
    lines.append("---\n\n")
    return "\n".join(lines)
