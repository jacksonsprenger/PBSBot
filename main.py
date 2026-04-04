import ssl
import certifi
import os
import json
import logging
import re
import time
import urllib.error
import urllib.request
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

import chromadb
import chromadb.errors
from chromadb.utils import embedding_functions

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))


def _resolve_ollama_base_url() -> str:
    """
    Local Ollama: on the host use 127.0.0.1; inside Docker the host is not loopback,
    so default to host.docker.internal (requires extra_hosts in compose on Linux).
    """
    raw = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    if os.path.exists("/.dockerenv"):
        return "http://host.docker.internal:11434"
    return "http://127.0.0.1:11434"


# Ollama on VM host (Docker) or laptop (127.0.0.1 / SSH tunnel like scripts/llm_connect.py)
ollama_base_url = _resolve_ollama_base_url()
ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
ollama_timeout = int(os.getenv("OLLAMA_TIMEOUT", "120"))
# Number of Chroma chunks to retrieve before LLM synthesis (default 5)
chroma_n_results = int(os.getenv("CHROMA_N_RESULTS", "5"))
# Restrict "projects" RAG to 📈Projects chunks only (avoids noise from promos, tasks, etc.)
chroma_projects_table_id = os.getenv("AIRTABLE_TABLE_ID", "tblU9LfZeVNicdB5e").strip()
chroma_filter_projects_only = os.getenv("CHROMA_FILTER_TO_PROJECTS_TABLE", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Slack posts above ~4000 chars are often truncated; keep a safe margin
MAX_SLACK_CHARS = 3500

# -----------------------------
# Connect to ChromaDB
# -----------------------------
log.info("Connecting to ChromaDB...")

_chroma_path = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
client = chromadb.PersistentClient(path=_chroma_path)

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
            "Chroma collection 'pbs_projects' is empty. Run sync (needs AIRTABLE_* in .env): "
            ".venv/bin/python3 scripts/sync_airtable_to_chroma.py "
            "or: docker compose run --rm pbsbot python scripts/sync_airtable_to_chroma.py"
        )
    else:
        log.info("ChromaDB connected: pbs_projects has %s document(s).", _n)
except Exception as e:
    log.info("ChromaDB connected (could not count documents: %s)", e)

log.info(
    "Ollama: base_url=%s model=%s (set OLLAMA_BASE_URL / OLLAMA_MODEL to override)",
    ollama_base_url,
    ollama_model,
)


def reconnect_chroma_client() -> None:
    """
    Re-open the on-disk store. Needed when another process (e.g. sync job) wrote to the
    same CHROMA_PERSIST_DIR while this process still held an old Chroma handle — otherwise
    queries can fail with hnsw / 'Nothing found on disk'.
    """
    global client, projects_collection
    log.warning(
        "Reopening Chroma at %r (disk was updated; refreshing client handle)",
        _chroma_path,
    )
    client = chromadb.PersistentClient(path=_chroma_path)
    projects_collection = client.get_or_create_collection(
        name="pbs_projects",
        embedding_function=embedding_function,
    )


# Conversation state for "confirm before retrieval"
pending_confirmations = {}


def ollama_generate(prompt: str) -> Optional[str]:
    """POST to Ollama /api/generate (non-streaming). Returns response text or None on failure."""
    if not ollama_base_url:
        return None
    url = f"{ollama_base_url}/api/generate"
    payload = json.dumps(
        {"model": ollama_model, "prompt": prompt, "stream": False}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=ollama_timeout) as resp:
            result = json.loads(resp.read().decode())
        out = (result.get("response") or "").strip()
        return out or None
    except urllib.error.URLError as e:
        log.warning("Ollama request failed (%s): %s", url, e)
        return None
    except Exception as e:
        log.warning("Ollama request error: %s", e)
        return None


