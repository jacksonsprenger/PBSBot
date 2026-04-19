"""
Index Airtable records into ChromaDB
"""

import os
from dotenv import load_dotenv
from pyairtable import Api
import chromadb
from chromadb.utils import embedding_functions

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
    print("Missing AIRTABLE_API_KEY or AIRTABLE_BASE_ID")
    exit()

# -----------------------------
# Connect to Airtable
# -----------------------------
print("Connecting to Airtable...")

api = Api(AIRTABLE_API_KEY)

TABLE_ID = "tblU9LfZeVNicdB5e"

table = api.table(AIRTABLE_BASE_ID, TABLE_ID)

records = table.all()

print(f"Fetched {len(records)} records")

# -----------------------------
# Setup ChromaDB (PERSISTENT)
# -----------------------------
print("Initializing ChromaDB...")

client = chromadb.PersistentClient(path="./chroma_db")

embedding_function = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_or_create_collection(
    name="pbs_projects",
    embedding_function=embedding_function
)

# -----------------------------
# Index records
# -----------------------------
print("Indexing records...")

count = 0

for record in records:

    record_id = record["id"]
    fields = record["fields"]

    text_parts = []

    for key, value in fields.items():

        if value is None or value == "":
            continue

        if isinstance(value, list):

            cleaned = []

            for item in value:

                if isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        cleaned.append(name)
                else:
                    cleaned.append(str(item))

            value = ", ".join(cleaned)

        elif isinstance(value, dict):

            name = value.get("name")
            email = value.get("email")

            if name:
                value = name
            elif email:
                value = email
            else:
                continue

        else:
            value = str(value)

        text_parts.append(f"{key}: {value}")

    document_text = "\n".join(text_parts)

    if not document_text.strip():
        continue

    collection.add(
        documents=[document_text],
        ids=[record_id],
        metadatas=[{"source": "airtable"}]
    )

    count += 1

print(f"Indexed {count} records")
print("Done.")