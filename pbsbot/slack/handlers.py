"""Bolt event wiring — Block Kit intents, modal question form, button confirm."""

from __future__ import annotations

import json
import logging

from slack_bolt import App
from slack_sdk.errors import SlackApiError

from pbsbot.slack.blocks import (
    QUESTION_BLOCK_ID,
    QUESTION_INPUT_ACTION_ID,
    QUESTION_MODAL_CALLBACK_ID,
    build_question_modal_view,
    intent_picker_blocks,
    question_modal_private_metadata,
)
from pbsbot.slack.conversation import (
    cancel_confirmation,
    clarify_and_set_pending,
    execute_confirmed_search,
    get_conversation_key,
    has_pending_confirmation,
    is_no,
    is_yes,
    pending_confirmations,
    pending_matches_message_channel_flow,
    reset_session_for_fresh_menu,
)

log = logging.getLogger("pbs_bot")

_IGNORE_MESSAGE_SUBTYPES = frozenset(
    {
        "message_changed",
        "message_deleted",
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
        "pinned_item",
        "unpinned_item",
        "ekm_access_denied",
        "reminder_add",
    }
)


def _open_question_modal(client, trigger_id: str, channel_id: str, user_id: str, route: str) -> None:
    meta = question_modal_private_metadata(channel_id, user_id, route)
    view = build_question_modal_view(route, meta)
    client.views_open(trigger_id=trigger_id, view=view)


def register(app: App) -> None:
    @app.action("pbs_intent")
    def on_intent(ack, body, client):
        ack()
        user = body["user"]["id"]
        channel = body["channel"]["id"]
        route = body["actions"][0]["value"]
        trigger_id = body.get("trigger_id")
        if not trigger_id:
            log.error("pbs_intent: missing trigger_id")
            return
        try:
            _open_question_modal(client, trigger_id, channel, user, route)
        except SlackApiError as e:
            log.warning("views_open failed: %s", e)
            try:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user,
                    text="Could not open the question form. Try again or mention the bot.",
                )
            except SlackApiError:
                pass

    @app.action("pbs_open_question")
    def on_open_question(ack, body, client):
        ack()
        user = body["user"]["id"]
        channel = body["channel"]["id"]
        route = body["actions"][0]["value"]
        trigger_id = body.get("trigger_id")
        if not trigger_id:
            log.error("pbs_open_question: missing trigger_id")
            return
        try:
            _open_question_modal(client, trigger_id, channel, user, route)
        except SlackApiError as e:
            log.warning("views_open (rephrase) failed: %s", e)

    @app.view(QUESTION_MODAL_CALLBACK_ID)
    def on_question_submit(ack, body, client):
        ack()
        view = body["view"]
        try:
            meta = json.loads(view.get("private_metadata") or "{}")
        except json.JSONDecodeError:
            log.error("invalid question modal private_metadata")
            return
        channel_id = meta.get("c")
        user_id = meta.get("u")
        route = meta.get("r")
        if not channel_id or not user_id or not route:
            log.error("question modal missing c/u/r in metadata")
            return

        values = view.get("state", {}).get("values", {})
        block = values.get(QUESTION_BLOCK_ID, {})
        inp = block.get(QUESTION_INPUT_ACTION_ID, {})
        question_text = (inp.get("value") or "").strip()

        conv_key = get_conversation_key(channel_id, user_id)
        blocks, err = clarify_and_set_pending(conv_key, channel_id, route, question_text)
        if err:
            try:
                client.chat_postMessage(channel=channel_id, text=err)
            except SlackApiError as e:
                log.warning("chat_postMessage error reply failed: %s", e)
            return
        assert blocks is not None
        try:
            client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text="Please confirm to search the knowledge base.",
            )
        except SlackApiError as e:
            log.warning("chat_postMessage confirm failed: %s", e)

    def on_confirm(ack, body, say):
        ack()
        user = body["user"]["id"]
        channel = body["channel"]["id"]
        conv_key = get_conversation_key(channel, user)
        value = body["actions"][0]["value"]

        if value == "yes":
            out = execute_confirmed_search(conv_key)
            say(channel=channel, text=out)
            return

        text, extra = cancel_confirmation(conv_key)
        if extra:
            say(channel=channel, text=text, blocks=extra)
        else:
            say(channel=channel, text=text)

    app.action("pbs_confirm_yes")(on_confirm)
    app.action("pbs_confirm_no")(on_confirm)

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
        if message.get("bot_id"):
            return
        sub = message.get("subtype")
        if sub and sub in _IGNORE_MESSAGE_SUBTYPES:
            return

        user = message.get("user")
        channel = message.get("channel")
        text = (message.get("text") or "").strip()
        channel_type = message.get("channel_type") or ""
        thread_ts = message.get("thread_ts")
        if thread_ts is not None:
            thread_ts = str(thread_ts)
        conv_key = get_conversation_key(channel, user)

        log.info(
            "event=message channel=%s channel_type=%s user=%s thread=%s subtype=%s text_preview=%r",
            channel,
            channel_type,
            user,
            thread_ts,
            sub,
            text[:80],
        )

        if not text:
            return

        pending = pending_confirmations.get(conv_key)
        if pending and pending_matches_message_channel_flow(pending, channel_type, thread_ts):
            if is_yes(text):
                out = execute_confirmed_search(conv_key)
                say(channel=channel, text=out)
                return
            if is_no(text):
                msg, extra = cancel_confirmation(conv_key)
                if extra:
                    say(channel=channel, text=msg, blocks=extra)
                else:
                    say(channel=channel, text=msg)
                return

        if channel_type == "im":
            if has_pending_confirmation(conv_key):
                return
            blocks = intent_picker_blocks(user)
            say(blocks=blocks, text="PBS Assistant — choose how we can help.")
            return

        log.debug("channel message ignored (no matching flow)")
