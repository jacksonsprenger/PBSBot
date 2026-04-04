"""Chroma persistent client + retrieval (RAG / vector feature)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import chromadb
import chromadb.errors
from chromadb.utils import embedding_functions

if TYPE_CHECKING:
    from pbsbot.config import Settings

log = logging.getLogger("pbs_bot")


class ChromaStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = settings.chroma_persist_dir
        self._embedding_function = embedding_functions.DefaultEmbeddingFunction()
        log.info("Connecting to ChromaDB at %r...", self._path)
        self._client = chromadb.PersistentClient(path=self._path)
        self._collection = self._client.get_or_create_collection(
            name="pbs_projects",
            embedding_function=self._embedding_function,
        )
        try:
            n = self._collection.count()
            if n == 0:
                log.warning(
                    "Chroma collection 'pbs_projects' is empty. Run sync (needs AIRTABLE_* in .env): "
                    "python -m pbsbot.ingestion.sync_airtable "
                    "or: docker compose run --rm pbsbot python -m pbsbot.ingestion.sync_airtable"
                )
            else:
                log.info("ChromaDB connected: pbs_projects has %s document(s).", n)
        except Exception as e:
            log.info("ChromaDB connected (could not count documents: %s)", e)

    def reconnect(self) -> None:
        log.warning(
            "Reopening Chroma at %r (disk was updated; refreshing client handle)",
            self._path,
        )
        self._client = chromadb.PersistentClient(path=self._path)
        self._collection = self._client.get_or_create_collection(
            name="pbs_projects",
            embedding_function=self._embedding_function,
        )

    def retrieve_chunks(
        self,
        query: str,
        n_results: Optional[int] = None,
        where: Optional[dict] = None,
    ) -> list[str]:
        k = n_results if n_results is not None else self._settings.chroma_n_results
        t0 = time.perf_counter()
        log.debug(
            "retrieve_chunks: start query=%r n_results=%s where=%s",
            query[:200],
            k,
            where,
        )
        qkwargs: dict = {
            "query_texts": [query],
            "n_results": max(1, k),
        }
        if where:
            qkwargs["where"] = where

        for attempt in range(2):
            try:
                results = self._collection.query(**qkwargs)
                break
            except chromadb.errors.InternalError as e:
                if attempt == 0:
                    log.warning("Chroma query failed (will reopen DB once): %s", e)
                    self.reconnect()
                    continue
                raise

        docs = results.get("documents", [[]])[0]
        elapsed = time.perf_counter() - t0
        log.info(
            "retrieve_chunks: done in %.2fs, got %s document(s)",
            elapsed,
            len(docs or []),
        )
        return docs or []
