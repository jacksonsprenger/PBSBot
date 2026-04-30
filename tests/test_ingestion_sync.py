from __future__ import annotations

import importlib
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


class AirtableSyncTransformTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync_mod = load_sync_module()

    def test_field_value_to_text_skips_empty_values(self) -> None:
        self.assertIsNone(self.sync_mod.field_value_to_text(None))
        self.assertIsNone(self.sync_mod.field_value_to_text(""))
        self.assertIsNone(self.sync_mod.field_value_to_text([]))

    def test_field_value_to_text_flattens_airtable_shapes(self) -> None:
        self.assertEqual(
            self.sync_mod.field_value_to_text([{"name": "Producer"}, "raw-id", {"email": "ignored"}]),
            "Producer, raw-id",
        )
        self.assertEqual(
            self.sync_mod.field_value_to_text({"name": "Jane Producer", "email": "jane@example.com"}),
            "Jane Producer",
        )
        self.assertEqual(
            self.sync_mod.field_value_to_text({"email": "contact@example.com"}),
            "contact@example.com",
        )
        self.assertEqual(self.sync_mod.field_value_to_text(True), "True")
        self.assertEqual(self.sync_mod.field_value_to_text(42), "42")

    def test_field_value_to_text_skips_dicts_without_supported_display_fields(self) -> None:
        self.assertIsNone(self.sync_mod.field_value_to_text({"id": "usr123"}))
        self.assertIsNone(self.sync_mod.field_value_to_text([{"email": "ignored@example.com"}]))

    def test_record_to_document_skips_empty_fields_and_preserves_labels(self) -> None:
        record = {
            "id": "rec123",
            "fields": {
                "Project Name": "Nature Show",
                "Empty": "",
                "Owner": {"name": "Jane"},
                "Tags": [{"name": "Promo"}, "Web"],
            },
        }

        parsed = self.sync_mod.record_to_document(record)

        self.assertEqual(
            parsed,
            (
                "rec123",
                "Project Name: Nature Show\nOwner: Jane\nTags: Promo, Web",
            ),
        )

    def test_record_to_document_returns_none_for_empty_records(self) -> None:
        self.assertIsNone(self.sync_mod.record_to_document({"id": "rec1", "fields": {}}))
        self.assertIsNone(self.sync_mod.record_to_document({"id": "rec1", "fields": {"A": ""}}))

    def test_chunk_text_handles_short_empty_and_overlapping_text(self) -> None:
        self.assertEqual(
            self.sync_mod.chunk_text("", chunk_size_chars=4, overlap_chars=1),
            [],
        )
        self.assertEqual(
            self.sync_mod.chunk_text(" abc ", chunk_size_chars=10, overlap_chars=2),
            ["abc"],
        )
        self.assertEqual(
            self.sync_mod.chunk_text("abcdefghij", chunk_size_chars=4, overlap_chars=1),
            ["abcd", "defg", "ghij"],
        )

    def test_chunk_text_exact_chunk_size_returns_single_chunk(self) -> None:
        self.assertEqual(
            self.sync_mod.chunk_text("abcd", chunk_size_chars=4, overlap_chars=2),
            ["abcd"],
        )

    def test_chunk_text_without_overlap_uses_adjacent_windows(self) -> None:
        self.assertEqual(
            self.sync_mod.chunk_text("abcdef", chunk_size_chars=3, overlap_chars=0),
            ["abc", "def"],
        )

    def test_chunk_text_clamps_overlap_to_avoid_zero_step(self) -> None:
        self.assertEqual(
            self.sync_mod.chunk_text("abcde", chunk_size_chars=3, overlap_chars=99),
            ["abc", "bcd", "cde"],
        )


