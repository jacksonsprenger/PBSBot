# explore_schema: main() error paths, format_value edge cases
from __future__ import annotations

import importlib
import io
import sys
import types
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import patch


def load_explore_schema_module():
    sys.modules.pop("pbsbot.ingestion.explore_schema", None)
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_requests = types.SimpleNamespace()

    with patch.dict(sys.modules, {"dotenv": fake_dotenv, "requests": fake_requests}):
        return importlib.import_module("pbsbot.ingestion.explore_schema")


class ExploreSchemaMainTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_explore_schema_module()

    def test_main_prints_error_when_api_key_missing(self) -> None:
        out = io.StringIO()
        with patch.dict("os.environ", {"AIRTABLE_BASE_ID": "base123"}, clear=True), \
             redirect_stdout(out):
            self.module.main()

        self.assertIn("AIRTABLE_API_KEY missing", out.getvalue())

    def test_main_prints_error_when_base_id_missing(self) -> None:
        out = io.StringIO()
        with patch.dict("os.environ", {"AIRTABLE_API_KEY": "key"}, clear=True), \
             redirect_stdout(out):
            self.module.main()

        self.assertIn("AIRTABLE_BASE_ID missing", out.getvalue())

    def test_main_prints_api_error_on_request_failure(self) -> None:
        class FakeRequestException(Exception):
            def __init__(self):
                super().__init__("fail")
                self.response = types.SimpleNamespace(text="Unauthorized")

        fake_requests_exc = types.SimpleNamespace(RequestException=FakeRequestException)

        class FakeRequests:
            exceptions = fake_requests_exc

            def get(self, url, *, headers, timeout):
                raise FakeRequestException()

        out = io.StringIO()
        with patch.dict(
            "os.environ",
            {"AIRTABLE_API_KEY": "key", "AIRTABLE_BASE_ID": "base123"},
            clear=True,
        ), patch.object(self.module, "requests", FakeRequests()), \
             redirect_stdout(out):
            self.module.main()

        self.assertIn("API error:", out.getvalue())


class FormatValueExtendedTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_explore_schema_module()

    def test_format_value_with_empty_list(self) -> None:
        self.assertEqual(self.module.format_value([]), "")

    def test_format_value_with_dict_url_only(self) -> None:
        value = {"url": "https://example.test/image.png"}
        result = self.module.format_value(value)
        self.assertIn("https://example.test/image.png", result)

    def test_format_value_with_plain_dict_no_special_keys(self) -> None:
        value = {"id": "abc123", "type": "record"}
        result = self.module.format_value(value)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_format_value_with_integer(self) -> None:
        self.assertEqual(self.module.format_value(42), "42")

    def test_format_value_with_float(self) -> None:
        self.assertEqual(self.module.format_value(3.14), "3.14")

    def test_format_value_with_list_of_dicts_without_name_or_filename(self) -> None:
        value = [{"id": "a"}, {"id": "b"}]
        result = self.module.format_value(value)
        self.assertIsInstance(result, str)

    def test_format_value_with_single_item_list(self) -> None:
        value = [{"name": "Producer"}]
        self.assertEqual(self.module.format_value(value), "Producer")

    def test_format_value_with_exactly_four_list_items(self) -> None:
        value = [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}]
        result = self.module.format_value(value)
        self.assertNotIn("more", result)
        self.assertIn("A", result)
        self.assertIn("D", result)

    def test_format_value_with_string_containing_html_entities(self) -> None:
        value = "<p>Hello</p> <br/> World"
        result = self.module.format_value(value)
        self.assertNotIn("<p>", result)
        self.assertNotIn("<br/>", result)
        self.assertIn("Hello", result)
        self.assertIn("World", result)
