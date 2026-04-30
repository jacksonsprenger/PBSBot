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
            collection.embedding_function = embedding_function
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


class VerifyChromaTablesToolTests(TestCase):
    def test_verify_chroma_tables_prints_empty_collection_summary(self) -> None:
        class EmptyCollection:
            def count(self):
                return 0

        collection = EmptyCollection()
        module = load_verify_module(collection)
        out = io.StringIO()

        with patch.dict("os.environ", {"CHROMA_PERSIST_DIR": "/tmp/chroma", "CHROMA_COLLECTION_NAME": "pbs"}, clear=True), redirect_stdout(out):
            result = module.main()

        self.assertEqual(result, 0)
        self.assertIn("Collection: 'pbs'  path: '/tmp/chroma'", out.getvalue())
        self.assertIn("Total chunks: 0", out.getvalue())
        self.assertEqual(collection.requested_name, "pbs")
        self.assertEqual(collection.embedding_function, "embedder")

    def test_verify_chroma_tables_counts_chunks_by_table_id(self) -> None:
        class PopulatedCollection:
            def count(self):
                return 3

            def get(self, *, include, limit, offset):
                self.last_get = {"include": include, "limit": limit, "offset": offset}
                return {
                    "metadatas": [
                        {"table_id": "tblProjects", "table_name": "Projects"},
                        {"table_id": "tblProjects", "table_name": "Projects"},
                        {"table_id": "tblTasks", "table_name": "Tasks"},
                    ]
                }

        collection = PopulatedCollection()
        module = load_verify_module(collection)
        out = io.StringIO()

        with patch.dict("os.environ", {}, clear=True), redirect_stdout(out):
            result = module.main()

        self.assertEqual(result, 0)
        text = out.getvalue()
        self.assertIn("Distinct tables (by table_id): 2", text)
        self.assertIn("tblProjects: 2 chunks  (Projects)", text)
        self.assertIn("tblTasks: 1 chunks  (Tasks)", text)
        self.assertEqual(collection.last_get, {"include": ["metadatas"], "limit": 3, "offset": 0})


class LlmConnectToolTests(TestCase):
    def test_prompt_llm_posts_to_local_ollama_endpoint(self) -> None:
        module = load_llm_connect_module()
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["headers"] = dict(req.header_items())
            captured["timeout"] = timeout
            return FakeResponse(b'{"response": "  answer text  "}')

        with patch.object(module, "LOCAL_PORT", 11555), patch.object(
            module,
            "MODEL",
            "test-model",
        ), patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            out = module.prompt_llm("hello")

        self.assertEqual(out, "answer text")
        self.assertEqual(captured["url"], "http://localhost:11555/api/generate")
        self.assertEqual(
            captured["body"],
            {"model": "test-model", "prompt": "hello", "stream": False},
        )
        self.assertEqual(captured["headers"]["Content-type"], "application/json")
        self.assertEqual(captured["timeout"], 120)