class AirtableSyncIntegrationShapeTests(TestCase):
    def setUp(self) -> None:
        self.sync_mod = load_sync_module()

    def test_fetch_tables_metadata_uses_airtable_metadata_endpoint(self) -> None:
        calls: list[dict] = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                calls.append({"raised": True})

            def json(self) -> dict:
                return {"tables": [{"id": "tbl1", "name": "Projects"}]}

        class FakeSession:
            trust_env = True

            def get(self, url, *, headers, timeout):
                calls.append(
                    {
                        "url": url,
                        "headers": headers,
                        "timeout": timeout,
                        "trust_env": self.trust_env,
                    }
                )
                return FakeResponse()

        with patch.object(self.sync_mod.requests, "Session", return_value=FakeSession()):
            tables = self.sync_mod.fetch_tables_metadata("base123", api_key="key123")

        self.assertEqual(tables, [{"id": "tbl1", "name": "Projects"}])
        self.assertEqual(calls[0]["url"], "https://api.airtable.com/v0/meta/bases/base123/tables")
        self.assertEqual(calls[0]["headers"], {"Authorization": "Bearer key123"})
        self.assertEqual(calls[0]["timeout"], 60)
        self.assertFalse(calls[0]["trust_env"])

    def test_fetch_tables_metadata_returns_empty_list_when_response_has_no_tables_key(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {}

        class FakeSession:
            def get(self, url, *, headers, timeout):
                return FakeResponse()

        with patch.object(self.sync_mod.requests, "Session", return_value=FakeSession()):
            tables = self.sync_mod.fetch_tables_metadata("base123", api_key="key123")

        self.assertEqual(tables, [])

    def test_fetch_tables_pyairtable_handles_missing_table_name(self) -> None:
        class FakeTable:
            id = "tbl1"

        class FakeBase:
            def tables(self):
                return [FakeTable()]

        class FakeApi:
            def __init__(self, api_key):
                self.api_key = api_key

            def base(self, base_id):
                return FakeBase()

        with patch.dict(sys.modules, {"pyairtable": types.SimpleNamespace(Api=FakeApi)}):
            tables = self.sync_mod.fetch_tables_pyairtable("base123", api_key="key123")

        self.assertEqual(tables, [{"id": "tbl1", "name": None}])

    def test_sync_upserts_deterministic_chunk_ids_and_metadata(self) -> None:
        upserts: list[dict] = []
        deletes: list[str] = []

        records = [
            {"id": "rec1", "fields": {"Name": "Alpha", "Owner": {"name": "Jane"}}},
            {"id": "rec2", "fields": {"Name": "Beta"}},
        ]

        class FakeTable:
            def all(self):
                return records

        class FakeApi:
            def __init__(self, api_key):
                self.api_key = api_key

            def table(self, base_id, table_id):
                self.base_id = base_id
                self.table_id = table_id
                return FakeTable()

        class FakeCollection:
            def upsert(self, *, ids, documents, metadatas):
                upserts.append(
                    {
                        "ids": list(ids),
                        "documents": list(documents),
                        "metadatas": list(metadatas),
                    }
                )

            def count(self):
                return sum(len(batch["ids"]) for batch in upserts)

        collection = FakeCollection()

        class FakeClient:
            def __init__(self, path):
                self.path = path

            def delete_collection(self, name):
                deletes.append(name)

            def get_or_create_collection(self, *, name, embedding_function):
                self.name = name
                self.embedding_function = embedding_function
                return collection

        fake_pyairtable = types.SimpleNamespace(Api=FakeApi)
        fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "embedder")
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
                reset=True,
                chroma_path="/tmp/chroma",
                collection_name="pbs_projects",
                base_id="base123",
                table_id="tblTasks",
                table_name="Tasks",
                chunk_size_chars=100,
                chunk_overlap_chars=0,
            )

        self.assertEqual(result, 0)
        self.assertEqual(deletes, ["pbs_projects"])
        self.assertEqual(upserts[0]["ids"], ["tblTasks:rec1:0", "tblTasks:rec2:0"])
        self.assertEqual(
            upserts[0]["metadatas"],
            [
                {
                    "source": "airtable",
                    "table_id": "tblTasks",
                    "table_name": "Tasks",
                    "record_id": "rec1",
                    "chunk_index": 0,
                },
                {
                    "source": "airtable",
                    "table_id": "tblTasks",
                    "table_name": "Tasks",
                    "record_id": "rec2",
                    "chunk_index": 0,
                },
            ],
        )

    def test_sync_returns_error_when_required_env_is_missing(self) -> None:
        fake_pyairtable = types.SimpleNamespace(Api=object)
        fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "embedder")
        fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)
        fake_chromadb = types.SimpleNamespace(PersistentClient=object, utils=fake_utils)

        with patch.dict(
            sys.modules,
            {
                "pyairtable": fake_pyairtable,
                "chromadb": fake_chromadb,
                "chromadb.utils": fake_utils,
                "chromadb.utils.embedding_functions": fake_embedding_functions,
            },
        ), patch.dict("os.environ", {}, clear=True):
            result = self.sync_mod.sync(
                reset=False,
                chroma_path="/tmp/chroma",
                collection_name="pbs_projects",
                base_id="",
                table_id="tblProjects",
                table_name="Projects",
                chunk_size_chars=100,
                chunk_overlap_chars=0,
            )

        self.assertEqual(result, 1)

    def test_sync_returns_error_when_required_dependency_is_missing(self) -> None:
        with patch.dict("os.environ", {"AIRTABLE_API_KEY": "key"}, clear=True), patch.dict(
            sys.modules,
            {
                "pyairtable": None,
                "chromadb": None,
            },
        ):
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

        self.assertEqual(result, 1)
