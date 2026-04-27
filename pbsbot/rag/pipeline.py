"""Retrieval + grounded answer assembly (RAG feature)."""

from __future__ import annotations

import logging
import time

from pbsbot import state
from pbsbot.llm.ollama import synthesize_answer_with_llm

log = logging.getLogger("pbs_bot")

VALID_ROUTES = {"projects", "tasks", "staff", "contacts"}


def route_query(query: str) -> str:
    q = query.lower()

    if any(word in q for word in ("task", "deadline", "due", "milestone")):
        return "tasks"

    if any(word in q for word in ("contact", "email", "phone", "partner")):
        return "contacts"

    if any(word in q for word in ("staff", "role", "who is", "team", "department")):
        return "staff"

    return "projects"


def _where_for_route(route: str) -> dict | None:
    s = state.settings
    assert s is not None

    table_id = s.route_table_ids.get(route, "").strip()
    if not table_id:
        log.warning("No table_id configured for route=%s; searching all tables", route)
        return None

    return {"table_id": table_id}


def rag_answer_with_retrieval(
    query_for_search: str,
    original_user_message: str,
    clarified_for_user: str,
    route: str = "projects",
) -> str:
    store = state.chroma_store
    s = state.settings
    assert store is not None and s is not None

    if route not in VALID_ROUTES:
        log.warning("Unknown route=%s; falling back to projects", route)
        route = "projects"

    where = _where_for_route(route)

    t0 = time.perf_counter()
    chunks = store.retrieve_chunks(query_for_search, where=where)

    out = synthesize_answer_with_llm(
        original_user_message,
        clarified_for_user,
        chunks,
    )

    log.info(
        "rag_answer_with_retrieval: route=%s total %.2fs",
        route,
        time.perf_counter() - t0,
    )
    return out