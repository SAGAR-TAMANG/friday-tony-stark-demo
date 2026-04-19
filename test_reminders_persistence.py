"""
Smoke test for persistent reminders — proves the JSON roundtrip, lazy-load,
and graceful degradation on disk failure all work without running the MCP
server.

Run: uv run python test_reminders_persistence.py
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def _reload_module():
    """Fresh module state for each test — reminders.py has module-level globals."""
    import importlib
    import friday.tools.reminders as r
    importlib.reload(r)
    return r


def test_fresh_install_has_empty_store():
    """No reminders.json → empty store, next_id=1, no crash."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("pathlib.Path.home", return_value=Path(tmp)):
            r = _reload_module()
            r._load_once()
            assert r._store == [], f"expected empty, got {r._store}"
            assert r._next_id == 1


def test_persist_roundtrip():
    """Write a reminder, reload module, verify it's still there."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("pathlib.Path.home", return_value=Path(tmp)):
            r = _reload_module()
            r._load_once()
            r._store.append({"id": 1, "text": "Mumbai time", "created_at": "11:00 UTC"})
            r._next_id = 2
            r._persist()

            # Simulate process restart — reload module, check disk state rehydrates
            r2 = _reload_module()
            r2._load_once()
            assert len(r2._store) == 1, f"expected 1 reminder, got {r2._store}"
            assert r2._store[0]["text"] == "Mumbai time"
            assert r2._next_id == 2


def test_corrupt_json_does_not_crash():
    """A malformed reminders.json should not break the tool — fall back to empty."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / ".friday" / "reminders.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{not valid json", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=Path(tmp)):
            r = _reload_module()
            r._load_once()
            assert r._store == [], f"expected empty on corrupt, got {r._store}"


def test_clear_persists_empty_state():
    """Clearing reminders should wipe the disk file too, not just memory."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("pathlib.Path.home", return_value=Path(tmp)):
            r = _reload_module()
            r._load_once()
            r._store.extend([{"id": 1, "text": "a"}, {"id": 2, "text": "b"}])
            r._next_id = 3
            r._persist()

            r._store.clear()
            r._persist()

            # Reload and verify disk is empty
            r2 = _reload_module()
            r2._load_once()
            assert r2._store == [], f"expected empty after clear, got {r2._store}"


def main() -> int:
    tests = [
        test_fresh_install_has_empty_store,
        test_persist_roundtrip,
        test_corrupt_json_does_not_crash,
        test_clear_persists_empty_state,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {t.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
