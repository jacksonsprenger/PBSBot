# _resolve_ollama_base_url: trailing slash, whitespace, docker detection
from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from pbsbot import config


class ResolveOllamaBaseUrlTests(TestCase):
    def test_whitespace_only_env_falls_back_to_local(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "   "}, clear=True), \
             patch("pbsbot.config.os.path.exists", return_value=False):
            url = config._resolve_ollama_base_url()

        self.assertEqual(url, "http://127.0.0.1:11434")

    def test_env_with_trailing_slash_is_stripped(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://custom:11434/"}, clear=True):
            url = config._resolve_ollama_base_url()

        self.assertEqual(url, "http://custom:11434")

    def test_env_without_trailing_slash_is_unchanged(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://custom:11434"}, clear=True):
            url = config._resolve_ollama_base_url()

        self.assertEqual(url, "http://custom:11434")

    def test_env_with_multiple_trailing_slashes(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://host:11434///"}, clear=True):
            url = config._resolve_ollama_base_url()

        # rstrip("/") removes all trailing slashes
        self.assertEqual(url, "http://host:11434")

    def test_docker_detection_only_when_env_is_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch("pbsbot.config.os.path.exists", return_value=True) as exists:
            url = config._resolve_ollama_base_url()

        exists.assert_called_once_with("/.dockerenv")
        self.assertEqual(url, "http://host.docker.internal:11434")


class SettingsFrozenTests(TestCase):
    def test_settings_dataclass_is_immutable(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch("pbsbot.config.os.path.exists", return_value=False):
            settings = config.load_settings()

        with self.assertRaises(AttributeError):
            settings.ollama_model = "changed"

    def test_settings_log_level_is_uppercased(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "warning"}, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.log_level, "WARNING")
