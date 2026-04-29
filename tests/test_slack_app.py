"""Tests for pbsbot.slack.app — the run() startup wiring."""

from __future__ import annotations

import importlib
import sys
import types
from unittest import TestCase
from unittest.mock import MagicMock, call, patch


def _build_fake_modules():
    """Return a dict of fake modules needed to import pbsbot.slack.app cleanly."""
    fake_dotenv = types.SimpleNamespace(load_dotenv=MagicMock())
    fake_bolt = types.SimpleNamespace(App=MagicMock)
    fake_socket = types.SimpleNamespace(SocketModeHandler=MagicMock())
    return {
        "dotenv": fake_dotenv,
        "slack_bolt": fake_bolt,
        "slack_bolt.adapter": types.SimpleNamespace(),
        "slack_bolt.adapter.socket_mode": fake_socket,
    }


class SlackAppRunTests(TestCase):
    """Verify that run() wires settings, ChromaStore, state, handlers, and starts Socket Mode."""

    def test_run_initializes_all_components_in_order(self) -> None:
        fake_settings = MagicMock(
            name="settings",
            log_level="INFO",
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
        )
        fake_store = MagicMock(name="store")
        fake_app = MagicMock(name="app")
        fake_handler = MagicMock(name="handler")

        with patch("pbsbot.slack.app.load_dotenv") as mock_dotenv, \
             patch("pbsbot.slack.app.load_settings", return_value=fake_settings) as mock_load, \
             patch("pbsbot.slack.app.configure_runtime") as mock_runtime, \
             patch("pbsbot.slack.app.ChromaStore", return_value=fake_store) as mock_chroma, \
             patch("pbsbot.slack.app.state") as mock_state, \
             patch("pbsbot.slack.app.App", return_value=fake_app) as mock_app_cls, \
             patch("pbsbot.slack.app.register") as mock_register, \
             patch("pbsbot.slack.app.SocketModeHandler", return_value=fake_handler) as mock_handler_cls, \
             patch("builtins.print"):

            from pbsbot.slack.app import run
            run()

        mock_dotenv.assert_called_once()
        mock_load.assert_called_once()
        mock_runtime.assert_called_once_with("INFO")
        mock_chroma.assert_called_once_with(fake_settings)
        mock_state.init.assert_called_once_with(fake_settings, fake_store)
        mock_app_cls.assert_called_once_with(token="xoxb-test")
        mock_register.assert_called_once_with(fake_app)
        mock_handler_cls.assert_called_once_with(fake_app, "xapp-test")
        fake_handler.start.assert_called_once()
