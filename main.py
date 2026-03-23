import ssl
import certifi
import os
import json
import logging
import time
from typing import Optional

# Logging (set LOG_LEVEL=DEBUG for verbose traces)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pbs_bot")

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
# Number of Chroma chunks to retrieve before LLM synthesis (default 5)
chroma_n_results = int(os.getenv("CHROMA_N_RESULTS", "5"))
# Slack posts above ~4000 chars are often truncated; keep a safe margin
MAX_SLACK_CHARS = 3500

# -----------------------------
# Connect to ChromaDB
# -----------------------------
log.info("Connecting to ChromaDB...")

client = chromadb.PersistentClient(path="./chroma_db")

embedding_function = embedding_functions.DefaultEmbeddingFunction()

# Create collection if missing (fresh clone has no DB yet — run scripts/sync_airtable_to_chroma.py)
projects_collection = client.get_or_create_collection(
    name="pbs_projects",
    embedding_function=embedding_function,
)
try:
    _n = projects_collection.count()
    if _n == 0:
        log.warning(
            "Chroma collection 'pbs_projects' is empty. Run: "
            ".venv/bin/python3 scripts/sync_airtable_to_chroma.py "
            "(needs AIRTABLE_* in .env)"
        )
    else:
        log.info("ChromaDB connected: pbs_projects has %s document(s).", _n)
except Exception as e:
    log.info("ChromaDB connected (could not count documents: %s)", e)

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
def retrieve_chunks(query: str, n_results: Optional[int] = None) -> list[str]:
    """
    Run semantic search: Chroma embeds the query and returns the top-N similar documents.
    """
    k = n_results if n_results is not None else chroma_n_results
    t0 = time.perf_counter()
    log.debug("retrieve_chunks: start query=%r n_results=%s", query[:200], k)
    results = projects_collection.query(
        query_texts=[query],
        n_results=max(1, k),
    )
    docs = results.get("documents", [[]])[0]
    elapsed = time.perf_counter() - t0
    log.info(
        "retrieve_chunks: done in %.2fs, got %s document(s)",
        elapsed,
        len(docs or []),
    )
    return docs or []


