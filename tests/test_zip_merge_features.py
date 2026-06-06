import os
import tempfile
import unittest
from unittest.mock import patch

from friday.memory import vault
from friday.tools import diagnostics, web


class ZipMergeFeatureTests(unittest.TestCase):
    def test_duckduckgo_html_parser_extracts_results(self):
        html = """
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com">Example <b>Result</b></a>
        <a class="result__snippet">A <b>short</b> snippet.</a>
        """

        results = web._parse_ddg_html(html, 3)

        self.assertEqual(results, [("Example Result", "https://example.com", "A short snippet.")])

    def test_memory_vault_stays_under_configured_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"OBSIDIAN_VAULT_PATH": temp_dir, "MEMORY_FOLDER": "Memory"},
                clear=False,
            ):
                path = vault.write_note("Facts/test.md", "hello")
                self.assertTrue(path.is_file())
                self.assertEqual(vault.read_note("Facts/test.md"), "hello")
                self.assertIsNone(vault.read_note("../escape.md"))

    def test_diagnostics_byte_formatter(self):
        self.assertEqual(diagnostics._fmt_bytes(1024), "1.0KB")


if __name__ == "__main__":
    unittest.main()
