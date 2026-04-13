"""Slack Socket Mode app entry."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from pbsbot.bootstrap import configure_runtime
from pbsbot.chroma.store import ChromaStore
from pbsbot.config import load_settings
from pbsbot import state
from pbsbot.slack.handlers import register

log = logging.getLogger("pbs_bot")


def run() -> None:
    load_dotenv()
    settings = load_settings()
    configure_runtime(settings.log_level)

    chroma_store = ChromaStore(settings)
    state.init(settings, chroma_store)

    log.info(
        "Ollama: base_url=%s model=%s (set OLLAMA_BASE_URL / OLLAMA_MODEL to override)",
        settings.ollama_base_url,
        settings.ollama_model,
    )

    app = App(token=settings.slack_bot_token)
    register(app)

    handler = SocketModeHandler(app, settings.slack_app_token)
    log.info("PBS Bot Socket Mode handler starting (set LOG_LEVEL=DEBUG for verbose logs)")
    print("🤖 PBS Bot is running!")
    handler.start()
