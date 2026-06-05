import time
import unittest
from unittest.mock import patch

from friday.tools import messaging


class MessagingToolTests(unittest.TestCase):
    def setUp(self):
        messaging.clear_pending_actions()

    def tearDown(self):
        messaging.clear_pending_actions()

    def test_prepare_message_creates_pending_action_without_sending(self):
        with patch("friday.tools.messaging._execute_message_action") as execute:
            result = messaging.prepare_outbound_message(
                channel="messages",
                recipient="Dhruv",
                message="I will call back in 10 minutes.",
            )

        execute.assert_not_called()
        self.assertEqual(result["status"], "pending_confirmation")
        self.assertEqual(result["risk"], "send_message")
        self.assertIn("action_id", result)

    def test_confirm_pending_action_executes_once(self):
        prepared = messaging.prepare_outbound_message(
            channel="messages",
            recipient="Dhruv",
            message="Testing.",
        )

        with patch("friday.tools.messaging._send_apple_message", return_value="sent") as send:
            result = messaging.confirm_pending_action(prepared["action_id"])

        send.assert_called_once_with("Dhruv", "Testing.")
        self.assertEqual(result["status"], "executed")

        with self.assertRaises(KeyError):
            messaging.confirm_pending_action(prepared["action_id"])

    def test_expired_pending_action_is_rejected(self):
        prepared = messaging.prepare_outbound_message(
            channel="messages",
            recipient="Dhruv",
            message="Testing.",
        )
        messaging.PENDING_ACTIONS[prepared["action_id"]].created_at = time.time() - 999

        with self.assertRaises(TimeoutError):
            messaging.confirm_pending_action(prepared["action_id"])

    def test_secret_like_message_is_rejected(self):
        with self.assertRaises(ValueError):
            messaging.prepare_outbound_message(
                channel="messages",
                recipient="Dhruv",
                message="OPENAI_API_KEY=sk-test-secret",
            )

    def test_unsupported_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            messaging.prepare_outbound_message(
                channel="telegram",
                recipient="Dhruv",
                message="Hello",
            )

    def test_whatsapp_confirmation_opens_draft_url(self):
        prepared = messaging.prepare_outbound_message(
            channel="whatsapp",
            recipient="+15551234567",
            message="Hello there",
        )

        with patch("friday.tools.messaging.webbrowser.open") as open_url:
            result = messaging.confirm_pending_action(prepared["action_id"])

        open_url.assert_called_once()
        self.assertIn("whatsapp://send", open_url.call_args.args[0])
        self.assertEqual(result["status"], "executed")

    def test_slack_and_email_prepare_drafts_not_direct_sends(self):
        for channel in ("slack", "email"):
            with self.subTest(channel=channel):
                prepared = messaging.prepare_outbound_message(
                    channel=channel,
                    recipient="person@example.com",
                    message="Hello",
                )
                with patch("friday.tools.messaging.webbrowser.open") as open_url:
                    result = messaging.confirm_pending_action(prepared["action_id"])
                open_url.assert_called()
                self.assertIn("draft", result["result"].lower())


if __name__ == "__main__":
    unittest.main()
