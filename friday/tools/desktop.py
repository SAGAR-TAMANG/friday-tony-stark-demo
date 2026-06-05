"""
Desktop tools for local browser control, safe file storage, and memory notes.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv


load_dotenv()

PROJECT_SLUG = "friday-tony-stark-demo"
DEFAULT_MAX_READ_CHARS = 6000
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|token|password|secret)\s*="),
)


def _configured_workspace_roots() -> list[Path]:
    raw = os.getenv("WORKSPACE_ROOTS", "").strip()
    if not raw:
        raw = str(Path.home())

    parts: list[str] = []
    for chunk in raw.split(os.pathsep):
        parts.extend(piece.strip() for piece in chunk.split(","))

    roots = [Path(part).expanduser().resolve() for part in parts if part]
    return roots or [Path.home().resolve()]


def _vault_path() -> Path:
    raw = os.getenv("OBSIDIAN_VAULT_PATH", "~/FridayVault")
    return Path(raw).expanduser().resolve()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_secret_content(content: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            raise ValueError("Refusing to store content that looks like a secret.")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return slug[:60] or "note"


def resolve_workspace_path(path: str | os.PathLike[str]) -> Path:
    """Resolve a user path and keep it inside WORKSPACE_ROOTS."""
    if not str(path).strip():
        raise ValueError("Path is required.")

    roots = _configured_workspace_roots()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate

    resolved = candidate.resolve(strict=False)
    if any(_is_under(resolved, root) for root in roots):
        return resolved

    raise ValueError("Path is outside configured WORKSPACE_ROOTS.")


def normalize_browser_url(url: str) -> str:
    """Normalize a URL and allow only browser-safe web schemes."""
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL is required.")

    parsed = urlparse(cleaned)
    if not parsed.scheme:
        cleaned = f"https://{cleaned}"
        parsed = urlparse(cleaned)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs can be opened as websites.")
    if not parsed.netloc:
        raise ValueError("URL must include a host.")

    return cleaned


def read_text_file(path: str, max_chars: int = DEFAULT_MAX_READ_CHARS) -> dict:
    target = resolve_workspace_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {target}")

    limit = max(1, min(max_chars, 20000))
    content = target.read_text(errors="replace")
    return {
        "path": str(target),
        "characters": len(content),
        "truncated": len(content) > limit,
        "content": content[:limit],
    }


def write_text_file(path: str, content: str, overwrite: bool = False) -> dict:
    _reject_secret_content(content)
    target = resolve_workspace_path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"path": str(target), "characters": len(content)}


def append_text_file(path: str, content: str) -> dict:
    _reject_secret_content(content)
    target = resolve_workspace_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(content)
    return {"path": str(target), "appended_characters": len(content)}


def list_workspace(path: str = ".", limit: int = 80) -> dict:
    target = resolve_workspace_path(path)
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {target}")

    entries = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        entries.append({
            "name": child.name,
            "path": str(child),
            "type": "directory" if child.is_dir() else "file",
        })
        if len(entries) >= max(1, min(limit, 200)):
            break

    return {"path": str(target), "entries": entries}


def create_desktop_view() -> dict:
    root = _configured_workspace_roots()[0]
    target = resolve_workspace_path(root / "Friday-Desktop-View.html")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>F.R.I.D.A.Y. Desktop View</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #090b10; color: #f5f7fb; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 48px 24px; }}
    h1 {{ font-size: 38px; margin: 0 0 8px; letter-spacing: 0; }}
    p {{ color: #aeb7c8; line-height: 1.5; }}
    section {{ border-top: 1px solid #293044; padding: 22px 0; }}
    ul {{ padding-left: 20px; line-height: 1.8; }}
    .status {{ color: #7ce7b2; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    <h1>F.R.I.D.A.Y.</h1>
    <p class="status">Local desktop bridge online</p>
    <p>Generated {html.escape(now)} on this Mac.</p>
    <section>
      <h2>Enabled Capabilities</h2>
      <ul>
        <li>Open websites in the default browser.</li>
        <li>Open local files and folders inside configured workspace roots.</li>
        <li>Read, write, append, and list files under WORKSPACE_ROOTS.</li>
        <li>Store explicit memory notes under OBSIDIAN_VAULT_PATH.</li>
      </ul>
    </section>
  </main>
</body>
</html>
"""
    target.write_text(html_doc)
    return {"path": str(target), "url": target.as_uri()}


