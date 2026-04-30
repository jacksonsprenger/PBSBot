from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from pbsbot import state


class StateTests(TestCase):
    def test_init_sets_process_wide_settings_and_store(self) -> None:
        original_settings = state.settings
        original_store = state.chroma_store
        settings = SimpleNamespace(name="settings")
        store = SimpleNamespace(name="store")

        try:
            state.init(settings, store)

            self.assertIs(state.settings, settings)
            self.assertIs(state.chroma_store, store)
        finally:
            state.settings = original_settings
            state.chroma_store = original_store

