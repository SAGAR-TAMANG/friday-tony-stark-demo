import os
import tempfile
import time
import unittest
from unittest.mock import patch

from friday.desktop import events
from friday.tools import odysseus


class OdysseusToolTests(unittest.TestCase):
    def setUp(self):
        odysseus.clear_pending_actions()

    def tearDown(self):
        odysseus.clear_pending_actions()

    def test_propose_odysseus_action_creates_pending_action_without_calling_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            event_log = os.path.join(temp_dir, "events.jsonl")
            with (
                patch.dict(os.environ, {"FRIDAY_DESKTOP_EVENT_LOG": event_log}, clear=False),
                patch("friday.tools.odysseus._send_odysseus_request") as send,
            ):
                result = odysseus.propose_odysseus_action(
                    "health.status",
                    {},
                    reason="Check workspace status",
                )

                send.assert_not_called()
                batch = events.read_events_since(0)

        self.assertEqual(result["status"], "pending_confirmation")
        self.assertEqual(result["risk"], "read")
        self.assertIn("action_id", result)
        self.assertIn("GET /api/health", result["target"])
        self.assertEqual(batch.events[-1]["tool"], "odysseus")
        self.assertIn("health.status", batch.events[-1]["detail"])

    def test_confirm_odysseus_action_executes_latest_pending_action_once(self):
        first = odysseus.propose_odysseus_action("health.status", {}, reason="old")
        second = odysseus.propose_odysseus_action("runtime.status", {}, reason="new")

        with patch("friday.tools.odysseus._send_odysseus_request", return_value={"ok": True}) as send:
            result = odysseus.confirm_odysseus_action()

        send.assert_called_once()
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["action_id"], second["action_id"])
        self.assertIn(first["action_id"], odysseus.PENDING_ODYSSEUS_ACTIONS)
        self.assertNotIn(second["action_id"], odysseus.PENDING_ODYSSEUS_ACTIONS)

    def test_expired_odysseus_action_is_rejected(self):
        prepared = odysseus.propose_odysseus_action("health.status", {}, reason="old")
        odysseus.PENDING_ODYSSEUS_ACTIONS[prepared["action_id"]].created_at = time.time() - 999

        with self.assertRaises(TimeoutError):
            odysseus.confirm_odysseus_action(prepared["action_id"])

    def test_cancelled_odysseus_action_cannot_execute(self):
        prepared = odysseus.propose_odysseus_action("health.status", {}, reason="cancel")

        cancelled = odysseus.cancel_odysseus_action(prepared["action_id"])

        self.assertEqual(cancelled["status"], "cancelled")
        with self.assertRaises(KeyError):
            odysseus.confirm_odysseus_action(prepared["action_id"])

    def test_unknown_odysseus_action_is_rejected(self):
        with self.assertRaises(ValueError):
            odysseus.propose_odysseus_action("raw.http", {"url": "http://127.0.0.1:7870/api/tokens"})

    def test_odysseus_offline_returns_clean_error(self):
        prepared = odysseus.propose_odysseus_action("health.status", {}, reason="offline")

        with patch("friday.tools.odysseus._send_odysseus_request", side_effect=ConnectionError("offline")):
            result = odysseus.confirm_odysseus_action(prepared["action_id"])

        self.assertEqual(result["status"], "error")
        self.assertIn("offline", result["error"])
        self.assertNotIn(prepared["action_id"], odysseus.PENDING_ODYSSEUS_ACTIONS)

    def test_bridge_token_is_never_written_to_desktop_event_log(self):
        token = "ody_test_bridge_token_123456789"
        with tempfile.TemporaryDirectory() as temp_dir:
            event_log = os.path.join(temp_dir, "events.jsonl")
            with (
                patch.dict(
                    os.environ,
                    {
                        "FRIDAY_DESKTOP_EVENT_LOG": event_log,
                        "ODYSSEUS_BRIDGE_TOKEN": token,
                    },
                    clear=False,
                ),
                patch("friday.tools.odysseus._send_odysseus_request", return_value={"ok": True}),
            ):
                prepared = odysseus.propose_odysseus_action("health.status", {}, reason="secret check")
                odysseus.confirm_odysseus_action(prepared["action_id"])
                with open(event_log, encoding="utf-8") as handle:
                    content = handle.read()

        self.assertNotIn(token, content)

    def test_open_panel_emits_hud_event_without_browser(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            event_log = os.path.join(temp_dir, "events.jsonl")
            with (
                patch.dict(os.environ, {"FRIDAY_DESKTOP_EVENT_LOG": event_log}, clear=False),
                patch("friday.tools.odysseus.webbrowser.open") as open_url,
            ):
                prepared = odysseus.propose_odysseus_action(
                    "open.panel",
                    {"panel": "notes"},
                    reason="show notes",
                )
                result = odysseus.confirm_odysseus_action(prepared["action_id"])
                batch = events.read_events_since(0)

        open_url.assert_not_called()
        self.assertEqual(result["status"], "executed")
        self.assertIn({"type": "odysseus_panel", "panel": "notes"}, [
            {"type": event.get("type"), "panel": event.get("panel")}
            for event in batch.events
        ])

    def test_tasks_create_supplies_odysseus_required_schedule_default(self):
        spec = odysseus.ACTION_CATALOG["tasks.create"]
        with (
            patch.dict(os.environ, {"ODYSSEUS_BRIDGE_TOKEN": "ody_test_token"}, clear=False),
            patch("friday.tools.odysseus.httpx.Client") as client_class,
        ):
            client = client_class.return_value.__enter__.return_value
            response = client.request.return_value
            response.status_code = 200
            response.json.return_value = {"id": "task-1"}

            result = odysseus._send_odysseus_request(spec, {"prompt": "Buy milk"})

        self.assertEqual(result, {"id": "task-1"})
        sent_json = client.request.call_args.kwargs["json"]
        self.assertEqual(sent_json["prompt"], "Buy milk")
        self.assertEqual(sent_json["schedule"], "once")
        self.assertEqual(sent_json["trigger_type"], "schedule")

    def test_prompts_route_todo_language_to_odysseus_tasks(self):
        import agent_friday
        from friday.desktop import brain

        for prompt in (agent_friday.SYSTEM_PROMPT, brain.SYSTEM_PROMPT):
            self.assertIn("to-do", prompt.lower())
            self.assertIn("tasks.create", prompt)
            self.assertIn("open.panel", prompt)


if __name__ == "__main__":
    unittest.main()
