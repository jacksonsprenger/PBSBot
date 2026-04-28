from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


class FakeInternalError(Exception):
    pass


class FakeCollection:
    def __init__(self, *, count_value=3, query_results=None, fail_first_query=False) -> None:
        self.count_value = count_value
        self.query_results = query_results or {"documents": [["chunk one", "chunk two"]]}
        self.fail_first_query = fail_first_query
        self.query_calls: list[dict] = []

    def count(self) -> int:
        return self.count_value

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self.fail_first_query and len(self.query_calls) == 1:
            raise FakeInternalError("stale db")
        return self.query_results


class FakeClient:
    collections: list[FakeCollection] = []
    paths: list[str] = []

    def __init__(self, path: str) -> None:
        self.path = path
        FakeClient.paths.append(path)

    def get_or_create_collection(self, *, name, embedding_function):
        collection = FakeClient.collections.pop(0)
        collection.collection_name = name
        collection.embedding_function = embedding_function
        return collection


def load_chroma_store_module(*, collections: list[FakeCollection]):
    sys.modules.pop("pbsbot.chroma.store", None)
    FakeClient.collections = list(collections)
    FakeClient.paths = []

    fake_embedding_functions = types.SimpleNamespace(DefaultEmbeddingFunction=lambda: "embedder")
    fake_chromadb = types.SimpleNamespace(
        PersistentClient=FakeClient,
        errors=types.SimpleNamespace(InternalError=FakeInternalError),
    )
    fake_utils = types.SimpleNamespace(embedding_functions=fake_embedding_functions)

    with patch.dict(
        sys.modules,
        {
            "chromadb": fake_chromadb,
            "chromadb.errors": fake_chromadb.errors,
            "chromadb.utils": fake_utils,
            "chromadb.utils.embedding_functions": fake_embedding_functions,
        },
    ):
        return importlib.import_module("pbsbot.chroma.store")


class ChromaStoreTests(TestCase):
    def test_init_opens_configured_persist_dir_and_collection(self) -> None:
        collection = FakeCollection(count_value=2)
        module = load_chroma_store_module(collections=[collection])
        settings = SimpleNamespace(chroma_persist_dir="/tmp/pbs-chroma", chroma_n_results=5)

        store = module.ChromaStore(settings)

        self.assertIs(store._collection, collection)
        self.assertEqual(FakeClient.paths, ["/tmp/pbs-chroma"])
        self.assertEqual(collection.collection_name, "pbs_projects")
        self.assertEqual(collection.embedding_function, "embedder")

    def test_retrieve_chunks_uses_default_result_count_and_where_filter(self) -> None:
        collection = FakeCollection(query_results={"documents": [["alpha"]]})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/pbs-chroma", chroma_n_results=7)
        )

        chunks = store.retrieve_chunks("status", where={"table_name": "Tasks"})

        self.assertEqual(chunks, ["alpha"])
        self.assertEqual(
            collection.query_calls,
            [
                {
                    "query_texts": ["status"],
                    "n_results": 7,
                    "where": {"table_name": "Tasks"},
                }
            ],
        )

    def test_retrieve_chunks_clamps_explicit_result_count_to_one(self) -> None:
        collection = FakeCollection(query_results={"documents": [[]]})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/pbs-chroma", chroma_n_results=7)
        )

        chunks = store.retrieve_chunks("status", n_results=0)

        self.assertEqual(chunks, [])
        self.assertEqual(collection.query_calls[0]["n_results"], 1)
        self.assertNotIn("where", collection.query_calls[0])

    def test_retrieve_chunks_reconnects_once_after_internal_error(self) -> None:
        stale_collection = FakeCollection(fail_first_query=True)
        fresh_collection = FakeCollection(query_results={"documents": [["fresh chunk"]]})
        module = load_chroma_store_module(collections=[stale_collection, fresh_collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/pbs-chroma", chroma_n_results=5)
        )

        chunks = store.retrieve_chunks("status")

        self.assertEqual(chunks, ["fresh chunk"])
        self.assertEqual(len(stale_collection.query_calls), 1)
        self.assertEqual(len(fresh_collection.query_calls), 1)
        self.assertEqual(FakeClient.paths, ["/tmp/pbs-chroma", "/tmp/pbs-chroma"])

