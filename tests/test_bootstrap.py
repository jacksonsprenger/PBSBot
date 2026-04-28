from __future__ import annotations

import logging
import os
import ssl
import importlib
import sys
import types
from unittest import TestCase
from unittest.mock import patch


def load_bootstrap_module():
    sys.modules.pop("pbsbot.bootstrap", None)
    fake_certifi = types.SimpleNamespace(where=lambda: "/tmp/cert.pem")
    with patch.dict(sys.modules, {"certifi": fake_certifi}):
        return importlib.import_module("pbsbot.bootstrap")


class BootstrapTests(TestCase):
    def test_configure_runtime_sets_cert_env_and_logging_level(self) -> None:
        original_ssl_context = ssl._create_default_https_context
        bootstrap = load_bootstrap_module()

        try:
            with patch("pbsbot.bootstrap.certifi.where", return_value="/tmp/cert.pem"), patch(
                "pbsbot.bootstrap.logging.basicConfig"
            ) as basic_config, patch(
                "pbsbot.bootstrap.ssl.create_default_context",
                return_value="fake-context",
            ) as create_default_context:
                bootstrap.configure_runtime("debug")

            self.assertEqual(os.environ["SSL_CERT_FILE"], "/tmp/cert.pem")
            self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], "/tmp/cert.pem")
            basic_config.assert_called_once()
            self.assertEqual(basic_config.call_args.kwargs["level"], "DEBUG")
            self.assertTrue(basic_config.call_args.kwargs["force"])
            self.assertIs(ssl._create_default_https_context, create_default_context)
        finally:
            ssl._create_default_https_context = original_ssl_context

    def test_configure_runtime_uses_log_level_env_when_argument_is_missing(self) -> None:
        bootstrap = load_bootstrap_module()
        with patch.dict(os.environ, {"LOG_LEVEL": "warning"}), patch(
            "pbsbot.bootstrap.logging.basicConfig"
        ) as basic_config:
            bootstrap.configure_runtime()

        self.assertEqual(basic_config.call_args.kwargs["level"], "WARNING")

    def test_configure_runtime_defaults_to_info(self) -> None:
        bootstrap = load_bootstrap_module()
        with patch.dict(os.environ, {}, clear=True), patch(
            "pbsbot.bootstrap.logging.basicConfig"
        ) as basic_config:
            bootstrap.configure_runtime()

        self.assertEqual(basic_config.call_args.kwargs["level"], "INFO")