def synthesize_answer_with_llm(
    original_question: str,
    clarified_interpretation: str,
    context_chunks: list[str],
) -> str:
    """
    RAG final step: answer the user using only the retrieved chunks (grounded response).
    """
    if not context_chunks:
        return (
            "I could not find relevant information in the knowledge base for that question."
        )

    log.info(
        "synthesize_answer_with_llm: chunks=%s openai=%s",
        len(context_chunks),
        bool(openai_client),
    )

    if not openai_client:
        # No LLM: show raw chunks as a transparent fallback
        joined = "\n\n---\n\n".join(
            f"[Source {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
        )
        return (
            "Here is what I found in the knowledge base (LLM synthesis is disabled):\n\n"
            + joined
        )

    context = "\n\n---\n\n".join(
        f"[Chunk {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
    )

    try:
        t0 = time.perf_counter()
        response = openai_client.chat.completions.create(
            model=openai_model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant for PBS Wisconsin internal project data. "
                        "Answer the user's question using ONLY the provided context chunks. "
                        "If the context is insufficient, say so clearly and suggest what might be missing. "
                        "Be concise and accurate. Use English only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Original user question:\n{original_question}\n\n"
                        f"Clarified interpretation (used for retrieval):\n{clarified_interpretation}\n\n"
                        f"Context from knowledge base:\n{context}"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        log.info(
            "synthesize_answer_with_llm: OpenAI OK in %.2fs, out_len=%s",
            time.perf_counter() - t0,
            len(text),
        )
        return text or (
            "I could not generate a response from the retrieved context. "
            "Try rephrasing your question."
        )
    except Exception as e:
        log.exception("LLM synthesis failed: %s", e)
        joined = "\n\n---\n\n".join(
            f"[Source {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
        )
        return (
            "I retrieved the following from the knowledge base, "
            "but could not summarize it with the LLM right now:\n\n" + joined
        )


def rag_answer_with_retrieval(
    query_for_search: str,
    original_user_message: str,
    clarified_for_user: str,
) -> str:
    """
    Full RAG path: embed query + vector search + multiple chunks + LLM answer.
    """
    chunks = retrieve_chunks(query_for_search)
    return synthesize_answer_with_llm(
        original_user_message,
        clarified_for_user,
        chunks,
    )


def truncate_for_slack(text: str, max_chars: int = MAX_SLACK_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 30].rstrip() + "\n\n_(Message truncated.)_"

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
        log.info("clarify_query_with_llm: no OPENAI_API_KEY, using fallback")
        return fallback

    try:
        t0 = time.perf_counter()
        log.info("clarify_query_with_llm: calling OpenAI model=%s", openai_model)
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

        log.info(
            "clarify_query_with_llm: OK in %.2fs",
            time.perf_counter() - t0,
        )
        return {
            "clarified_for_user": clarified_for_user,
            "query_for_search": query_for_search
        }
    except Exception as e:
        log.exception("clarify_query_with_llm failed: %s", e)
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
    log.info(
        "handle_user_query_flow: user=%s channel=%s pending=%s text_preview=%r",
        user,
        channel,
        bool(pending),
        (text or "")[:120],
    )

    if pending:
        if is_yes(text):
            query_for_search = pending["query_for_search"]
            original_user_message = pending.get(
                "original_user_message", query_for_search
            )
            clarified_for_user = pending.get(
                "clarified_for_user", query_for_search
            )
            pending_confirmations.pop(conversation_key, None)

            route = route_query(query_for_search)
            log.info(
                "confirmation yes: route=%s query_for_search=%r",
                route,
                query_for_search[:200],
            )
            if route == "projects":
                t_rag = time.perf_counter()
                answer = rag_answer_with_retrieval(
                    query_for_search,
                    original_user_message,
                    clarified_for_user,
                )
                log.info(
                    "rag_answer_with_retrieval: total %.2fs",
                    time.perf_counter() - t_rag,
                )
                return truncate_for_slack(answer)
            return "Right now I can answer questions about projects."

        if is_no(text):
            pending_confirmations.pop(conversation_key, None)
            log.info("confirmation no: cleared pending for %s", conversation_key)
            return "Understood. Please ask your question again, and I will confirm my understanding first."

        log.debug("pending but not yes/no: prompting again")
        return "Please reply with one of: `yes` or `no`."

    log.info("new question: calling clarify_query_with_llm")
    clarification = clarify_query_with_llm(text)
    pending_confirmations[conversation_key] = {
        **clarification,
        "original_user_message": text,
    }
    log.info(
        "stored pending confirmation key=%s (await yes/no in this channel/DM)",
        conversation_key,
    )
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
    raw_text = event.get("text", "") or ""
    text = normalize_mention_text(raw_text)
    log.info(
        "event=app_mention channel=%s user=%s raw_preview=%r normalized_preview=%r",
        channel,
        user,
        raw_text[:200],
        text[:200],
    )
    answer = handle_user_query_flow(user, channel, text)

    say(f"<@{user}>\n{answer}")


@app.event("message")
def handle_message(message, say):
    """
    - DMs: full flow (new questions + yes/no).
    - Channels: only process messages when this user has a pending confirmation
      (so plain 'yes' after @mention works in #channels — previously ignored).
    """
    if message.get("bot_id") or message.get("subtype"):
        return

    user = message.get("user")
    channel = message.get("channel")
    text = message.get("text", "") or ""
    channel_type = message.get("channel_type") or ""

    log.debug(
        "event=message channel=%s channel_type=%s user=%s text_preview=%r",
        channel,
        channel_type,
        user,
        text[:80],
    )

    if channel_type == "im":
        log.info("message in DM: full flow")
        answer = handle_user_query_flow(user, channel, text)
        say(f"<@{user}>\n{answer}")
        return

    # Public/private channel or MPIM: only handle yes/no follow-ups
    if channel_type in ("channel", "group", "mpim", ""):
        conversation_key = get_conversation_key(channel, user)
        if conversation_key not in pending_confirmations:
            log.debug(
                "channel message ignored (no pending): key=%s",
                conversation_key,
            )
            return
        # Same user message often triggers both app_mention and message; the latter
        # carries the full question again. Only treat short yes/no as confirmation.
        if not is_yes(text) and not is_no(text):
            log.debug(
                "channel: pending but text is not yes/no — skip "
                "(avoids duplicate reply for mention + message event)"
            )
            return
        log.info(
            "channel follow-up with pending (yes/no): user=%s channel=%s",
            user,
            channel,
        )
        answer = handle_user_query_flow(user, channel, text)
        say(f"<@{user}>\n{answer}")
        return

    log.debug("message ignored: channel_type=%s", channel_type)


# -----------------------------
# Start Slack Bot
# -----------------------------
if __name__ == "__main__":
    handler = SocketModeHandler(
        app,
        os.getenv("SLACK_APP_TOKEN")
    )
    log.info("PBS Bot Socket Mode handler starting (set LOG_LEVEL=DEBUG for verbose logs)")
    print("🤖 PBS Bot is running!")
    handler.start()