def remember_note(title: str, content: str) -> dict:
    _reject_secret_content(content)
    vault = _vault_path()
    notes_dir = vault / "projects" / PROJECT_SLUG / "outputs" / "friday-memory"
    notes_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    target = notes_dir / f"{timestamp}-{_slugify(title)}.md"
    body = (
        "---\n"
        f"title: {title.strip() or 'Friday Memory Note'}\n"
        "type: output\n"
        f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        "tags: [friday, memory]\n"
        "---\n\n"
        f"# {title.strip() or 'Friday Memory Note'}\n\n"
        f"{content.strip()}\n"
    )
    target.write_text(body)
    return {"path": str(target), "characters": len(body)}


def search_memory(query: str, limit: int = 5) -> dict:
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Query is required.")

    vault = _vault_path()
    matches = []
    for note in vault.rglob("*.md"):
        try:
            text = note.read_text(errors="replace")
        except OSError:
            continue
        index = text.lower().find(needle)
        if index == -1:
            continue
        start = max(0, index - 120)
        end = min(len(text), index + len(needle) + 220)
        matches.append({"path": str(note), "excerpt": text[start:end].strip()})
        if len(matches) >= max(1, min(limit, 20)):
            break

    return {"query": query, "matches": matches}


def register(mcp):
    @mcp.tool()
    def open_website(url: str) -> str:
        """Open a website in the Mac's default browser. Only http and https URLs are allowed."""
        target = normalize_browser_url(url)
        webbrowser.open(target)
        return f"Opened {target} in the desktop browser."

    @mcp.tool()
    def open_path(path: str) -> str:
        """Open a local file or folder under WORKSPACE_ROOTS in Finder/default app."""
        target = resolve_workspace_path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")
        subprocess.run(["open", str(target)], check=False)
        return f"Opened {target} on the desktop."

    @mcp.tool()
    def open_friday_desktop_view() -> str:
        """Create and open FRIDAY's local desktop status view."""
        result = create_desktop_view()
        webbrowser.open(result["url"])
        return f"Opened FRIDAY desktop view: {result['path']}"

    @mcp.tool()
    def list_workspace_files(path: str = ".", limit: int = 80) -> dict:
        """List files and folders under WORKSPACE_ROOTS."""
        return list_workspace(path=path, limit=limit)

    @mcp.tool()
    def read_workspace_file(path: str, max_chars: int = DEFAULT_MAX_READ_CHARS) -> dict:
        """Read a text file under WORKSPACE_ROOTS."""
        return read_text_file(path=path, max_chars=max_chars)

    @mcp.tool()
    def write_workspace_file(path: str, content: str, overwrite: bool = False) -> dict:
        """Write a text file under WORKSPACE_ROOTS. Refuses likely secrets."""
        return write_text_file(path=path, content=content, overwrite=overwrite)

    @mcp.tool()
    def append_workspace_file(path: str, content: str) -> dict:
        """Append text to a file under WORKSPACE_ROOTS. Refuses likely secrets."""
        return append_text_file(path=path, content=content)

    @mcp.tool()
    def remember_in_obsidian(title: str, content: str) -> dict:
        """Store an explicit user-approved memory note in OBSIDIAN_VAULT_PATH. Refuses likely secrets."""
        return remember_note(title=title, content=content)

    @mcp.tool()
    def search_obsidian_memory(query: str, limit: int = 5) -> dict:
        """Search markdown notes under OBSIDIAN_VAULT_PATH."""
        return search_memory(query=query, limit=limit)
