import unittest


class OdysseusPanelTests(unittest.TestCase):
    def test_base_url_allows_only_loopback_http_urls(self):
        from friday.desktop.odysseus_panel import normalize_odysseus_base_url

        self.assertEqual(
            normalize_odysseus_base_url("http://127.0.0.1:7870/"),
            "http://127.0.0.1:7870",
        )
        self.assertEqual(
            normalize_odysseus_base_url("http://localhost:7870"),
            "http://localhost:7870",
        )
        with self.assertRaises(ValueError):
            normalize_odysseus_base_url("https://example.com")
        with self.assertRaises(ValueError):
            normalize_odysseus_base_url("file:///tmp/index.html")

    def test_panel_urls_map_known_odysseus_surfaces(self):
        from friday.desktop.odysseus_panel import odysseus_panel_url

        base = "http://127.0.0.1:7870"
        self.assertEqual(odysseus_panel_url("home", base), base + "/")
        self.assertEqual(odysseus_panel_url("notes", base), base + "/notes")
        self.assertEqual(odysseus_panel_url("tasks", base), base + "/tasks")
        self.assertEqual(odysseus_panel_url("memory", base), base + "/memory")
        self.assertEqual(odysseus_panel_url("settings", base), base + "/settings")
        self.assertEqual(odysseus_panel_url("research", base), base + "/research")

        with self.assertRaises(ValueError):
            odysseus_panel_url("https://evil.test", base)

    def test_parse_odysseus_command_resolves_shortcuts(self):
        from friday.desktop.window import parse_odysseus_command

        self.assertEqual(parse_odysseus_command("/odysseus"), "home")
        self.assertEqual(parse_odysseus_command("/ody notes"), "notes")
        self.assertEqual(parse_odysseus_command("/ody tasks"), "tasks")
        self.assertEqual(parse_odysseus_command("/core"), "__core__")
        self.assertIsNone(parse_odysseus_command("open notes"))


if __name__ == "__main__":
    unittest.main()
