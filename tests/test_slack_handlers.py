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


class SlackHandlerTests(TestCase):
    def setUp(self) -> None:
        self.handlers_mod = load_handlers_module()
        self.handlers_mod.pending_confirmations.clear()
        self.app = FakeBoltApp()
        self.handlers_mod.register(self.app)

    def tearDown(self) -> None:
        self.handlers_mod.pending_confirmations.clear()

    def test_app_mention_normalizes_text_and_mentions_user_in_reply(self) -> None:
        sent: list[str] = []

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="answer",
        ) as flow:
            self.app.handlers["app_mention"](
                {"user": "U1", "channel": "C1", "text": "<@BOT>  What tasks are due?"},
                sent.append,
            )

        flow.assert_called_once_with("U1", "C1", "What tasks are due?")
        self.assertEqual(sent, ["<@U1>\nanswer"])

    def test_dm_message_runs_full_query_flow(self) -> None:
        sent: list[str] = []

        with patch.object(
            self.handlers_mod,
            "handle_user_query_flow",
            return_value="dm answer",
        ) as flow:
            self.app.handlers["message"](
                {
                    "user": "U1",
                    "channel": "D1",
                    "text": "status?",
                    "channel_type": "im",
                },
                sent.append,
            )

        flow.assert_called_once_with("U1", "D1", "status?")
        self.assertEqual(sent, ["<@U1>\ndm answer"])

    def test_bot_and_subtype_messages_are_ignored(self) -> None:
        sent: list[str] = []

        with patch.object(self.handlers_mod, "handle_user_query_flow") as flow:
            self.app.handlers["message"]({"bot_id": "B1", "text": "ignore"}, sent.append)
            self.app.handlers["message"]({"subtype": "message_changed", "text": "ignore"}, sent.append)

        flow.assert_not_called()
        self.assertEqual(sent, [])

    def test_channel_message_without_pending_confirmation_is_ignored(self) -> None:
        sent: list[str] = []

        with patch.object(self.handlers_mod, "handle_user_query_flow") as flow:
            self.app.handlers["message"](
                {
                    "user": "U1",
                    "channel": "C1",
                    "text": "yes",
                    "channel_type": "channel",
                },
                sent.append,
            )

        flow.assert_not_called()
        self.assertEqual(sent, [])

    def test_channel_pending_message_that_is_not_yes_or_no_is_ignored(self) -> None:
        sent: list[str] = []
        self.handlers_mod.pending_confirmations["C1:U1"] = {"query_for_search": "status"}

        with patch.object(self.handlers_mod, "handle_user_query_flow") as flow:
            self.app.handlers["message"](
                {
                    "user": "U1",
                    "channel": "C1",
                    "text": "tell me more",
                    "channel_type": "channel",
                },
                sent.append,
            )

        flow.assert_not_called()
        self.assertEqual(sent, [])

    def test_channel_pending_yes_or_no_message_runs_query_flow(self) -> None:
        for text in ("yes", "no"):
            with self.subTest(text=text):
                sent: list[str] = []
                self.handlers_mod.pending_confirmations["C1:U1"] = {"query_for_search": "status"}

                with patch.object(
                    self.handlers_mod,
                    "handle_user_query_flow",
                    return_value=f"{text} answer",
                ) as flow:
                    self.app.handlers["message"](
                        {
                            "user": "U1",
                            "channel": "C1",
                            "text": text,
                            "channel_type": "channel",
                        },
                        sent.append,
                    )

                flow.assert_called_once_with("U1", "C1", text)
                self.assertEqual(sent, [f"<@U1>\n{text} answer"])

