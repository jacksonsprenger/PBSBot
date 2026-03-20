#!/usr/bin/env python3
"""
Batch sync: Airtable table → ChromaDB (same store the Slack bot reads).

Designed to run on a schedule (e.g. cron) separately from main.py.

Uses upsert by Airtable record id so re-runs update existing vectors.

Environment (see docs/CONFIGURATION.md):
  AIRTABLE_API_KEY, AIRTABLE_BASE_ID
  AIRTABLE_TABLE_ID  (defaults to Projects table id used by the team)
  CHROMA_PERSIST_DIR (default ./chroma_db)
  CHROMA_COLLECTION_NAME (default pbs_projects — must match main.py)

Usage (use the same venv as the Slack bot — plain `python` often has no deps):

  .venv/bin/python3 scripts/sync_airtable_to_chroma.py
  .venv/bin/python3 scripts/sync_airtable_to_chroma.py --reset   # full rebuild
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

# SSL fix for macOS (Airtable HTTPS)
import certifi
import ssl

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
ssl._create_default_https_context = ssl.create_default_context

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] sync_chroma: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sync_chroma")

# Defaults aligned with main.py and legacy index_airtable.py
DEFAULT_TABLE_ID = "tblU9LfZeVNicdB5e"
DEFAULT_CHROMA_PATH = "./chroma_db"
DEFAULT_COLLECTION = "pbs_projects"
UPSERT_BATCH = 50


def field_value_to_text(value) -> str | None:
    """Flatten one Airtable field to a line of text (same rules as index_airtable)."""
    if value is None or value == "":
        return None

    if isinstance(value, list):
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    cleaned.append(name)
            else:
                cleaned.append(str(item))
        return ", ".join(cleaned) if cleaned else None

    if isinstance(value, dict):
        name = value.get("name")
        email = value.get("email")
        if name:
            return name
        if email:
            return email
        return None

    return str(value)


def record_to_document(record: dict) -> tuple[str, str] | None:
    """Return (record_id, document_text) or None if empty."""
    record_id = record["id"]
    fields = record.get("fields") or {}
    text_parts: list[str] = []

    for key, value in fields.items():
        line = field_value_to_text(value)
        if line is None:
            continue
        text_parts.append(f"{key}: {line}")

    document_text = "\n".join(text_parts)
    if not document_text.strip():
        return None
    return record_id, document_text


def sync(
    *,
    reset: bool,
    chroma_path: str,
    collection_name: str,
    base_id: str,
    table_id: str,
) -> int:
    try:
        from pyairtable import Api
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError as e:
        log.error(
            "Missing Python package (%s). The sync script needs the project dependencies.\n"
            "  1) cd to the repo root\n"
            "  2) .venv/bin/python3 -m pip install -r requirements.txt\n"
            "  3) .venv/bin/python3 scripts/sync_airtable_to_chroma.py",
            e,
        )
        return 1

    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key or not base_id:
        log.error("Missing AIRTABLE_API_KEY or AIRTABLE_BASE_ID in .env")
        return 1

    log.info("Fetching Airtable table=%s ...", table_id)
    t0 = time.perf_counter()
    api = Api(api_key)
    table = api.table(base_id, table_id)
    records = table.all()
    log.info("Fetched %s records in %.2fs", len(records), time.perf_counter() - t0)

    log.info("Opening Chroma at %s collection=%s", chroma_path, collection_name)
    client = chromadb.PersistentClient(path=chroma_path)
    embedding_function = embedding_functions.DefaultEmbeddingFunction()

    if reset:
        try:
            client.delete_collection(collection_name)
            log.info("Deleted collection %r (--reset)", collection_name)
        except Exception as e:
            log.debug("delete_collection: %s", e)

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_function,
    )

    ids_batch: list[str] = []
    docs_batch: list[str] = []
    meta_batch: list[dict] = []
    total = 0

    for record in records:
        parsed = record_to_document(record)
        if not parsed:
            continue
        rec_id, doc_text = parsed
        ids_batch.append(rec_id)
        docs_batch.append(doc_text)
        meta_batch.append({"source": "airtable", "table_id": table_id})

        if len(ids_batch) >= UPSERT_BATCH:
            collection.upsert(
                ids=ids_batch,
                documents=docs_batch,
                metadatas=meta_batch,
            )
            total += len(ids_batch)
            log.debug("Upserted batch, total so far %s", total)
            ids_batch, docs_batch, meta_batch = [], [], []

    if ids_batch:
        collection.upsert(
            ids=ids_batch,
            documents=docs_batch,
            metadatas=meta_batch,
        )
        total += len(ids_batch)

    log.info("Upsert complete: %s documents. Collection count=%s", total, collection.count())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Airtable → Chroma for PBSBot")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the Chroma collection before re-indexing (full rebuild)",
    )
    args = parser.parse_args()

    base_id = os.getenv("AIRTABLE_BASE_ID") or ""
    table_id = os.getenv("AIRTABLE_TABLE_ID", DEFAULT_TABLE_ID)
    chroma_path = os.getenv("CHROMA_PERSIST_DIR", DEFAULT_CHROMA_PATH)
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", DEFAULT_COLLECTION)

    return sync(
        reset=args.reset,
        chroma_path=chroma_path,
        collection_name=collection_name,
        base_id=base_id,
        table_id=table_id,
    )


if __name__ == "__main__":
    sys.exit(main())
