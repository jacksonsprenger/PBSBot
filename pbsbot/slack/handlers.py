"""Bolt event wiring — Block Kit intents, thread Q&A, button confirm."""

from __future__ import annotations

import logging

from slack_bolt import App

from pbsbot.slack.blocks import intent_followup_text, intent_picker_blocks
from pbsbot.slack.conversation import (
    cancel_confirmation,
    consume_question_and_clarify,
    execute_confirmed_search,
    get_conversation_key,
    has_pending_confirmation,
    intent_awaiting,
    is_awaiting_question_in_thread,
    is_no,
    is_yes,
    pending_confirmations,
    reset_session_for_fresh_menu,
    set_intent_session,
)

log = logging.getLogger("pbs_bot")


def _reply_thread_ts(message: dict) -> str:
    return message.get("thread_ts") or message["ts"]


def register(app: App) -> None:
    @app.action("pbs_intent")
    def on_intent(ack, body, say):
        ack()
        user = body["user"]["id"]
        channel = body["channel"]["id"]
        route = body["actions"][0]["value"]
        root_ts = body["message"]["ts"]
        conv_key = get_conversation_key(channel, user)
        set_intent_session(conv_key, root_ts, route)
        text = intent_followup_text(route)
        say(
            channel=channel,
            thread_ts=root_ts,
            text=text,
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                }
            ],
        )

    @app.action("pbs_confirm")
    def on_confirm(ack, body, say):
        ack()
        user = body["user"]["id"]
        channel = body["channel"]["id"]
        conv_key = get_conversation_key(channel, user)
        value = body["actions"][0]["value"]
        thread_ts = _reply_thread_ts(body["message"])

        if value == "yes":
            out = execute_confirmed_search(conv_key)
        else:
            out = cancel_confirmation(conv_key)

        say(channel=channel, thread_ts=thread_ts, text=out)

    @app.event("app_mention")
    def handle_mention(event, say):
        user = event["user"]
        channel = event.get("channel")
        raw_text = event.get("text", "") or ""
        log.info(
            "event=app_mention channel=%s user=%s raw_preview=%r",
            channel,
            user,
            raw_text[:200],
        )
        conv_key = get_conversation_key(channel, user)
        reset_session_for_fresh_menu(conv_key)

        blocks = intent_picker_blocks(user)
        say(
            blocks=blocks,
            text="PBS Assistant — choose how we can help.",
        )

    @app.event("message")
    def handle_message(message, say):
        if message.get("bot_id") or message.get("subtype"):
            return

        user = message.get("user")
        channel = message.get("channel")
        text = (message.get("text") or "").strip()
        channel_type = message.get("channel_type") or ""
        thread_ts = message.get("thread_ts")
        conv_key = get_conversation_key(channel, user)

        log.debug(
            "event=message channel=%s channel_type=%s user=%s thread=%s text_preview=%r",
            channel,
            channel_type,
            user,
            thread_ts,
            text[:80],
        )

        if not text:
            return

        # User typed their question under the intent prompt (same thread root as picker message).
        if is_awaiting_question_in_thread(conv_key, thread_ts):
            blocks, err = consume_question_and_clarify(conv_key, text)
            if err:
                say(channel=channel, thread_ts=thread_ts, text=err)
            else:
                assert blocks is not None
                say(
                    channel=channel,
                    thread_ts=thread_ts,
                    blocks=blocks,
                    text="Please confirm to search the knowledge base.",
                )
            return

        # Accessibility fallback: typed yes/no in the same thread as the confirm step.
        pending = pending_confirmations.get(conv_key)
        if pending and thread_ts and pending.get("thread_root_ts") == thread_ts:
            if is_yes(text):
                out = execute_confirmed_search(conv_key)
                say(channel=channel, thread_ts=thread_ts, text=out)
                return
            if is_no(text):
                out = cancel_confirmation(conv_key)
                say(channel=channel, thread_ts=thread_ts, text=out)
                return

        # DM: nudge if they skipped the thread
        if channel_type == "im" and intent_awaiting.get(conv_key) and not thread_ts:
            say(
                channel=channel,
                text=(
                    "Please reply *in the thread* under my last message (click “Reply in thread”) "
                    "so I can match your question to the topic you picked."
                ),
            )
            return

        # DM: show topic menu when not in an active thread flow.
        if channel_type == "im":
            if intent_awaiting.get(conv_key) or has_pending_confirmation(conv_key):
                return
            blocks = intent_picker_blocks(user)
            say(blocks=blocks, text="PBS Assistant — choose how we can help.")
            return

        # Public channel: ignore non-thread traffic (no more channel-level yes/no without thread).
        log.debug("channel message ignored (no matching thread flow)")
