import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from friday.tools import desktop


class DesktopToolTests(unittest.TestCase):
    def test_workspace_paths_stay_under_configured_roots(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"WORKSPACE_ROOTS": root}, clear=False):
                safe = desktop.resolve_workspace_path("notes/today.txt")
                self.assertEqual(safe, Path(root).resolve() / "notes" / "today.txt")

                with self.assertRaises(ValueError):
                    desktop.resolve_workspace_path(Path(root).parent / "outside.txt")

    def test_write_and_read_workspace_file(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"WORKSPACE_ROOTS": root}, clear=False):
                written = desktop.write_text_file("friday/out.txt", "hello", overwrite=False)
                self.assertEqual(written["path"], str(Path(root).resolve() / "friday" / "out.txt"))
                self.assertEqual(desktop.read_text_file("friday/out.txt")["content"], "hello")

                with self.assertRaises(FileExistsError):
                    desktop.write_text_file("friday/out.txt", "again", overwrite=False)

    def test_browser_urls_are_limited_to_safe_schemes(self):
        self.assertEqual(desktop.normalize_browser_url("example.com"), "https://example.com")
        self.assertEqual(desktop.normalize_browser_url("http://example.com"), "http://example.com")

        with self.assertRaises(ValueError):
            desktop.normalize_browser_url("javascript:alert(1)")

    def test_legacy_html_desktop_view_tool_is_removed(self):
        self.assertFalse(hasattr(desktop, "create_desktop_view"))

    def test_remember_note_writes_to_obsidian_vault_and_blocks_secrets(self):
        with tempfile.TemporaryDirectory() as vault:
            with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": vault}, clear=False):
                result = desktop.remember_note("Run Notes", "Use OpenAI LLM now.")
                note_path = Path(result["path"])
                self.assertTrue(note_path.is_file())
                self.assertIn("Use OpenAI LLM now.", note_path.read_text())

                with self.assertRaises(ValueError):
                    desktop.remember_note("Secret", "OPENAI_API_KEY=sk-test-secret")


if __name__ == "__main__":
    unittest.main()
