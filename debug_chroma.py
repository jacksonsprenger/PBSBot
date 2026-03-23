"""
Debug utility for inspecting the ChromaDB collection.

This script prints stored documents and metadata
to verify that Airtable records were indexed correctly.
"""

import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_collection(name="pbs_projects")

data = collection.get()

docs = data["documents"]

print("Total docs:", len(docs))

for d in docs:
    if "bucky" in d.lower():
        print("FOUND BUCKY:")
        print(d)
        print("-----")