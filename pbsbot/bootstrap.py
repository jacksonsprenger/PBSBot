"""Process-wide SSL + logging. Import and call configure_runtime() before Chroma/HTTP."""

from __future__ import annotations

import logging
import os
import ssl

import certifi


def configure_runtime(log_level: str | None = None) -> None:
    level = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    ssl._create_default_https_context = ssl.create_default_context
