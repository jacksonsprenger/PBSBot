#!/usr/bin/env python3
"""
Batch sync: Airtable tables → ChromaDB (same store the Slack bot reads).

Designed to run on a schedule (e.g. cron) separately from main.py.

This script:
  1) Fetches one table (default) or all tables in the base (`--all-tables`)
  2) Converts each Airtable record into a text document
  3) Chunks each document into smaller overlapping chunks
  4) Upserts chunk-level vectors into Chroma (deterministic chunk IDs)

Environment:
  AIRTABLE_API_KEY, AIRTABLE_BASE_ID
  AIRTABLE_TABLE_ID  (defaults to Projects table id used by the team)
  CHROMA_PERSIST_DIR (default ./chroma_db)
  CHROMA_COLLECTION_NAME (default pbs_projects — must match main.py)

Usage (use the same venv as the Slack bot — plain `python` often has no deps):
  .venv/bin/python3 scripts/sync_airtable_to_chroma.py
  .venv/bin/python3 scripts/sync_airtable_to_chroma.py --reset                # full rebuild (single table)
  .venv/bin/python3 scripts/sync_airtable_to_chroma.py --reset --all-tables # full rebuild (all tables)
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

import requests

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
DEFAULT_CHUNK_SIZE_CHARS = 1200
DEFAULT_CHUNK_OVERLAP_CHARS = 200


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


def chunk_text(
    text: str,
    *,
    chunk_size_chars: int,
    overlap_chars: int,
) -> list[str]:
    """
    Chunk by character windows with overlap.
    (Simple + deterministic; good enough for Chroma embedding.)
    """
    if not text:
        return []
    text = text.strip()
    if len(text) <= chunk_size_chars:
        return [text]

    overlap_chars = max(0, min(overlap_chars, chunk_size_chars - 1))
    step = max(1, chunk_size_chars - overlap_chars)

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start += step

    return chunks


def fetch_tables_metadata(base_id: str, *, api_key: str) -> list[dict]:
    """
    Uses Airtable Metadata API to list tables (id + name).
    """
    meta_url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {"Authorization": f"Bearer {api_key}"}
    # Avoid proxy env vars (some environments set HTTP(S)_PROXY and block this request)
    session = requests.Session()
    session.trust_env = False
    resp = session.get(meta_url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("tables", [])


def fetch_tables_pyairtable(base_id: str, *, api_key: str) -> list[dict]:
    """
    List tables via pyairtable (works better in restricted network environments).
    Returns [{id, name}, ...].
    """
    from pyairtable import Api

    api = Api(api_key)
    base = api.base(base_id)
    tables = base.tables()

    out: list[dict] = []
    for t in tables:
        out.append({"id": getattr(t, "id", None), "name": getattr(t, "name", None)})
    return out


def sync(
    *,
    reset: bool,
    chroma_path: str,
    collection_name: str,
    base_id: str,
    table_id: str,
    table_name: str,
    chunk_size_chars: int,
    chunk_overlap_chars: int,
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

    log.info("Fetching Airtable table=%s (%s) ...", table_name, table_id)
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
    n_records = len(records)
    progress_every = max(1, int(os.getenv("SYNC_PROGRESS_EVERY", "500")))

    for rec_idx, record in enumerate(records):
        if rec_idx and rec_idx % progress_every == 0:
            log.info(
                "  ... progress %s/%s records (%s)",
                rec_idx,
                n_records,
                table_name,
            )
        parsed = record_to_document(record)
        if not parsed:
            continue
        rec_id, doc_text = parsed

        chunks = chunk_text(
            doc_text,
            chunk_size_chars=chunk_size_chars,
            overlap_chars=chunk_overlap_chars,
        )
        if not chunks:
            continue

        for i, chunk in enumerate(chunks):
            # Stable unique ID per chunk so chunk upserts are deterministic.
            ids_batch.append(f"{table_id}:{rec_id}:{i}")
            docs_batch.append(chunk)
            meta_batch.append(
                {
                    "source": "airtable",
                    "table_id": table_id,
                    "table_name": table_name,
                    "record_id": rec_id,
                    "chunk_index": i,
                }
            )

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

    log.info(
        "Upsert complete: %s chunks. Collection count=%s",
        total,
        collection.count(),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Airtable → Chroma for PBSBot")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the Chroma collection before re-indexing (full rebuild)",
    )
    parser.add_argument(
        "--all-tables",
        action="store_true",
        help="Index every table in AIRTABLE_BASE_ID",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=int(os.getenv("CHUNK_SIZE_CHARS", str(DEFAULT_CHUNK_SIZE_CHARS))),
        help="Chunk size in characters",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=int(os.getenv("CHUNK_OVERLAP_CHARS", str(DEFAULT_CHUNK_OVERLAP_CHARS))),
        help="Chunk overlap in characters",
    )
    args = parser.parse_args()

    base_id = os.getenv("AIRTABLE_BASE_ID") or ""
    table_id = os.getenv("AIRTABLE_TABLE_ID", DEFAULT_TABLE_ID)
    chroma_path = os.getenv("CHROMA_PERSIST_DIR", DEFAULT_CHROMA_PATH)
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", DEFAULT_COLLECTION)

    api_key = os.getenv("AIRTABLE_API_KEY") or ""
    if not base_id or not api_key:
        log.error("Missing AIRTABLE_BASE_ID or AIRTABLE_API_KEY in .env")
        return 1

    if args.all_tables:
        # Use pyairtable table listing to avoid blocked metadata requests in some envs.
        tables = fetch_tables_pyairtable(base_id, api_key=api_key)
        if not tables:
            log.error("No Airtable tables found for base_id=%s", base_id)
            return 1

        first = True
        for t in tables:
            tid = t.get("id")
            if not tid:
                continue
            tname = t.get("name") or tid

            sync(
                reset=args.reset and first,
                chroma_path=chroma_path,
                collection_name=collection_name,
                base_id=base_id,
                table_id=tid,
                table_name=tname,
                chunk_size_chars=args.chunk_size,
                chunk_overlap_chars=args.chunk_overlap,
            )
            first = False
        return 0

    table_name = "Projects" if table_id == DEFAULT_TABLE_ID else table_id
    return sync(
        reset=args.reset,
        chroma_path=chroma_path,
        collection_name=collection_name,
        base_id=base_id,
        table_id=table_id,
        table_name=table_name,
        chunk_size_chars=args.chunk_size,
        chunk_overlap_chars=args.chunk_overlap,
    )


if __name__ == "__main__":
    sys.exit(main())
