"""Slack conversation state: intent picker → modal question → button confirm → RAG."""

from __future__ import annotations

import logging

from pbsbot import state
from pbsbot.llm.ollama import clarify_query_with_llm
from pbsbot.rag.pipeline import rag_answer_with_retrieval, route_query
from pbsbot.slack.blocks import confirm_blocks, rephrase_question_blocks

log = logging.getLogger("pbs_bot")

# After clarify: + route_override from intent. thread_root_ts is None = main-channel flow.
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


def reset_session_for_fresh_menu(conv_key: str) -> None:
    """New @mention: drop in-flight flows for this user in this channel."""
    pending_confirmations.pop(conv_key, None)


def clarify_and_set_pending(
    conv_key: str,
    channel_id: str,
    route: str,
    question_text: str,
) -> tuple[list[dict] | None, str | None]:
    """Run clarify LLM and store pending confirmation. Returns (confirm blocks, error_message)."""
    q = question_text.strip()
    if not q:
        return None, "Please enter a question in the form."

    log.info("question (modal): key=%s route=%s preview=%r", conv_key, route, q[:120])

    clarification = clarify_query_with_llm(q)
    pending_confirmations[conv_key] = {
        **clarification,
        "original_user_message": q,
        "route_override": route,
        "thread_root_ts": None,
        "channel_id": channel_id,
    }
    blocks = confirm_blocks(clarification["clarified_for_user"])
    return blocks, None


def execute_confirmed_search(conv_key: str) -> str:
    pending = pending_confirmations.pop(conv_key, None)
    if not pending:
        return "That confirmation expired. Mention the bot to start again."

    query_for_search = pending["query_for_search"]
    original_user_message = pending.get("original_user_message", query_for_search)
    clarified_for_user = pending.get("clarified_for_user", query_for_search)
    forced = pending.get("route_override")
    route = forced if forced else route_query(query_for_search)

    log.info(
        "confirmation yes: route=%s (forced=%s) query_for_search=%r",
        route,
        forced,
        query_for_search[:200],
    )

    if route == "projects":
        answer = rag_answer_with_retrieval(
            query_for_search,
            original_user_message,
            clarified_for_user,
        )
        return truncate_for_slack(answer)

    return (
        f"_RAG search is enabled for **project information** right now._\n"
        f"You asked in the *{route}* category — try rephrasing as a project question, "
        "or pick *Project information* from the menu."
    )


def cancel_confirmation(conv_key: str) -> tuple[str, list[dict] | None]:
    pending = pending_confirmations.pop(conv_key, None)
    if not pending:
        log.info("confirmation no: key=%s (nothing pending)", conv_key)
        return "Nothing to cancel here. Mention the bot to open the menu again.", None

    route = str(pending.get("route_override", "projects"))
    log.info("confirmation no: key=%s (rephrase button)", conv_key)
    text = "Use the button below to open the question form again for the same topic."
    return text, rephrase_question_blocks(route)


def has_pending_confirmation(conv_key: str) -> bool:
    return conv_key in pending_confirmations


def pending_matches_message_channel_flow(
    pending: dict,
    channel_type: str,
    thread_ts: str | None,
) -> bool:
    """True if this user message should pair with a main-channel pending confirmation."""
    if pending.get("thread_root_ts") is not None:
        return bool(thread_ts) and str(pending.get("thread_root_ts")) == str(thread_ts)
    if channel_type == "im":
        return True
    return not thread_ts
