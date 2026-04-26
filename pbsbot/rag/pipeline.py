"""Retrieval + grounded answer assembly (RAG feature)."""

from __future__ import annotations

import logging
import time

from pbsbot import state
from pbsbot.llm.ollama import synthesize_answer_with_llm

log = logging.getLogger("pbs_bot")

ROUTE_TABLE_NAMES = {
    "tasks": "Tasks",
    "contacts": "Contacts",
    "staff": "Staff",
}


def route_query(query: str) -> str:
    q = query.lower()
    if "task" in q:
        return "tasks"
    if "contact" in q or "email" in q or "phone" in q:
        return "contacts"
    if "staff" in q or "who is" in q:
        return "staff"
    return "projects"


def retrieval_filter_for_route(route: str) -> dict | None:
    s = state.settings
    assert s is not None

    if route == "projects":
        if s.chroma_filter_projects_only and s.chroma_projects_table_id:
            log.info(
                "retrieve_chunks: scoping to Projects table_id=%s",
                s.chroma_projects_table_id,
            )
            return {"table_id": s.chroma_projects_table_id}
        return None

    table_name = ROUTE_TABLE_NAMES.get(route)
    if table_name:
        log.info("retrieve_chunks: scoping to %s table_name=%s", route, table_name)
        return {"table_name": table_name}

    return None


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
    if not chunks and where and selected_route != "projects":
        log.info(
            "retrieve_chunks: no chunks for route=%s where=%s; retrying without filter",
            selected_route,
            where,
        )
        chunks = store.retrieve_chunks(query_for_search)
    out = synthesize_answer_with_llm(
        original_user_message,
        clarified_for_user,
        chunks,
    )
    log.info("rag_answer_with_retrieval: total %.2fs", time.perf_counter() - t0)
    return out
