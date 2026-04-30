# sync_airtable: CLI args, batching, empty records, chunk_text edges
from __future__ import annotations

import importlib
import os
import sys
import types
from unittest import TestCase
from unittest.mock import patch


def load_sync_module():
    sys.modules.pop("pbsbot.ingestion.sync_airtable", None)
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_certifi = types.SimpleNamespace(where=lambda: "/tmp/test-cert.pem")
    fake_requests = types.SimpleNamespace(Session=lambda: None)

    with patch.dict(
        sys.modules,
        {
            "certifi": fake_certifi,
            "dotenv": fake_dotenv,
            "requests": fake_requests,
        },
    ):
        return importlib.import_module("pbsbot.ingestion.sync_airtable")


class SyncMainCliTests(TestCase):
    def setUp(self) -> None:
        self.sync_mod = load_sync_module()

    def test_main_returns_error_when_base_id_is_missing(self) -> None:
        with patch.dict(
            os.environ,
            {"AIRTABLE_API_KEY": "key", "AIRTABLE_BASE_ID": ""},
            clear=True,
        ), patch("sys.argv", ["sync_airtable"]):
            result = self.sync_mod.main()

        self.assertEqual(result, 1)

    def test_main_returns_error_when_api_key_is_missing(self) -> None:
        with patch.dict(
            os.environ,
            {"AIRTABLE_BASE_ID": "base123", "AIRTABLE_API_KEY": ""},
            clear=True,
        ), patch("sys.argv", ["sync_airtable"]):
            result = self.sync_mod.main()

        self.assertEqual(result, 1)

    def test_main_single_table_passes_correct_args_to_sync(self) -> None:
        sync_calls: list[dict] = []

        def fake_sync(**kwargs):
            sync_calls.append(kwargs)
            return 0

        with patch.dict(
            os.environ,
            {
                "AIRTABLE_API_KEY": "key",
                "AIRTABLE_BASE_ID": "base123",
                "AIRTABLE_PROJECTS_TABLE_ID": "tblCustom",
                "CHROMA_PERSIST_DIR": "/tmp/chroma",
            },
            clear=True,
        ), patch("sys.argv", ["sync_airtable", "--reset"]), \
             patch.object(self.sync_mod, "sync", side_effect=fake_sync):
            result = self.sync_mod.main()

        self.assertEqual(result, 0)
        self.assertEqual(len(sync_calls), 1)
        self.assertTrue(sync_calls[0]["reset"])
        self.assertEqual(sync_calls[0]["table_id"], "tblCustom")
        self.assertEqual(sync_calls[0]["chroma_path"], "/tmp/chroma")
        # Non-default table_id → table_name is the table_id
        self.assertEqual(sync_calls[0]["table_name"], "tblCustom")

    def test_main_default_table_id_uses_projects_as_table_name(self) -> None:
        sync_calls: list[dict] = []

        def fake_sync(**kwargs):
            sync_calls.append(kwargs)
            return 0

        with patch.dict(
            os.environ,
            {
                "AIRTABLE_API_KEY": "key",
                "AIRTABLE_BASE_ID": "base123",
            },
            clear=True,
        ), patch("sys.argv", ["sync_airtable"]), \
             patch.object(self.sync_mod, "sync", side_effect=fake_sync):
            self.sync_mod.main()

        self.assertEqual(sync_calls[0]["table_name"], "Projects")

    def test_main_all_tables_calls_sync_per_table(self) -> None:
        sync_calls: list[dict] = []

        def fake_sync(**kwargs):
            sync_calls.append(kwargs)
            return 0

        tables = [
            {"id": "tbl1", "name": "Projects"},
            {"id": "tbl2", "name": "Tasks"},
            {"id": None, "name": "Empty"},  # Should be skipped
        ]

        with patch.dict(
            os.environ,
            {"AIRTABLE_API_KEY": "key", "AIRTABLE_BASE_ID": "base123"},
            clear=True,
        ), patch("sys.argv", ["sync_airtable", "--all-tables", "--reset"]), \
             patch.object(self.sync_mod, "fetch_tables_pyairtable", return_value=tables), \
             patch.object(self.sync_mod, "sync", side_effect=fake_sync):
            result = self.sync_mod.main()

        self.assertEqual(result, 0)
        self.assertEqual(len(sync_calls), 2)  # tbl with None id is skipped
        # First table gets reset=True, second gets reset=False
        self.assertTrue(sync_calls[0]["reset"])
        self.assertFalse(sync_calls[1]["reset"])
        self.assertEqual(sync_calls[0]["table_name"], "Projects")
        self.assertEqual(sync_calls[1]["table_name"], "Tasks")

    def test_main_all_tables_returns_error_when_no_tables_found(self) -> None:
        with patch.dict(
            os.environ,
            {"AIRTABLE_API_KEY": "key", "AIRTABLE_BASE_ID": "base123"},
            clear=True,
        ), patch("sys.argv", ["sync_airtable", "--all-tables"]), \
             patch.object(self.sync_mod, "fetch_tables_pyairtable", return_value=[]):
            result = self.sync_mod.main()

        self.assertEqual(result, 1)

    def test_main_chunk_size_and_overlap_args(self) -> None:
        sync_calls: list[dict] = []

        def fake_sync(**kwargs):
            sync_calls.append(kwargs)
            return 0

        with patch.dict(
            os.environ,
            {"AIRTABLE_API_KEY": "key", "AIRTABLE_BASE_ID": "base123"},
            clear=True,
        ), patch("sys.argv", ["sync_airtable", "--chunk-size", "800", "--chunk-overlap", "100"]), \
             patch.object(self.sync_mod, "sync", side_effect=fake_sync):
            self.sync_mod.main()

        self.assertEqual(sync_calls[0]["chunk_size_chars"], 800)
        self.assertEqual(sync_calls[0]["chunk_overlap_chars"], 100)


