"""Retrieval + grounded answer assembly (RAG feature)."""

from __future__ import annotations

import logging
import time

from pbsbot import state
from pbsbot.llm.ollama import synthesize_answer_with_llm

log = logging.getLogger("pbs_bot")


def route_query(query: str) -> str:
    q = query.lower()
    if "task" in q:
        return "tasks"
    if "contact" in q or "email" in q or "phone" in q:
        return "contacts"
    if "staff" in q or "who is" in q:
        return "staff"
    return "projects"


def rag_answer_with_retrieval(
    query_for_search: str,
    original_user_message: str,
    clarified_for_user: str,
) -> str:
    store = state.chroma_store
    s = state.settings
    assert store is not None and s is not None

    w = None
    if s.chroma_filter_projects_only and s.chroma_projects_table_id:
        w = {"table_id": s.chroma_projects_table_id}
        log.info("retrieve_chunks: scoping to Projects table_id=%s", s.chroma_projects_table_id)

    t0 = time.perf_counter()
    chunks = store.retrieve_chunks(query_for_search, where=w)
    out = synthesize_answer_with_llm(
        original_user_message,
        clarified_for_user,
        chunks,
    )
    log.info("rag_answer_with_retrieval: total %.2fs", time.perf_counter() - t0)
    return out
