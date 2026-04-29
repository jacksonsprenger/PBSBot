"""Extended tests for pbsbot.chroma.store — init edge cases and failure modes."""

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
    def __init__(self, *, count_value=3, query_results=None, fail_first_query=False, count_raises=False) -> None:
        self.count_value = count_value
        self.query_results = query_results if query_results is not None else {"documents": [["chunk one", "chunk two"]]}
        self.fail_first_query = fail_first_query
        self.count_raises = count_raises
        self.query_calls: list[dict] = []

    def count(self) -> int:
        if self.count_raises:
            raise RuntimeError("segment fault simulation")
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


class ChromaStoreInitEdgeCases(TestCase):
    def test_init_warns_when_collection_is_empty(self) -> None:
        collection = FakeCollection(count_value=0)
        module = load_chroma_store_module(collections=[collection])
        settings = SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)

        with patch.object(module.log, "warning") as mock_warn:
            module.ChromaStore(settings)

        mock_warn.assert_called_once()
        self.assertIn("empty", mock_warn.call_args[0][0].lower())

    def test_init_handles_count_exception_gracefully(self) -> None:
        collection = FakeCollection(count_raises=True)
        module = load_chroma_store_module(collections=[collection])
        settings = SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)

        # Should not raise
        store = module.ChromaStore(settings)
        self.assertIs(store._collection, collection)


class ChromaStoreRetrieveEdgeCases(TestCase):
    def test_retrieve_chunks_without_where_filter(self) -> None:
        collection = FakeCollection(query_results={"documents": [["alpha", "beta"]]})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        chunks = store.retrieve_chunks("project update")

        self.assertEqual(chunks, ["alpha", "beta"])
        self.assertEqual(
            collection.query_calls,
            [{"query_texts": ["project update"], "n_results": 5}],
        )
        self.assertNotIn("where", collection.query_calls[0])

    def test_retrieve_chunks_with_explicit_n_results(self) -> None:
        collection = FakeCollection(query_results={"documents": [["one"]]})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        chunks = store.retrieve_chunks("query", n_results=3)

        self.assertEqual(collection.query_calls[0]["n_results"], 3)

    def test_retrieve_chunks_raises_on_second_internal_error(self) -> None:
        """When reconnect also fails, the second InternalError should propagate."""

        class AlwaysFailCollection(FakeCollection):
            def query(self, **kwargs):
                raise FakeInternalError("persistent failure")

        stale = AlwaysFailCollection()
        fresh = AlwaysFailCollection()
        module = load_chroma_store_module(collections=[stale, fresh])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        with self.assertRaises(FakeInternalError):
            store.retrieve_chunks("query")

    def test_retrieve_chunks_returns_empty_list_when_documents_key_is_empty(self) -> None:
        collection = FakeCollection(query_results={"documents": [[]]})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        chunks = store.retrieve_chunks("query")

        self.assertEqual(chunks, [])

    def test_retrieve_chunks_handles_missing_documents_key(self) -> None:
        collection = FakeCollection(query_results={})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        chunks = store.retrieve_chunks("query")

        self.assertEqual(chunks, [])

    def test_reconnect_replaces_client_and_collection(self) -> None:
        original = FakeCollection()
        replacement = FakeCollection(query_results={"documents": [["new"]]})
        module = load_chroma_store_module(collections=[original, replacement])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        self.assertIs(store._collection, original)

        store.reconnect()

        self.assertIs(store._collection, replacement)
        self.assertEqual(FakeClient.paths, ["/tmp/chroma", "/tmp/chroma"])

    def test_retrieve_chunks_with_negative_n_results_clamps_to_one(self) -> None:
        collection = FakeCollection(query_results={"documents": [[]]})
        module = load_chroma_store_module(collections=[collection])
        store = module.ChromaStore(
            SimpleNamespace(chroma_persist_dir="/tmp/chroma", chroma_n_results=5)
        )

        store.retrieve_chunks("q", n_results=-5)

        self.assertEqual(collection.query_calls[0]["n_results"], 1)
