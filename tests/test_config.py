from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from pbsbot import config


class ConfigTests(TestCase):
    def test_load_settings_uses_local_defaults_outside_docker(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "pbsbot.config.os.path.exists", return_value=False
        ):
            settings = config.load_settings()

        self.assertIsNone(settings.slack_bot_token)
        self.assertIsNone(settings.slack_app_token)
        self.assertEqual(settings.ollama_base_url, "http://127.0.0.1:11434")
        self.assertEqual(settings.ollama_model, "llama3.1:8b")
        self.assertEqual(settings.ollama_timeout, 120)
        self.assertEqual(settings.chroma_n_results, 5)
        self.assertEqual(settings.chroma_persist_dir, "./chroma_db")
        self.assertEqual(settings.chroma_projects_table_id, "tblU9LfZeVNicdB5e")
        self.assertTrue(settings.chroma_filter_projects_only)
        self.assertEqual(settings.max_slack_chars, 3500)
        self.assertEqual(settings.log_level, "INFO")

    def test_load_settings_uses_docker_ollama_default_inside_container(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "pbsbot.config.os.path.exists", return_value=True
        ):
            settings = config.load_settings()

        self.assertEqual(settings.ollama_base_url, "http://host.docker.internal:11434")

    def test_load_settings_applies_env_overrides_and_strips_url(self) -> None:
        env = {
            "SLACK_BOT_TOKEN": "xoxb-token",
            "SLACK_APP_TOKEN": "xapp-token",
            "OLLAMA_BASE_URL": "http://llm.example.test:11434/",
            "OLLAMA_MODEL": "mistral",
            "OLLAMA_TIMEOUT": "30",
            "CHROMA_N_RESULTS": "9",
            "CHROMA_PERSIST_DIR": "/tmp/chroma",
            "AIRTABLE_TABLE_ID": " tblProjects ",
            "CHROMA_FILTER_TO_PROJECTS_TABLE": "no",
            "MAX_SLACK_CHARS": "500",
            "LOG_LEVEL": "debug",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.slack_bot_token, "xoxb-token")
        self.assertEqual(settings.slack_app_token, "xapp-token")
        self.assertEqual(settings.ollama_base_url, "http://llm.example.test:11434")
        self.assertEqual(settings.ollama_model, "mistral")
        self.assertEqual(settings.ollama_timeout, 30)
        self.assertEqual(settings.chroma_n_results, 9)
        self.assertEqual(settings.chroma_persist_dir, "/tmp/chroma")
        self.assertEqual(settings.chroma_projects_table_id, "tblProjects")
        self.assertFalse(settings.chroma_filter_projects_only)
        self.assertEqual(settings.max_slack_chars, 500)
        self.assertEqual(settings.log_level, "DEBUG")

    def test_filter_truthy_values_are_accepted(self) -> None:
        for value in ("1", "true", "yes"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"CHROMA_FILTER_TO_PROJECTS_TABLE": value}, clear=True
            ):
                self.assertTrue(config.load_settings().chroma_filter_projects_only)

