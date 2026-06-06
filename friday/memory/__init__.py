"""
Persistent memory backed by an Obsidian vault on disk.

- vault.py    — low-level path / read / write helpers, sandboxed to the vault
- journal.py  — daily auto-log of every conversation turn
- search.py   — keyword search across the vault
"""

from friday.memory import vault, journal, search

__all__ = ["vault", "journal", "search"]
