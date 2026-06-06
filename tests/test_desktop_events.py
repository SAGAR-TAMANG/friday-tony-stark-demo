import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from friday.desktop import events


class DesktopEventsTests(unittest.TestCase):
    def test_append_and_read_events_since_offset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "events.jsonl")
            with patch.dict(os.environ, {"FRIDAY_DESKTOP_EVENT_LOG": path}, clear=False):
                first = events.append_event("chat", role="user", text="hello")
                second = events.append_event("state", state="thinking")

                batch = events.read_events_since(0)
                size = os.path.getsize(path)

        self.assertEqual(batch.offset, size)
        self.assertEqual([item["type"] for item in batch.events], ["chat", "state"])
        self.assertGreater(second["seq"], first["seq"])

    def test_corrupt_event_lines_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "events.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{bad json}\n")
                handle.write('{"type":"chat","role":"assistant","text":"ok"}\n')

            with patch.dict(os.environ, {"FRIDAY_DESKTOP_EVENT_LOG": path}, clear=False):
                batch = events.read_events_since(0)

        self.assertEqual(len(batch.events), 1)
        self.assertEqual(batch.events[0]["text"], "ok")

    def test_emit_event_refuses_secret_like_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "events.jsonl")
            with patch.dict(os.environ, {"FRIDAY_DESKTOP_EVENT_LOG": path}, clear=False):
                with self.assertRaises(ValueError):
                    events.append_event("chat", role="user", text="OPENAI_API_KEY=sk-test-secret")

    def test_window_applies_external_chat_state_and_activity_events(self):
        window = Mock()
        window.chat = Mock()
        window.activity = Mock()
        window.orb = Mock()
        window._status_lbl = Mock()
        window._status_dot = Mock()
        window._on_assistant = Mock()
        window._on_state = Mock()

        from friday.desktop.window import apply_external_event

        apply_external_event(window, {"type": "chat", "role": "user", "text": "hi"})
        apply_external_event(window, {"type": "chat", "role": "assistant", "text": "hello"})
        apply_external_event(window, {"type": "state", "state": "speaking"})
        apply_external_event(window, {"type": "activity", "tool": "search_web", "detail": "query=x", "kind": "ok"})
        apply_external_event(window, {"type": "odysseus_panel", "panel": "notes"})

        window.chat.add_message.assert_any_call("hi", "user")
        window._on_assistant.assert_called_once_with("hello")
        window._on_state.assert_called_once_with("speaking")
        window.activity.log.assert_called_once_with("search_web", "query=x", "ok")
        window.show_odysseus_panel.assert_called_once_with("notes")


if __name__ == "__main__":
    unittest.main()
