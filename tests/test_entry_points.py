"""Tests for entry points: main.py and pbsbot/__main__.py."""

from __future__ import annotations

import importlib
import sys
import types
from unittest import TestCase
from unittest.mock import MagicMock, patch


def _make_external_stubs() -> dict:
    """Fake modules for importing app.py and its transitive dependencies."""
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


def _clear_app_modules():
    for key in list(sys.modules):
        if key in ("main", "pbsbot.__main__") or key.startswith("pbsbot.slack.app") or key.startswith("pbsbot.chroma"):
            sys.modules.pop(key, None)


class MainEntryPointTests(TestCase):
    def test_main_py_imports_run_from_slack_app(self) -> None:
        _clear_app_modules()

        with patch.dict(sys.modules, _make_external_stubs()):
            module = importlib.import_module("main")
            app_module = importlib.import_module("pbsbot.slack.app")

        self.assertIs(module.run, app_module.run)

    def test_dunder_main_imports_run_from_slack_app(self) -> None:
        _clear_app_modules()

        with patch.dict(sys.modules, _make_external_stubs()):
            module = importlib.import_module("pbsbot.__main__")
            app_module = importlib.import_module("pbsbot.slack.app")

        self.assertIs(module.run, app_module.run)
