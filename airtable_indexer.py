"""
PBS-50: Fetch and index Airtable records into ChromaDB.

Pipeline:
  Airtable (pyairtable) → text serialization → ChromaDB (vector store)

Usage:
  python airtable_indexer.py            # index all tables
  python airtable_indexer.py --reset    # wipe ChromaDB and re-index

Dependencies:
  pip install pyairtable chromadb python-dotenv
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CHROMA_COLLECTION_NAME = "pbs_airtable"
CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_UPSERT_BATCH = 50  # ChromaDB upsert batch size


# ---------------------------------------------------------------------------
# Airtable helpers (pyairtable)
# ---------------------------------------------------------------------------

def get_api():
    """Return a pyairtable Api instance."""
    try:
        from pyairtable import Api
    except ImportError:
        raise ImportError("pyairtable is not installed. Run: pip install pyairtable")

    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise EnvironmentError("AIRTABLE_API_KEY not set in .env")
    return Api(api_key)


def fetch_schema(api, base_id: str) -> list:
    """
    Return list of Table objects using pyairtable's schema reading.
    pyairtable automatically reads the schema without hard-coding table names.
    """
    base = api.base(base_id)
    # base.schema() returns a BaseSchema with a .tables list
    schema = base.schema()
    return schema.tables


def fetch_all_records(api, base_id: str, table_id: str) -> list[dict]:
    """
    Fetch every record from a table using pyairtable.
    pyairtable handles pagination automatically via .all().
    """
    table = api.table(base_id, table_id)
    # .all() pages through the entire table and returns a flat list
    # Each record is a dict: {"id": "recXXX", "fields": {...}, "createdTime": "..."}
    return table.all()


# ---------------------------------------------------------------------------
# Text serialization
# ---------------------------------------------------------------------------

def record_to_text(record: dict, table_name: str) -> str:
    """
    Convert a single Airtable record into a plain-text string for embedding.

    Format example:
        Table: Projects
        Record ID: recXXXXXXXXXXXXXX
        Name: Q3 Fundraiser Campaign
        Status: In Progress
        Assigned To: Alice, Bob
        ...
    """
    lines = [
        f"Table: {table_name}",
        f"Record ID: {record.get('id', 'unknown')}",
    ]

    fields = record.get("fields", {})
    for field_name, value in fields.items():
        formatted = format_field_value(value)
        if formatted:
            lines.append(f"{field_name}: {formatted}")

    return "\n".join(lines)


def format_field_value(value) -> str:
    """Flatten any Airtable field value to a readable string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                # Linked record, attachment, collaborator, etc.
                parts.append(
                    item.get("name")
                    or item.get("text")
                    or item.get("email")
                    or item.get("filename")
                    or str(item)
                )
            else:
                parts.append(str(item))
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        # Formula error objects, etc.
        return str(value)
    return str(value)


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------

def get_or_create_collection(reset: bool = False):
    """
    Return a ChromaDB collection, optionally wiping it first.
    Import is deferred so the module loads even if chromadb is missing.
    """
    try:
        import chromadb
    except ImportError:
        raise ImportError(
            "chromadb is not installed. Run: pip install chromadb"
        )

    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    if reset:
        try:
            client.delete_collection(CHROMA_COLLECTION_NAME)
            print(f"  [reset] Deleted existing collection '{CHROMA_COLLECTION_NAME}'")
        except Exception:
            pass  # Collection didn't exist yet

    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def upsert_records(collection, ids: list, documents: list, metadatas: list):
    """Upsert into ChromaDB in batches to avoid memory pressure."""
    total = len(ids)
    for start in range(0, total, CHROMA_UPSERT_BATCH):
        end = min(start + CHROMA_UPSERT_BATCH, total)
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
    return total


# ---------------------------------------------------------------------------
# Main indexing logic
# ---------------------------------------------------------------------------

def index_all_tables(reset: bool = False):
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not base_id:
        raise EnvironmentError("AIRTABLE_BASE_ID not set in .env")

    print(f"\nPBS Wisconsin Airtable → ChromaDB Indexer")
    print(f"Base ID : {base_id}")
    print(f"ChromaDB: {CHROMA_PERSIST_DIR}/{CHROMA_COLLECTION_NAME}")
    print()

    # 1. Init pyairtable API and fetch schema
    print("Fetching Airtable schema...")
    api = get_api()
    # pyairtable reads schema automatically — no need to hard-code table names
    tables = fetch_schema(api, base_id)
    print(f"  Found {len(tables)} tables: {[t.name for t in tables]}\n")

    # 2. Prepare ChromaDB
    collection = get_or_create_collection(reset=reset)

    # 3. Index each table
    total_indexed = 0

    for table_schema in tables:
        table_name = table_schema.name
        table_id = table_schema.id

        print(f"Indexing table: {table_name} ({table_id})")

        try:
            # pyairtable .all() handles pagination automatically
            records = fetch_all_records(api, base_id, table_id)
        except Exception as e:
            print(f"  ERROR fetching records: {e}")
            continue

        if not records:
            print(f"  No records found, skipping.")
            continue

        print(f"  Fetched {len(records)} records")

        # Build ChromaDB inputs
        ids = []
        documents = []
        metadatas = []

        for record in records:
            rec_id = record.get("id", "")
            fields = record.get("fields", {})

            # Unique ChromaDB ID: tableId_recordId
            chroma_id = f"{table_id}_{rec_id}"

            # Full text for embedding
            doc_text = record_to_text(record, table_name)

            # Metadata for filtering / display
            meta = {
                "table_name": table_name,
                "table_id": table_id,
                "record_id": rec_id,
                # Store first 500 chars of raw text for quick retrieval
                "preview": doc_text[:500],
            }

            ids.append(chroma_id)
            documents.append(doc_text)
            metadatas.append(meta)

        # Upsert into ChromaDB
        count = upsert_records(collection, ids, documents, metadatas)
        total_indexed += count
        print(f"  Indexed {count} records into ChromaDB")

    print(f"\nDone. Total records indexed: {total_indexed}")
    print(f"Collection size: {collection.count()} documents")
    return collection


# ---------------------------------------------------------------------------
# Quick smoke test: query the collection after indexing
# ---------------------------------------------------------------------------

def smoke_test(collection, query: str = "project status"):
    print(f"\nSmoke test — querying: '{query}'")
    results = collection.query(
        query_texts=[query],
        n_results=3,
        include=["documents", "metadatas", "distances"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not docs:
        print("  No results returned.")
        return

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances)):
        print(f"\n  Result {i + 1} (distance: {dist:.4f})")
        print(f"  Table : {meta.get('table_name')}")
        print(f"  Record: {meta.get('record_id')}")
        # Print first 3 lines of the document
        preview_lines = doc.split("\n")[:4]
        for line in preview_lines:
            print(f"    {line}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv

    if reset_flag:
        print("--reset flag detected: ChromaDB collection will be wiped and re-built.")

    try:
        collection = index_all_tables(reset=reset_flag)
        smoke_test(collection)
    except EnvironmentError as e:
        print(f"\nConfiguration error: {e}")
        print("Make sure .env contains AIRTABLE_API_KEY and AIRTABLE_BASE_ID")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        raise
