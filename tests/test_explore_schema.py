from __future__ import annotations

import importlib
import sys
import types
from unittest import TestCase
from unittest.mock import patch


def load_explore_schema_module():
    sys.modules.pop("pbsbot.ingestion.explore_schema", None)
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_requests = types.SimpleNamespace()

    with patch.dict(sys.modules, {"dotenv": fake_dotenv, "requests": fake_requests}):
        return importlib.import_module("pbsbot.ingestion.explore_schema")


class ExploreSchemaFormatValueTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_explore_schema_module()

    def test_format_value_handles_empty_and_boolean_values(self) -> None:
        self.assertEqual(self.module.format_value(None), "")
        self.assertEqual(self.module.format_value(True), "Yes")
        self.assertEqual(self.module.format_value(False), "No")

    def test_format_value_prefers_attachment_filename_over_url(self) -> None:
        value = {
            "url": "https://example.test/file.mov",
            "filename": "promo_cut.mov",
        }

        self.assertEqual(self.module.format_value(value), "promo_cut.mov")

    def test_format_value_summarizes_long_lists_and_dict_items(self) -> None:
        value = [
            {"name": "Producer"},
            {"filename": "promo.mov"},
            "Raw",
            "Published",
            "Extra",
        ]

        self.assertEqual(
            self.module.format_value(value),
            "Producer, promo.mov, Raw, Published (+1 more)",
        )

    def test_format_value_removes_html_and_collapses_whitespace(self) -> None:
        value = "  <b>Project</b>\n\n   status\tupdate  "

        self.assertEqual(self.module.format_value(value), "Project status update")

    def test_format_value_truncates_long_text_on_word_boundary(self) -> None:
        value = "word " * 40

        out = self.module.format_value(value)

        self.assertLessEqual(len(out), self.module.MAX_FIELD_VALUE_LEN + 3)
        self.assertTrue(out.endswith("..."))
