import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from friday.tools import mac_worker


class MacWorkerToolTests(unittest.TestCase):
    def test_open_app_uses_mac_open(self):
        with patch("friday.tools.mac_worker.subprocess.run") as run:
            result = mac_worker.open_application("WhatsApp")

        run.assert_called_once_with(["open", "-a", "WhatsApp"], check=True)
        self.assertIn("WhatsApp", result)

    def test_focus_app_uses_osascript_activate(self):
        with patch("friday.tools.mac_worker.subprocess.run") as run:
            result = mac_worker.focus_application("Messages")

        args = run.call_args.args[0]
        self.assertEqual(args[:2], ["osascript", "-e"])
        self.assertIn('tell application "Messages" to activate', args[2])
        self.assertIn("Messages", result)

    def test_capture_screen_uses_configured_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"FRIDAY_SCREENSHOT_DIR": temp_dir}, clear=False):
                with patch("friday.tools.mac_worker.subprocess.run") as run:
                    path = mac_worker.capture_screen_file()

            self.assertEqual(Path(path).parent, Path(temp_dir).resolve())
            self.assertTrue(path.endswith(".png"))
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][0], "screencapture")

    def test_describe_screen_sends_base64_image_to_openai(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "screen.png"
            image_path.write_bytes(b"png-bytes")
            response = Mock(output_text="Chrome is open on a login page.")
            client = Mock()
            client.responses.create.return_value = response

            with patch("friday.tools.mac_worker.capture_screen_file", return_value=str(image_path)):
                result = mac_worker.describe_current_screen(client=client, prompt="What is visible?")

        self.assertEqual(result["description"], "Chrome is open on a login page.")
        request = client.responses.create.call_args.kwargs
        self.assertIn("input", request)
        content = request["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_image")
        self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))

    def test_risky_ui_actions_require_confirmation(self):
        with self.assertRaises(PermissionError):
            mac_worker.click_screen_point(10, 20, confirm=False)
        with self.assertRaises(PermissionError):
            mac_worker.type_into_focused_app("hello", confirm=False)
        with self.assertRaises(PermissionError):
            mac_worker.press_key_combo("cmd+l", confirm=False)

    def test_confirmation_env_can_disable_ui_guard(self):
        with patch.dict(os.environ, {"FRIDAY_REQUIRE_CONFIRMATION": "false"}, clear=False):
            with patch("friday.tools.mac_worker.subprocess.run") as run:
                mac_worker.click_screen_point(10, 20, confirm=False)

        run.assert_called_once()

    def test_confirmed_click_type_and_keys_use_system_events(self):
        with patch("friday.tools.mac_worker.subprocess.run") as run:
            mac_worker.click_screen_point(10, 20, confirm=True)
            mac_worker.type_into_focused_app("hello", confirm=True)
            mac_worker.press_key_combo("cmd+l", confirm=True)

        self.assertEqual(run.call_count, 3)
        scripts = [call.args[0][2] for call in run.call_args_list]
        self.assertIn("click at {10, 20}", scripts[0])
        self.assertIn("keystroke", scripts[1])
        self.assertIn("command down", scripts[2])

    def test_key_combo_rejects_unsupported_combo(self):
        with self.assertRaises(ValueError):
            mac_worker.press_key_combo("ctrl+alt+delete", confirm=True)


if __name__ == "__main__":
    unittest.main()
