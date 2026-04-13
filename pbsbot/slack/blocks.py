"""Slack Block Kit layouts for PBS bot UI."""

from __future__ import annotations

import json

# Modal: must match Bolt @app.view callback_id and state.keys below.
QUESTION_MODAL_CALLBACK_ID = "pbs_question_submit"
QUESTION_BLOCK_ID = "pbs_q_block"
QUESTION_INPUT_ACTION_ID = "pbs_q_input"


def intent_picker_blocks(user_id: str) -> list[dict]:
    """Large greeting + category buttons (inspired by Slackbot-style quick actions)."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "PBS Wisconsin Assistant",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Hi <@{user_id}>! *How can I help today?*\n"
                    "_Choose a topic — a form will open where you can type your question (no @ mention needed)._"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*📋 Project information*\n"
                    "Schedules, promos, and project details from our knowledge base."
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Select", "emoji": True},
                "action_id": "pbs_intent",
                "value": "projects",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*👥 Staff & roles*\n"
                    "Who works on what, teams, and role-related questions."
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Select", "emoji": True},
                "action_id": "pbs_intent",
                "value": "staff",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*✅ Tasks & deadlines*\n"
                    "Milestones, due dates, and task-related lookups."
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Select", "emoji": True},
                "action_id": "pbs_intent",
                "value": "tasks",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*📇 Contacts & partners*\n"
                    "Emails, phones, and external contacts when available."
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Select", "emoji": True},
                "action_id": "pbs_intent",
                "value": "contacts",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_Use Submit in the form for your question; Yes/No search confirmation uses the buttons below that message._",
                }
            ],
        },
    ]


def confirm_blocks(clarified_for_user: str) -> list[dict]:
    """Clarification summary + Yes / No as clickable buttons."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*I understood your question as:*\n"
                    f"_{clarified_for_user}_\n\n"
                    "Ready to search the knowledge base?"
                ),
            },
        },
        {
            "type": "actions",
            "block_id": "pbs_confirm_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Yes, search",
                        "emoji": True,
                    },
                    "style": "primary",
                    "action_id": "pbs_confirm_yes",
                    "value": "yes",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✏️ No, let me rephrase",
                        "emoji": True,
                    },
                    "action_id": "pbs_confirm_no",
                    "value": "no",
                },
            ],
        },
    ]


def route_label(route: str) -> str:
    labels = {
        "projects": "Project information",
        "staff": "Staff & roles",
        "tasks": "Tasks & deadlines",
        "contacts": "Contacts & partners",
    }
    return labels.get(route, "this topic")


def build_question_modal_view(route: str, private_metadata: str) -> dict:
    """Modal with multiline question field (Slack does not allow inputs inside channel messages)."""
    title = route_label(route)
    return {
        "type": "modal",
        "callback_id": QUESTION_MODAL_CALLBACK_ID,
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "Ask PBS", "emoji": True},
        "submit": {"type": "plain_text", "text": "Submit", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Topic:* {title}\nEnter your question below, then press *Submit*.",
                },
            },
            {
                "type": "input",
                "block_id": QUESTION_BLOCK_ID,
                "label": {"type": "plain_text", "text": "Your question", "emoji": True},
                "element": {
                    "type": "plain_text_input",
                    "action_id": QUESTION_INPUT_ACTION_ID,
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Tell me about the Badger project promo dates",
                    },
                },
            },
        ],
    }


def question_modal_private_metadata(channel_id: str, user_id: str, route: str) -> str:
    return json.dumps({"c": channel_id, "u": user_id, "r": route})


def rephrase_question_blocks(route: str) -> list[dict]:
    """After “No” on confirm — reopen the question modal via button (needs interactive trigger)."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "No problem. Click below to open the question form again for the same topic.",
            },
        },
        {
            "type": "actions",
            "block_id": "pbs_rephrase_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Enter question again", "emoji": True},
                    "action_id": "pbs_open_question",
                    "value": route,
                },
            ],
        },
    ]
