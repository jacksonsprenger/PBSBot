"""Retrieval + grounded answer assembly (RAG feature)."""

from __future__ import annotations

import logging
import time

from pbsbot import state
from pbsbot.llm.ollama import synthesize_answer_with_llm

log = logging.getLogger("pbs_bot")


def route_query(query: str) -> str:
    # figure out which Airtable table to search based on keywords in the question
    q = query.lower()

    if any(word in q for word in ("task", "deadline", "due", "milestone")):
        return "tasks"

    if any(word in q for word in ("contact", "email", "phone", "partner")):
        return "contacts"

    if any(word in q for word in ("staff", "role", "who is", "team", "department")):
        return "staff"

    return "projects"


def retrieval_filter_for_route(route: str) -> dict | None:
    # build a chroma "where" filter using the table_id from config
    # returns None if no table_id is set (searches everything)
    s = state.settings
    assert s is not None

    selected_route = (route or "projects").strip().lower()
    table_id = s.route_table_ids.get(selected_route, "").strip()

    if not table_id:
        log.warning(
            "retrieve_chunks: no table_id configured for route=%s; searching all tables",
            selected_route,
        )
        return None

    log.info(
        "retrieve_chunks: scoping route=%s table_id=%s",
        selected_route,
        table_id,
    )
    return {"table_id": table_id}


def rag_answer_with_retrieval(
    query_for_search: str,
    original_user_message: str,
    clarified_for_user: str,
    route: str | None = None,
) -> str:
    store = state.chroma_store
    s = state.settings
    assert store is not None and s is not None

    selected_route = route or route_query(query_for_search)
    where = retrieval_filter_for_route(selected_route)

    t0 = time.perf_counter()
    chunks = store.retrieve_chunks(query_for_search, where=where)

    out = synthesize_answer_with_llm(
        original_user_message,
        clarified_for_user,
        chunks,
    )
    log.info(
        "rag_answer_with_retrieval: route=%s total %.2fs",
        selected_route,
        time.perf_counter() - t0,
    )
    return out