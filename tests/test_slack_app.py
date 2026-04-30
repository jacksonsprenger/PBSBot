# slack.app.run() wiring: dotenv, settings, chroma, state, bolt, socket mode
from __future__ import annotations

import importlib
import sys
import types
from unittest import TestCase
from unittest.mock import MagicMock, patch


def _make_external_stubs() -> dict:
    fake_dotenv = types.SimpleNamespace(load_dotenv=MagicMock())
    fake_bolt = types.SimpleNamespace(App=MagicMock)
    fake_socket_mod = types.SimpleNamespace(SocketModeHandler=MagicMock())
    fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "embedder")
    fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)
    fake_chromadb = types.SimpleNamespace(
        PersistentClient=MagicMock,
        errors=types.SimpleNamespace(InternalError=Exception),
    )
    return {
        "dotenv": fake_dotenv,
        "slack_bolt": fake_bolt,
        "slack_bolt.adapter": types.SimpleNamespace(),
        "slack_bolt.adapter.socket_mode": fake_socket_mod,
        "chromadb": fake_chromadb,
        "chromadb.errors": fake_chromadb.errors,
        "chromadb.utils": fake_utils,
        "chromadb.utils.embedding_functions": fake_embedding_functions,
        "certifi": types.SimpleNamespace(where=lambda: "/tmp/cert.pem"),
    }


def load_app_module():
    # Clear cached modules to get a clean import
    for key in list(sys.modules):
        if key.startswith("pbsbot.slack.app") or key.startswith("pbsbot.chroma"):
            sys.modules.pop(key, None)

    with patch.dict(sys.modules, _make_external_stubs()):
        return importlib.import_module("pbsbot.slack.app")


class SlackAppRunTests(TestCase):

    def test_run_initializes_all_components_in_order(self) -> None:
        module = load_app_module()

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

        with patch.object(module, "load_dotenv") as mock_dotenv, \
             patch.object(module, "load_settings", return_value=fake_settings) as mock_load, \
             patch.object(module, "configure_runtime") as mock_runtime, \
             patch.object(module, "ChromaStore", return_value=fake_store) as mock_chroma, \
             patch.object(module, "state") as mock_state, \
             patch.object(module, "App", return_value=fake_app) as mock_app_cls, \
             patch.object(module, "register") as mock_register, \
             patch.object(module, "SocketModeHandler", return_value=fake_handler) as mock_handler_cls, \
             patch("builtins.print"):

            module.run()

        mock_dotenv.assert_called_once()
        mock_load.assert_called_once()
        mock_runtime.assert_called_once_with("INFO")
        mock_chroma.assert_called_once_with(fake_settings)
        mock_state.init.assert_called_once_with(fake_settings, fake_store)
        mock_app_cls.assert_called_once_with(token="xoxb-test")
        mock_register.assert_called_once_with(fake_app)
        mock_handler_cls.assert_called_once_with(fake_app, "xapp-test")
        fake_handler.start.assert_called_once()
