"""Environment-backed settings (single place for feature teams to extend)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _resolve_ollama_base_url() -> str:
    raw = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    if os.path.exists("/.dockerenv"):
        return "http://host.docker.internal:11434"
    return "http://127.0.0.1:11434"


@dataclass(frozen=True)
class Settings:
    slack_bot_token: str | None
    slack_app_token: str | None
    ollama_base_url: str
    ollama_model: str
    ollama_timeout: int
    chroma_n_results: int
    chroma_persist_dir: str
    chroma_projects_table_id: str
    chroma_filter_projects_only: bool
    route_table_ids: dict[str, str]
    max_slack_chars: int
    log_level: str


def load_settings() -> Settings:
    filt = os.getenv("CHROMA_FILTER_TO_PROJECTS_TABLE", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    projects_table_id = os.getenv(
        "AIRTABLE_PROJECTS_TABLE_ID",
        os.getenv("AIRTABLE_TABLE_ID", "tblU9LfZeVNicdB5e"),
    ).strip()

    return Settings(
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN"),
        slack_app_token=os.getenv("SLACK_APP_TOKEN"),
        ollama_base_url=_resolve_ollama_base_url(),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        ollama_timeout=int(os.getenv("OLLAMA_TIMEOUT", "120")),
        chroma_n_results=int(os.getenv("CHROMA_N_RESULTS", "5")),
        chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
        chroma_projects_table_id=projects_table_id,
        chroma_filter_projects_only=filt,
        route_table_ids={
            "projects": projects_table_id,
            "tasks": os.getenv("AIRTABLE_TASKS_TABLE_ID", "").strip(),
            "staff": os.getenv("AIRTABLE_STAFF_TABLE_ID", "").strip(),
            "contacts": os.getenv("AIRTABLE_CONTACTS_TABLE_ID", "").strip(),
        },
        max_slack_chars=int(os.getenv("MAX_SLACK_CHARS", "3500")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )