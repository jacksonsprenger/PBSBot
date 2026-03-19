import ssl
import certifi
import os
import json

# SSL fix for Mac
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl.create_default_context

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from openai import OpenAI

import chromadb
from chromadb.utils import embedding_functions

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# -----------------------------
# Connect to ChromaDB
# -----------------------------
print("Connecting to ChromaDB...")

client = chromadb.PersistentClient(path="./chroma_db")

embedding_function = embedding_functions.DefaultEmbeddingFunction()

projects_collection = client.get_collection(
    name="pbs_projects",
    embedding_function=embedding_function
)

print("ChromaDB connected.")

# Conversation state for "confirm before retrieval"
pending_confirmations = {}


# -----------------------------
# Content Routing
# -----------------------------
def route_query(query: str) -> str:
    q = query.lower()

    if "task" in q:
        return "tasks"

    if "contact" in q or "email" in q or "phone" in q:
        return "contacts"

    if "staff" in q or "who is" in q:
        return "staff"

    return "projects"


# -----------------------------
# Retrieval from ChromaDB
# -----------------------------
def search_projects(query: str) -> str:

    results = projects_collection.query(
        query_texts=[query],
        n_results=2
    )

    docs = results.get("documents", [[]])[0]

    if not docs:
        return "I couldn't find anything related to that project."

    return docs[0]


def normalize_mention_text(text: str) -> str:
    """
    Removes Slack user mention tokens from app mention events.
    """
    cleaned = text.strip()
    parts = [part for part in cleaned.split() if not (part.startswith("<@") and part.endswith(">"))]
    return " ".join(parts).strip()


def is_yes(text: str) -> bool:
    normalized = text.strip().lower()
    yes_values = {
        "yes", "y", "yeah", "yep", "correct"
    }
    return normalized in yes_values


def is_no(text: str) -> bool:
    normalized = text.strip().lower()
    no_values = {
        "no", "n", "nope", "incorrect"
    }
    return normalized in no_values


def clarify_query_with_llm(user_query: str) -> dict:
    """
    Uses an LLM to rewrite user query into a retrieval-friendly question.
    Falls back to the original query if LLM is unavailable or fails.
    """
    fallback = {
        "clarified_for_user": user_query,
        "query_for_search": user_query
    }

    if not openai_client:
        return fallback

    try:
        response = openai_client.chat.completions.create(
            model=openai_model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You help rewrite user questions before retrieval. "
                        "Return strict JSON with keys: clarified_for_user, query_for_search. "
                        "Use English only. "
                        "clarified_for_user should be a polite confirmation sentence in English. "
                        "query_for_search should be concise keywords/sentence optimized for vector search."
                    )
                },
                {
                    "role": "user",
                    "content": f"Original user question:\n{user_query}"
                }
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        clarified_for_user = parsed.get("clarified_for_user", user_query).strip() or user_query
        query_for_search = parsed.get("query_for_search", user_query).strip() or user_query

        return {
            "clarified_for_user": clarified_for_user,
            "query_for_search": query_for_search
        }
    except Exception as e:
        print(f"LLM clarify failed: {e}")
        return fallback


def get_conversation_key(channel_id: str, user_id: str) -> str:
    return f"{channel_id}:{user_id}"


def handle_user_query_flow(user: str, channel: str, text: str) -> str:
    """
    - If there is a pending confirmation, process yes/no.
    - Otherwise clarify with LLM, ask for confirmation, and wait.
    """
    conversation_key = get_conversation_key(channel, user)
    pending = pending_confirmations.get(conversation_key)

    if pending:
        if is_yes(text):
            query_for_search = pending["query_for_search"]
            pending_confirmations.pop(conversation_key, None)

            route = route_query(query_for_search)
            if route == "projects":
                return search_projects(query_for_search)
            return "Right now I can answer questions about projects."

        if is_no(text):
            pending_confirmations.pop(conversation_key, None)
            return "Understood. Please ask your question again, and I will confirm my understanding first."

        return "Please reply with one of: `yes` or `no`."

    clarification = clarify_query_with_llm(text)
    pending_confirmations[conversation_key] = clarification
    return (
        "Here is how I understood your question. Reply `yes` to continue, or `no` to rewrite it.\n\n"
        f"- {clarification['clarified_for_user']}"
    )


# -----------------------------
# Slack Event Handlers
# -----------------------------
@app.event("app_mention")
def handle_mention(event, say):
    user = event["user"]
    channel = event.get("channel")
    text = normalize_mention_text(event.get("text", ""))
    answer = handle_user_query_flow(user, channel, text)

    say(f"<@{user}>\n{answer}")


@app.event("message")
def handle_dm(message, say):
    # Ignore bot messages and subtypes
    if message.get("bot_id") or message.get("subtype"):
        return

    # Only handle DMs
    if message.get("channel_type") == "im":

        user = message.get("user")
        channel = message.get("channel")
        text = message.get("text", "")
        answer = handle_user_query_flow(user, channel, text)

        say(f"<@{user}>\n{answer}")


# -----------------------------
# Start Slack Bot
# -----------------------------
if __name__ == "__main__":
    handler = SocketModeHandler(
        app,
        os.getenv("SLACK_APP_TOKEN")
    )
    print("🤖 PBS Bot is running!")
    handler.start()