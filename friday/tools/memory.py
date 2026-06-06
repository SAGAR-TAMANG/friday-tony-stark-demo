"""
Memory tools — FRIDAY's persistent recall, backed by an Obsidian vault.
She uses these to file preferences, people, projects, and facts; and to
look them up in later sessions.
"""

from __future__ import annotations

from friday.memory import vault, journal, search


_VALID_CATEGORIES = {
    "facts": "Facts",
    "people": "People",
    "projects": "Projects",
    "preferences": "Preferences",
}

_PROFILE_PATH = "Profile/about_user.md"


def _category_folder(category: str) -> str:
    return _VALID_CATEGORIES.get(category.strip().lower(), "Facts")


def register(mcp):

    @mcp.tool()
    async def save_memory(
        content: str,
        category: str = "facts",
        tags: list[str] | None = None,
        title: str = "",
    ) -> str:
        """
        File a curated memory into the Obsidian vault.

        Use this whenever the user states a preference, fact, plan, name,
        relationship, or project worth remembering across sessions.

        category: one of "facts", "people", "projects", "preferences".
                  Anything else falls back to "facts".
        tags:     optional list of tag strings (no leading '#').
        title:    optional title; if blank, a slug is derived from `content`.
        """
        folder = _category_folder(category)
        slug = vault.slugify(title or content)
        rel = f"{folder}/{slug}.md"

        existing = vault.read_note(rel)
        now = vault.now_iso()
        if existing is None:
            frontmatter = {
                "tags": tags or [folder.lower()],
                "created": now,
                "updated": now,
            }
            body = f"# {title or slug.replace('-', ' ').title()}\n\n{content.strip()}\n"
            path = vault.write_note(rel, body, frontmatter=frontmatter)
        else:
            path = vault.append_note(rel, f"\n- {now}: {content.strip()}\n")
        return f"Saved to {path.relative_to(vault.vault_root().parent)}"

    @mcp.tool()
    async def recall_recent(days: int = 3) -> str:
        """
        Return the last `days` of journal entries (auto-logged turns).
        Use this to refresh context on what was discussed recently.
        """
        text = journal.recent_journal(days=max(1, min(days, 14)))
        return text or "(no recent journal entries)"

    @mcp.tool()
    async def search_memory(query: str, max_results: int = 5) -> str:
        """
        Keyword search across every note in the vault. Returns the most
        relevant notes with a short snippet. Use this before answering
        questions where memory might help — "what did I tell you about X",
        "who is Y", "what's my Z".
        """
        hits = search.search(query, k=max(1, min(max_results, 20)))
        if not hits:
            return f"No notes match {query!r}."
        lines = []
        for h in hits:
            lines.append(f"[{h.path}] {h.title} — {h.snippet}")
        return "\n".join(lines)

    @mcp.tool()
    async def read_note(path: str) -> str:
        """Read a note from the vault by its vault-relative path."""
        body = vault.read_note(path)
        if body is None:
            return f"No note at {path!r}."
        return body

    @mcp.tool()
    async def list_notes(folder: str = "") -> list[str]:
        """List notes under a vault folder (recursive). Empty folder = all."""
        return vault.list_notes(folder)

    @mcp.tool()
    async def update_profile(field: str, value: str) -> str:
        """
        Record an "about the user" fact in Profile/about_user.md as a
        bullet. If the same field already exists, its value is replaced.
        Use this for stable facts: name, location, role, preferences,
        important relationships.
        """
        field = field.strip()
        value = value.strip()
        if not field or not value:
            return "Field and value are both required."

        existing = vault.read_note(_PROFILE_PATH) or ""
        body, frontmatter_block = _split_frontmatter(existing)
        bullet = f"- **{field}**: {value}"
        lines = body.splitlines()

        prefix = f"- **{field}**:"
        replaced = False
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                lines[i] = bullet
                replaced = True
                break
        if not replaced:
            if not lines or lines[-1].strip():
                lines.append("")
            lines.append(bullet)

        new_body = "\n".join(lines).rstrip() + "\n"
        frontmatter = {
            "tags": ["profile"],
            "updated": vault.now_iso(),
        }
        vault.write_note(_PROFILE_PATH, new_body, frontmatter=frontmatter)
        return f"Profile updated: {field} = {value}"

    @mcp.tool()
    async def get_profile() -> str:
        """Return the about-user profile note verbatim."""
        body = vault.read_note(_PROFILE_PATH)
        return body or "(no profile yet)"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Strip a leading YAML frontmatter block (---...---) if present."""
    if not text.startswith("---"):
        return text, ""
    end = text.find("\n---", 3)
    if end < 0:
        return text, ""
    fm_end = text.find("\n", end + 4)
    if fm_end < 0:
        return "", text
    return text[fm_end + 1 :].lstrip("\n"), text[: fm_end + 1]
