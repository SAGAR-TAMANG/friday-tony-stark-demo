"""
Keyword search across the vault. Plain Python token scoring — no embedding
deps. Good enough for "what did the boss tell me about X".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from friday.memory import vault


_IGNORED_DIRS = {".obsidian", ".trash"}
_WORD = re.compile(r"\w+")


@dataclass
class Hit:
    path: str
    title: str
    score: int
    snippet: str


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text)]


def _iter_notes(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.md"):
        if any(part in _IGNORED_DIRS for part in p.parts):
            continue
        yield p


def _snippet(body: str, terms: list[str], width: int = 160) -> str:
    lower = body.lower()
    for term in terms:
        idx = lower.find(term)
        if idx >= 0:
            start = max(0, idx - width // 2)
            end = min(len(body), idx + width // 2)
            snip = body[start:end].replace("\n", " ").strip()
            return ("…" if start > 0 else "") + snip + ("…" if end < len(body) else "")
    return body[:width].replace("\n", " ").strip()


def _title(path: Path, body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ")


def search(query: str, k: int = 5) -> list[Hit]:
    root = vault.vault_root()
    terms = _tokenize(query)
    if not terms:
        return []

    hits: list[Hit] = []
    for path in _iter_notes(root):
        try:
            body = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lower = body.lower()
        title = _title(path, body)
        title_lower = title.lower()
        score = 0
        for term in terms:
            score += lower.count(term)
            score += 3 * title_lower.count(term)
        if score == 0:
            continue
        hits.append(
            Hit(
                path=str(path.relative_to(root)),
                title=title,
                score=score,
                snippet=_snippet(body, terms),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]
