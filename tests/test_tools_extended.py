"""Extended tests for tools/ — verify_chroma_tables edge cases and llm_connect units."""

from __future__ import annotations

import importlib
import io
import json
import sys
import types
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import patch


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def load_verify_module(collection):
    sys.modules.pop("tools.verify_chroma_tables", None)
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "embedder")
    fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_collection(self, name, embedding_function):
            collection.requested_name = name
            return collection

    fake_chromadb = types.SimpleNamespace(PersistentClient=FakeClient)

    with patch.dict(
        sys.modules,
        {
            "dotenv": fake_dotenv,
            "chromadb": fake_chromadb,
            "chromadb.utils": fake_utils,
            "chromadb.utils.embedding_functions": fake_embedding_functions,
        },
    ):
        return importlib.import_module("tools.verify_chroma_tables")


def load_llm_connect_module():
    sys.modules.pop("tools.llm_connect", None)
    fake_paramiko = types.SimpleNamespace(
        SSHClient=object,
        AutoAddPolicy=object,
        AuthenticationException=Exception,
        SSHException=Exception,
    )

    with patch.dict(sys.modules, {"paramiko": fake_paramiko}):
        return importlib.import_module("tools.llm_connect")


class VerifyChromaTablesExtendedTests(TestCase):
    def test_handles_none_metadata_entries(self) -> None:
        class CollectionWithNones:
            def count(self):
                return 3

            def get(self, *, include, limit, offset):
                return {
                    "metadatas": [
                        None,
                        {"table_id": "tbl1", "table_name": "Projects"},
                        None,
                    ]
                }

        collection = CollectionWithNones()
        module = load_verify_module(collection)
        out = io.StringIO()

        with patch.dict("os.environ", {}, clear=True), redirect_stdout(out):
            result = module.main()

        self.assertEqual(result, 0)
        self.assertIn("tbl1: 1 chunks", out.getvalue())

    def test_handles_metadata_with_missing_table_id(self) -> None:
        class CollectionWithMissingId:
            def count(self):
                return 2

            def get(self, *, include, limit, offset):
                return {
                    "metadatas": [
                        {"table_name": "Unknown"},
                        {"table_id": "tbl1", "table_name": "Projects"},
                    ]
                }

        collection = CollectionWithMissingId()
        module = load_verify_module(collection)
        out = io.StringIO()

        with patch.dict("os.environ", {}, clear=True), redirect_stdout(out):
            result = module.main()

        self.assertEqual(result, 0)
        text = out.getvalue()
        self.assertIn("?: 1 chunks", text)
        self.assertIn("tbl1: 1 chunks", text)

    def test_handles_empty_metadata_list_in_get_response(self) -> None:
        class CollectionWithEmptyGet:
            def count(self):
                return 5

            def get(self, *, include, limit, offset):
                return {"metadatas": []}

        collection = CollectionWithEmptyGet()
        module = load_verify_module(collection)
        out = io.StringIO()

        with patch.dict("os.environ", {}, clear=True), redirect_stdout(out):
            result = module.main()

        self.assertEqual(result, 0)
        # Should exit loop early without crashing
        self.assertIn("Total chunks: 5", out.getvalue())

    def test_uses_env_vars_for_paths(self) -> None:
        class SimpleCollection:
            def count(self):
                return 0

        collection = SimpleCollection()
        module = load_verify_module(collection)
        out = io.StringIO()

        with patch.dict(
            "os.environ",
            {"CHROMA_PERSIST_DIR": "/custom/path", "CHROMA_COLLECTION_NAME": "custom_col"},
            clear=True,
        ), redirect_stdout(out):
            module.main()

        text = out.getvalue()
        self.assertIn("'/custom/path'", text)
        self.assertIn("'custom_col'", text)


class LlmConnectExtendedTests(TestCase):
    def test_prompt_llm_handles_empty_response(self) -> None:
        module = load_llm_connect_module()
        payload = json.dumps({"response": ""}).encode()

        with patch.object(
            module.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            result = module.prompt_llm("hello")

        self.assertEqual(result, "")

    def test_prompt_llm_handles_missing_response_key(self) -> None:
        module = load_llm_connect_module()
        payload = json.dumps({"model": "test"}).encode()

        with patch.object(
            module.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            result = module.prompt_llm("hello")

        self.assertEqual(result, "")

    def test_forward_handler_factory_returns_handler_class(self) -> None:
        module = load_llm_connect_module()
        mock_transport = types.SimpleNamespace()

        handler_class = module._forward_handler_factory(mock_transport, "localhost", 11434)

        self.assertTrue(callable(handler_class))
        self.assertEqual(handler_class.__name__, "ForwardHandler")

    def test_start_tunnel_returns_server_object(self) -> None:
        module = load_llm_connect_module()

        class FakeTransport:
            pass

        class FakeSSHClient:
            def get_transport(self):
                return FakeTransport()

        # Use a random high port to avoid conflicts
        with patch.object(module, "_forward_handler_factory", return_value=type(
            "Handler", (), {"handle": lambda self: None}
        )):
            server = module.start_tunnel(FakeSSHClient(), 0, "localhost", 11434)

        try:
            self.assertIsNotNone(server)
        finally:
            server.shutdown()
