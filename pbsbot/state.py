"""Wired in pbsbot.slack.app before handlers run."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pbsbot.chroma.store import ChromaStore
    from pbsbot.config import Settings

settings: Settings | None = None
chroma_store: ChromaStore | None = None


def init(settings_: Settings, chroma_store_: ChromaStore) -> None:
    global settings, chroma_store
    settings = settings_
    chroma_store = chroma_store_
