#!/usr/bin/env python3
"""Print chunk counts per Airtable table_id in Chroma (expects chunked sync metadata)."""
from __future__ import annotations

import os
import sys
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

import chromadb
from chromadb.utils import embedding_functions


def main() -> int:
    chroma_path = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    name = os.getenv("CHROMA_COLLECTION_NAME", "pbs_projects")

    client = chromadb.PersistentClient(path=chroma_path)
    col = client.get_collection(
        name,
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
    )
    n = col.count()
    print(f"Collection: {name!r}  path: {chroma_path!r}")
    print(f"Total chunks: {n}")
    if n == 0:
        return 0

    offset = 0
    batch = 2000
    ctr: Counter[str] = Counter()
    names: dict[str, str] = {}

    while offset < n:
        res = col.get(include=["metadatas"], limit=min(batch, n - offset), offset=offset)
        metas = res.get("metadatas") or []
        for m in metas:
            if not m:
                continue
            tid = m.get("table_id") or "?"
            ctr[tid] += 1
            tname = m.get("table_name")
            if tname and tid not in names:
                names[tid] = str(tname)
        offset += len(metas)
        if len(metas) == 0:
            break

    print(f"Distinct tables (by table_id): {len(ctr)}")
    for tid, cnt in sorted(ctr.items(), key=lambda x: -x[1]):
        label = names.get(tid, "")
        extra = f"  ({label})" if label else ""
        print(f"  {tid}: {cnt} chunks{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
