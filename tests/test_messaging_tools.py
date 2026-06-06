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

    def test_confirm_pending_action_can_use_latest_pending_message(self):
        first = messaging.prepare_outbound_message(
            channel="messages",
            recipient="First",
            message="Older.",
        )
        second = messaging.prepare_outbound_message(
            channel="messages",
            recipient="Second",
            message="Newer.",
        )

        with patch("friday.tools.messaging._send_apple_message", return_value="sent") as send:
            result = messaging.confirm_pending_action()

        send.assert_called_once_with("Second", "Newer.")
        self.assertEqual(result["action_id"], second["action_id"])
        self.assertIn(first["action_id"], messaging.PENDING_ACTIONS)
        self.assertNotIn(second["action_id"], messaging.PENDING_ACTIONS)

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

    def test_messages_contact_name_is_resolved_before_send(self):
        with (
            patch("friday.tools.messaging._lookup_contact_handle", return_value="+15551234567") as lookup,
            patch("friday.tools.messaging._send_messages_handle", return_value="Sent through Apple Messages.") as send,
        ):
            result = messaging._send_apple_message("Dhruv", "Testing.")

        lookup.assert_called_once_with("Dhruv")
        send.assert_called_once_with("+15551234567", "Testing.")
        self.assertIn("Sent", result)

    def test_messages_send_falls_back_from_imessage_to_sms(self):
        with patch("friday.tools.messaging._osascript") as run:
            run.side_effect = [RuntimeError("iMessage failed"), None]
            result = messaging._send_messages_handle("+15551234567", "Testing.")

        self.assertEqual(run.call_count, 2)
        self.assertIn("SMS", result)

    def test_messages_send_opens_draft_when_direct_send_fails(self):
        with (
            patch("friday.tools.messaging._osascript", side_effect=RuntimeError("send failed")),
            patch("friday.tools.messaging.webbrowser.open") as open_url,
        ):
            result = messaging._send_messages_handle("+15551234567", "Testing.")

        open_url.assert_called_once()
        self.assertIn("sms:", open_url.call_args.args[0])
        self.assertIn("Opened Messages draft", result)


if __name__ == "__main__":
    unittest.main()
