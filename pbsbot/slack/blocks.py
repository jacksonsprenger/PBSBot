"""Slack Block Kit layouts for PBS bot UI."""

from __future__ import annotations


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
                    "_Choose a topic below, then type your question in the thread._"
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
                    "text": "_You can confirm searches with the buttons—no need to @ mention the bot for Yes/No._",
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
                    "action_id": "pbs_confirm",
                    "value": "yes",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✏️ No, let me rephrase",
                        "emoji": True,
                    },
                    "action_id": "pbs_confirm",
                    "value": "no",
                },
            ],
        },
    ]


def intent_followup_text(route: str) -> str:
    labels = {
        "projects": "Project information",
        "staff": "Staff & roles",
        "tasks": "Tasks & deadlines",
        "contacts": "Contacts & partners",
    }
    title = labels.get(route, "this topic")
    return (
        f"You chose *{title}*.\n"
        "*Reply in this thread* with your question (you do not need to @ mention me here)."
    )