class SyncFunctionExtendedTests(TestCase):
    def setUp(self) -> None:
        self.sync_mod = load_sync_module()

    def test_sync_without_reset_does_not_delete_collection(self) -> None:
        upserts: list[dict] = []
        deletes: list[str] = []

        records = [{"id": "rec1", "fields": {"Name": "Alpha"}}]

        class FakeTable:
            def all(self):
                return records

        class FakeApi:
            def __init__(self, api_key):
                pass

            def table(self, base_id, table_id):
                return FakeTable()

        class FakeCollection:
            def upsert(self, *, ids, documents, metadatas):
                upserts.append({"ids": list(ids)})

            def count(self):
                return 1

        collection = FakeCollection()

        class FakeClient:
            def __init__(self, path):
                pass

            def delete_collection(self, name):
                deletes.append(name)

            def get_or_create_collection(self, *, name, embedding_function):
                return collection

        fake_pyairtable = types.SimpleNamespace(Api=FakeApi)
        fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "e")
        fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)
        fake_chromadb = types.SimpleNamespace(PersistentClient=FakeClient, utils=fake_utils)

        with patch.dict(
            sys.modules,
            {
                "pyairtable": fake_pyairtable,
                "chromadb": fake_chromadb,
                "chromadb.utils": fake_utils,
                "chromadb.utils.embedding_functions": fake_embedding_functions,
            },
        ), patch.dict("os.environ", {"AIRTABLE_API_KEY": "key"}, clear=True):
            result = self.sync_mod.sync(
                reset=False,
                chroma_path="/tmp/chroma",
                collection_name="pbs_projects",
                base_id="base123",
                table_id="tblProjects",
                table_name="Projects",
                chunk_size_chars=100,
                chunk_overlap_chars=0,
            )

        self.assertEqual(result, 0)
        self.assertEqual(deletes, [])
        self.assertEqual(len(upserts), 1)

    def test_sync_batches_when_exceeding_upsert_batch_size(self) -> None:
        upserts: list[dict] = []

        # Create enough records to trigger batching (UPSERT_BATCH=50)
        records = [
            {"id": f"rec{i}", "fields": {"Name": f"Record {i}"}}
            for i in range(60)
        ]

        class FakeTable:
            def all(self):
                return records

        class FakeApi:
            def __init__(self, api_key):
                pass

            def table(self, base_id, table_id):
                return FakeTable()

        class FakeCollection:
            def upsert(self, *, ids, documents, metadatas):
                upserts.append({"ids": list(ids), "count": len(ids)})

            def count(self):
                return sum(u["count"] for u in upserts)

        collection = FakeCollection()

        class FakeClient:
            def __init__(self, path):
                pass

            def get_or_create_collection(self, *, name, embedding_function):
                return collection

        fake_pyairtable = types.SimpleNamespace(Api=FakeApi)
        fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "e")
        fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)
        fake_chromadb = types.SimpleNamespace(PersistentClient=FakeClient, utils=fake_utils)

        with patch.dict(
            sys.modules,
            {
                "pyairtable": fake_pyairtable,
                "chromadb": fake_chromadb,
                "chromadb.utils": fake_utils,
                "chromadb.utils.embedding_functions": fake_embedding_functions,
            },
        ), patch.dict("os.environ", {"AIRTABLE_API_KEY": "key"}, clear=True):
            result = self.sync_mod.sync(
                reset=False,
                chroma_path="/tmp/chroma",
                collection_name="pbs_projects",
                base_id="base123",
                table_id="tblX",
                table_name="X",
                chunk_size_chars=10000,
                chunk_overlap_chars=0,
            )

        self.assertEqual(result, 0)
        # Should have at least 2 upsert calls: batch of 50 + remainder of 10
        self.assertGreaterEqual(len(upserts), 2)
        total_chunks = sum(u["count"] for u in upserts)
        self.assertEqual(total_chunks, 60)

    def test_sync_skips_empty_records(self) -> None:
        upserts: list[dict] = []

        records = [
            {"id": "rec1", "fields": {}},
            {"id": "rec2", "fields": {"Name": ""}},
            {"id": "rec3", "fields": {"Name": "Valid"}},
        ]

        class FakeTable:
            def all(self):
                return records

        class FakeApi:
            def __init__(self, api_key):
                pass

            def table(self, base_id, table_id):
                return FakeTable()

        class FakeCollection:
            def upsert(self, *, ids, documents, metadatas):
                upserts.append({"ids": list(ids)})

            def count(self):
                return 1

        collection = FakeCollection()

        class FakeClient:
            def __init__(self, path):
                pass

            def get_or_create_collection(self, *, name, embedding_function):
                return collection

        fake_pyairtable = types.SimpleNamespace(Api=FakeApi)
        fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "e")
        fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)
        fake_chromadb = types.SimpleNamespace(PersistentClient=FakeClient, utils=fake_utils)

        with patch.dict(
            sys.modules,
            {
                "pyairtable": fake_pyairtable,
                "chromadb": fake_chromadb,
                "chromadb.utils": fake_utils,
                "chromadb.utils.embedding_functions": fake_embedding_functions,
            },
        ), patch.dict("os.environ", {"AIRTABLE_API_KEY": "key"}, clear=True):
            result = self.sync_mod.sync(
                reset=False,
                chroma_path="/tmp/chroma",
                collection_name="pbs_projects",
                base_id="base123",
                table_id="tblX",
                table_name="X",
                chunk_size_chars=10000,
                chunk_overlap_chars=0,
            )

        self.assertEqual(result, 0)
        self.assertEqual(len(upserts), 1)
        self.assertEqual(upserts[0]["ids"], ["tblX:rec3:0"])


class FieldValueToTextExtendedTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync_mod = load_sync_module()

    def test_field_value_to_text_with_list_of_plain_dicts_without_name(self) -> None:
        result = self.sync_mod.field_value_to_text([{"id": "123"}, "visible"])
        self.assertEqual(result, "visible")

    def test_field_value_to_text_with_dict_no_name_no_email(self) -> None:
        self.assertIsNone(self.sync_mod.field_value_to_text({"url": "http://example.com"}))

    def test_field_value_to_text_with_float(self) -> None:
        self.assertEqual(self.sync_mod.field_value_to_text(3.14), "3.14")

    def test_field_value_to_text_with_boolean_false(self) -> None:
        self.assertEqual(self.sync_mod.field_value_to_text(False), "False")

    def test_record_to_document_with_none_fields(self) -> None:
        record = {"id": "rec1", "fields": None}
        self.assertIsNone(self.sync_mod.record_to_document(record))

    def test_record_to_document_with_mixed_field_types(self) -> None:
        record = {
            "id": "rec1",
            "fields": {
                "Name": "Show",
                "Count": 42,
                "Active": True,
                "Notes": None,
            },
        }

        parsed = self.sync_mod.record_to_document(record)

        self.assertIsNotNone(parsed)
        rec_id, doc = parsed
        self.assertEqual(rec_id, "rec1")
        self.assertIn("Name: Show", doc)
        self.assertIn("Count: 42", doc)
        self.assertIn("Active: True", doc)
        self.assertNotIn("Notes:", doc)


class ChunkTextExtendedTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync_mod = load_sync_module()

    def test_chunk_text_with_whitespace_only_returns_empty_string_chunk(self) -> None:
        result = self.sync_mod.chunk_text("   \n\t  ", chunk_size_chars=10, overlap_chars=2)
        self.assertEqual(result, [""])

    def test_chunk_text_preserves_content_across_chunks(self) -> None:
        text = "abcdefghijklmnopqrstuvwxyz"
        chunks = self.sync_mod.chunk_text(text, chunk_size_chars=10, overlap_chars=3)

        reconstructed = set()
        for chunk in chunks:
            for ch in chunk:
                reconstructed.add(ch)
        for ch in text:
            self.assertIn(ch, reconstructed)

    def test_chunk_text_large_overlap_produces_sliding_window(self) -> None:
        chunks = self.sync_mod.chunk_text("abcdefgh", chunk_size_chars=5, overlap_chars=4)
        # step = 5 - 4 = 1, so very fine-grained sliding
        self.assertGreater(len(chunks), 3)
