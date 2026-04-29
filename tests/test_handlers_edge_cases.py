"""Edge-case tests for pbsbot.slack.handlers beyond the happy paths."""

from __future__ import annotations

import importlib
import sys
import types
from unittest import TestCase
from unittest.mock import patch


def load_handlers_module():
    sys.modules.pop("pbsbot.slack.handlers", None)
    fake_slack_bolt = types.SimpleNamespace(App=object)
    with patch.dict(sys.modules, {"slack_bolt": fake_slack_bolt}):
        return importlib.import_module("pbsbot.slack.handlers")


class FakeBoltApp:
    def __init__(self) -> None:
        self.handlers = {}

    def event(self, event_name):
        def decorator(fn):
            self.handlers[event_name] = fn
            return fn
        return decorator


class HandlersEdgeCaseTests(TestCase):
    def setUp(self) -> None:
        self.handlers_mod = load_handlers_module()
        self.handlers_mod.pending_confirmations.clear()
        self.app = FakeBoltApp()
        self.handlers_mod.register(self.app)

    def tearDown(self) -> None:
        self.handlers_mod.pending_confirmations.clear()

    # ── app_mention edge cases ───────────────────────────────────────

    def test_app_mention_with_none_text_does_not_crash(self) -> None:
        sent: list[str] = []

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="answer",
        ):
            self.app.handlers["app_mention"](
                {"user": "U1", "channel": "C1", "text": None},
                sent.append,
            )

        self.assertEqual(len(sent), 1)

    def test_app_mention_with_missing_channel_key(self) -> None:
        sent: list[str] = []

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="answer",
        ) as flow:
            self.app.handlers["app_mention"](
                {"user": "U1", "text": "<@BOT> hello"},
                sent.append,
            )

        flow.assert_called_once_with("U1", None, "hello")
        self.assertEqual(sent, ["<@U1>\nanswer"])

    # ── message handler: channel_type="group" ────────────────────────

    def test_group_channel_type_with_pending_yes_runs_flow(self) -> None:
        sent: list[str] = []
        self.handlers_mod.pending_confirmations["G1:U1"] = {"query_for_search": "q"}

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="group answer",
        ) as flow:
            self.app.handlers["message"](
                {
                    "user": "U1",
                    "channel": "G1",
                    "text": "yes",
                    "channel_type": "group",
                },
                sent.append,
            )

        flow.assert_called_once_with("U1", "G1", "yes")
        self.assertEqual(sent, ["<@U1>\ngroup answer"])

    # ── message handler: channel_type="" (empty string) ──────────────

    def test_empty_string_channel_type_with_pending_runs_flow(self) -> None:
        sent: list[str] = []
        self.handlers_mod.pending_confirmations["C2:U2"] = {"query_for_search": "q"}

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="empty-type answer",
        ) as flow:
            self.app.handlers["message"](
                {
                    "user": "U2",
                    "channel": "C2",
                    "text": "no",
                    "channel_type": "",
                },
                sent.append,
            )

        flow.assert_called_once_with("U2", "C2", "no")
        self.assertEqual(sent, ["<@U2>\nempty-type answer"])

    def test_empty_string_channel_type_without_pending_is_ignored(self) -> None:
        sent: list[str] = []

        with patch.object(self.handlers_mod, "handle_user_query_flow") as flow:
            self.app.handlers["message"](
                {
                    "user": "U2",
                    "channel": "C2",
                    "text": "hello",
                    "channel_type": "",
                },
                sent.append,
            )

        flow.assert_not_called()
        self.assertEqual(sent, [])

    # ── message handler: missing optional fields ─────────────────────

    def test_message_with_none_text_in_dm_does_not_crash(self) -> None:
        sent: list[str] = []

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="answer",
        ) as flow:
            self.app.handlers["message"](
                {
                    "user": "U1",
                    "channel": "D1",
                    "text": None,
                    "channel_type": "im",
                },
                sent.append,
            )

        flow.assert_called_once_with("U1", "D1", "")
        self.assertEqual(sent, ["<@U1>\nanswer"])

    def test_message_with_missing_channel_type_key(self) -> None:
        """When channel_type key is absent, message.get returns '' which is in the tuple."""
        sent: list[str] = []
        self.handlers_mod.pending_confirmations["C1:U1"] = {"query_for_search": "q"}

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="answer",
        ) as flow:
            self.app.handlers["message"](
                {"user": "U1", "channel": "C1", "text": "yes"},
                sent.append,
            )

        flow.assert_called_once_with("U1", "C1", "yes")

    # ── message handler: bot_id present but falsy ────────────────────

    def test_message_with_empty_bot_id_is_not_ignored(self) -> None:
        """An empty-string bot_id is falsy, so the message should not be ignored."""
        sent: list[str] = []

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="dm answer",
        ) as flow:
            self.app.handlers["message"](
                {
                    "bot_id": "",
                    "user": "U1",
                    "channel": "D1",
                    "text": "hello",
                    "channel_type": "im",
                },
                sent.append,
            )

        flow.assert_called_once()
