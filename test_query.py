"""
Test script for verifying ChromaDB vector retrieval.

This script sends a sample query to the ChromaDB collection
and prints the most relevant Airtable records retrieved.

Used to validate that indexing and semantic search are working correctly.
"""

import chromadb
from chromadb.utils import embedding_functions

# connect to persistent DB
client = chromadb.PersistentClient(path="./chroma_db")

embedding_function = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_collection(
    name="pbs_projects",
    embedding_function=embedding_function
)

results = collection.query(
    query_texts=["What is the status of Bucky project"],
    n_results=2
)

print("\nRESULTS:\n")

for doc in results["documents"][0]:
    print(doc)
    print("-----")