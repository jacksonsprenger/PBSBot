"""Bolt event wiring."""

from __future__ import annotations

import logging

from slack_bolt import App

from pbsbot.slack.conversation import (
    get_conversation_key,
    handle_user_query_flow,
    is_no,
    is_yes,
    normalize_mention_text,
    pending_confirmations,
)

log = logging.getLogger("pbs_bot")


def register(app: App) -> None:
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

        if channel_type in ("channel", "group", "mpim", ""):
            conversation_key = get_conversation_key(channel, user)
            if conversation_key not in pending_confirmations:
                log.debug("channel message ignored (no pending): key=%s", conversation_key)
                return
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
