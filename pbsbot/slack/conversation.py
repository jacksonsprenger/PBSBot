"""Slack-side dialog: confirmations, yes/no, truncation (Slack UX feature)."""

from __future__ import annotations

import logging

from pbsbot import state
from pbsbot.llm.ollama import clarify_query_with_llm
from pbsbot.rag.pipeline import rag_answer_with_retrieval, route_query

log = logging.getLogger("pbs_bot")

pending_confirmations: dict[str, dict] = {}


def truncate_for_slack(text: str, max_chars: int | None = None) -> str:
    s = state.settings
    assert s is not None
    cap = max_chars if max_chars is not None else s.max_slack_chars
    if len(text) <= cap:
        return text
    return text[: cap - 30].rstrip() + "\n\n_(Message truncated.)_"


def normalize_mention_text(text: str) -> str:
    cleaned = text.strip()
    parts = [p for p in cleaned.split() if not (p.startswith("<@") and p.endswith(">"))]
    return " ".join(parts).strip()


def is_yes(text: str) -> bool:
    return text.strip().lower() in {"yes", "y", "yeah", "yep", "correct"}


def is_no(text: str) -> bool:
    return text.strip().lower() in {"no", "n", "nope", "incorrect"}


def get_conversation_key(channel_id: str, user_id: str) -> str:
    return f"{channel_id}:{user_id}"


def handle_user_query_flow(user: str, channel: str, text: str) -> str:
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
            original_user_message = pending.get("original_user_message", query_for_search)
            clarified_for_user = pending.get("clarified_for_user", query_for_search)
            pending_confirmations.pop(conversation_key, None)

            route = route_query(query_for_search)
            log.info(
                "confirmation yes: route=%s query_for_search=%r",
                route,
                query_for_search[:200],
            )
            answer = rag_answer_with_retrieval(
                query_for_search,
                original_user_message,
                clarified_for_user,
                route=route,
            )
            return truncate_for_slack(answer)

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