def _extract_json_object(text: str) -> Optional[dict]:
    """Parse a JSON object from model output; tolerate extra prose or markdown fences."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


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
def retrieve_chunks(
    query: str,
    n_results: Optional[int] = None,
    where: Optional[dict] = None,
) -> list[str]:
    """
    Run semantic search: Chroma embeds the query and returns the top-N similar documents.
    Optional ``where`` filters metadata (e.g. only 📈Projects rows).
    """
    k = n_results if n_results is not None else chroma_n_results
    t0 = time.perf_counter()
    log.debug(
        "retrieve_chunks: start query=%r n_results=%s where=%s",
        query[:200],
        k,
        where,
    )
    qkwargs = {
        "query_texts": [query],
        "n_results": max(1, k),
    }
    if where:
        qkwargs["where"] = where

    for attempt in range(2):
        try:
            results = projects_collection.query(**qkwargs)
            break
        except chromadb.errors.InternalError as e:
            if attempt == 0:
                log.warning("Chroma query failed (will reopen DB once): %s", e)
                reconnect_chroma_client()
                continue
            raise

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
        "synthesize_answer_with_llm: chunks=%s ollama_base=%s",
        len(context_chunks),
        bool(ollama_base_url),
    )

    context = "\n\n---\n\n".join(
        f"[Chunk {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
    )

    prompt = (
        "You are a helpful assistant for PBS Wisconsin internal project data. "
        "Answer the user's question using ONLY the provided context chunks below. "
        "If the context is insufficient, say so clearly and suggest what might be missing. "
        "Be concise and accurate. Use English only.\n\n"
        f"Original user question:\n{original_question}\n\n"
        f"Clarified interpretation (used for retrieval):\n{clarified_interpretation}\n\n"
        f"Context from knowledge base:\n{context}"
    )

    t0 = time.perf_counter()
    text = ollama_generate(prompt)
    if text:
        log.info(
            "synthesize_answer_with_llm: Ollama OK in %.2fs, out_len=%s",
            time.perf_counter() - t0,
            len(text),
        )
        return text

    joined = "\n\n---\n\n".join(
        f"[Source {i + 1}]\n{chunk}" for i, chunk in enumerate(context_chunks)
    )
    return (
        "Here is what I found in the knowledge base (Ollama unreachable — showing raw chunks). "
        "Start your VPN/SSH tunnel to localhost:11434 if you expect a summarized answer:\n\n"
        + joined
    )


def rag_answer_with_retrieval(
    query_for_search: str,
    original_user_message: str,
    clarified_for_user: str,
) -> str:
    """
    Full RAG path: embed query + vector search + multiple chunks + LLM answer.
    """
    w = None
    if chroma_filter_projects_only and chroma_projects_table_id:
        w = {"table_id": chroma_projects_table_id}
        log.info("retrieve_chunks: scoping to Projects table_id=%s", chroma_projects_table_id)
    chunks = retrieve_chunks(query_for_search, where=w)
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

    if not ollama_base_url:
        log.info("clarify_query_with_llm: OLLAMA_BASE_URL empty, using fallback")
        return fallback

    prompt = (
        "You rewrite user questions before retrieval. Reply with ONLY a JSON object (no markdown fences), "
        "with exactly these keys: \"clarified_for_user\", \"query_for_search\". Use English only. "
        "clarified_for_user: a polite confirmation sentence. "
        "query_for_search: concise keywords for vector search; include specific project or show titles "
        "from the user message verbatim when present.\n\n"
        f"Original user question:\n{user_query}"
    )

    t0 = time.perf_counter()
    log.info("clarify_query_with_llm: calling Ollama model=%s", ollama_model)
    content = ollama_generate(prompt)
    parsed = _extract_json_object(content or "") if content else None
    if not parsed:
        log.warning("clarify_query_with_llm: bad or empty JSON from Ollama, using fallback")
        return fallback

    clarified_for_user = str(parsed.get("clarified_for_user", user_query) or user_query).strip()
    query_for_search = str(parsed.get("query_for_search", user_query) or user_query).strip()
    if not clarified_for_user:
        clarified_for_user = user_query
    if not query_for_search:
        query_for_search = user_query

    log.info(
        "clarify_query_with_llm: OK in %.2fs",
        time.perf_counter() - t0,
    )
    return {
        "clarified_for_user": clarified_for_user,
        "query_for_search": query_for_search,
    }


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