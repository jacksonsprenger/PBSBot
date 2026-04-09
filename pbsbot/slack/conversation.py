"""Slack conversation state: intent picker → thread question → button confirm → RAG."""

from __future__ import annotations

import logging

from pbsbot import state
from pbsbot.llm.ollama import clarify_query_with_llm
from pbsbot.rag.pipeline import rag_answer_with_retrieval, route_query
from pbsbot.slack.blocks import confirm_blocks, intent_followup_text

log = logging.getLogger("pbs_bot")

# After user picks intent: wait for their question in this thread (parent ts = root message).
intent_awaiting: dict[str, dict[str, str]] = {}
# After clarify: same shape as before + route_override from intent.
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


def set_intent_session(conv_key: str, root_ts: str, route: str) -> None:
    intent_awaiting[conv_key] = {"root_ts": root_ts, "route": route}
    pending_confirmations.pop(conv_key, None)
    log.info("intent session: key=%s route=%s root_ts=%s", conv_key, route, root_ts)


def clear_intent_session(conv_key: str) -> None:
    intent_awaiting.pop(conv_key, None)


def reset_session_for_fresh_menu(conv_key: str) -> None:
    """New @mention: drop in-flight thread flows for this user in this channel."""
    intent_awaiting.pop(conv_key, None)
    pending_confirmations.pop(conv_key, None)


def is_awaiting_question_in_thread(conv_key: str, message_thread_ts: str | None) -> bool:
    sess = intent_awaiting.get(conv_key)
    if not sess or not message_thread_ts:
        return False
    return sess["root_ts"] == message_thread_ts


def consume_question_and_clarify(
    conv_key: str,
    question_text: str,
) -> tuple[list[dict] | None, str | None]:
    """
    Move from intent → pending confirm. Returns (confirm blocks, error_message).
    """
    sess = intent_awaiting.pop(conv_key, None)
    if not sess:
        return None, "That menu expired. Mention the bot again to pick a topic."

    route_override = sess["route"]
    log.info("question in thread: key=%s route=%s preview=%r", conv_key, route_override, question_text[:120])

    clarification = clarify_query_with_llm(question_text)
    pending_confirmations[conv_key] = {
        **clarification,
        "original_user_message": question_text,
        "route_override": route_override,
        "thread_root_ts": sess["root_ts"],
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


def cancel_confirmation(conv_key: str) -> str:
    pending = pending_confirmations.pop(conv_key, None)
    if not pending:
        log.info("confirmation no: key=%s (nothing pending)", conv_key)
        return "Nothing to cancel here. Mention the bot to open the menu again."

    root = pending.get("thread_root_ts")
    route = pending.get("route_override", "projects")
    if root and route:
        intent_awaiting[conv_key] = {"root_ts": str(root), "route": str(route)}
    log.info("confirmation no: key=%s restored_intent=%s", conv_key, True)
    return (
        "No problem. *Type your revised question in this thread* (same topic). "
        "Or mention the bot for the full menu again."
    )


def has_pending_confirmation(conv_key: str) -> bool:
    return conv_key in pending_confirmations
