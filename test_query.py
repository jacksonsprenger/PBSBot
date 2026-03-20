"""
Test script for verifying ChromaDB vector retrieval.

This script sends a sample query to the ChromaDB collection
and prints the most relevant Airtable records retrieved (same embedding path
as the Slack bot). Use this to validate indexing before running main.py.

Set CHROMA_N_RESULTS in .env to match the bot (default 5).
"""

import os

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

N_RESULTS = int(os.getenv("CHROMA_N_RESULTS", "5"))

client = chromadb.PersistentClient(path="./chroma_db")

embedding_function = embedding_functions.DefaultEmbeddingFunction()

collection = client.get_collection(
    name="pbs_projects",
    embedding_function=embedding_function
)

results = collection.query(
    query_texts=["What is the status of Bucky project"],
    n_results=max(1, N_RESULTS),
)

print("\nRESULTS:\n")

docs = results.get("documents", [[]])[0]
for i, doc in enumerate(docs):
    print(f"--- Chunk {i + 1} ---")
    print(doc)
    print("-----")