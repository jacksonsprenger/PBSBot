"""Extended tests for pbsbot.llm.ollama — happy paths and additional edge cases."""

from __future__ import annotations

import json
import urllib.error
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.llm import ollama


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class GenerateHappyPathTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        state.settings = SimpleNamespace(
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
            ollama_timeout=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings

    def test_generate_returns_trimmed_response_on_success(self) -> None:
        payload = json.dumps({"response": "  The answer is 42.  "}).encode()

        with patch(
            "pbsbot.llm.ollama.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        ):
            result = ollama.generate("What is the answer?")

        self.assertEqual(result, "The answer is 42.")

    def test_generate_builds_correct_request(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["timeout"] = timeout
            captured["content_type"] = req.get_header("Content-type")
            return FakeResponse(b'{"response": "ok"}')

        with patch("pbsbot.llm.ollama.urllib.request.urlopen", side_effect=fake_urlopen):
            ollama.generate("test prompt")

        self.assertEqual(captured["url"], "http://localhost:11434/api/generate")
        self.assertEqual(captured["body"]["model"], "llama3.1:8b")
        self.assertEqual(captured["body"]["prompt"], "test prompt")
        self.assertFalse(captured["body"]["stream"])
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(captured["content_type"], "application/json")

    def test_generate_returns_none_on_generic_exception(self) -> None:
        with patch(
            "pbsbot.llm.ollama.urllib.request.urlopen",
            side_effect=RuntimeError("unexpected"),
        ):
            self.assertIsNone(ollama.generate("hello"))

    def test_generate_returns_none_when_response_key_missing(self) -> None:
        payload = json.dumps({"model": "test", "done": True}).encode()

        with patch(
            "pbsbot.llm.ollama.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        ):
            self.assertIsNone(ollama.generate("hello"))


class ExtractJsonObjectEdgeCases(TestCase):
    def test_extract_json_object_handles_nested_braces(self) -> None:
        text = '{"a": {"b": 1}}'
        result = ollama._extract_json_object(text)
        self.assertEqual(result, {"a": {"b": 1}})

    def test_extract_json_object_handles_json_in_markdown_fences(self) -> None:
        text = '```json\n{"clarified_for_user": "Status", "query_for_search": "status"}\n```'
        result = ollama._extract_json_object(text)
        self.assertEqual(result, {"clarified_for_user": "Status", "query_for_search": "status"})

    def test_extract_json_object_returns_none_for_none_input(self) -> None:
        self.assertIsNone(ollama._extract_json_object(None))

    def test_extract_json_object_handles_json_array(self) -> None:
        """Arrays are valid JSON but not dicts — regex won't match (no outer braces)."""
        self.assertIsNone(ollama._extract_json_object("[1, 2, 3]"))

    def test_extract_json_object_picks_first_object_from_multiple(self) -> None:
        text = 'First: {"a": 1} Second: {"b": 2}'
        result = ollama._extract_json_object(text)
        # re.search finds the largest match from first { to last }
        self.assertIsNotNone(result)


class ClarifyQueryExtendedTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        state.settings = SimpleNamespace(
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
            ollama_timeout=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings

    def test_clarify_query_with_only_clarified_for_user_empty(self) -> None:
        with patch.object(
            ollama,
            "generate",
            return_value='{"clarified_for_user": "", "query_for_search": "project deadlines"}',
        ):
            result = ollama.clarify_query_with_llm("when are deadlines?")

        self.assertEqual(result["clarified_for_user"], "when are deadlines?")
        self.assertEqual(result["query_for_search"], "project deadlines")

    def test_clarify_query_with_only_query_for_search_empty(self) -> None:
        with patch.object(
            ollama,
            "generate",
            return_value='{"clarified_for_user": "You want project deadlines.", "query_for_search": ""}',
        ):
            result = ollama.clarify_query_with_llm("when are deadlines?")

        self.assertEqual(result["clarified_for_user"], "You want project deadlines.")
        self.assertEqual(result["query_for_search"], "when are deadlines?")

    def test_clarify_query_with_extra_keys_in_response_ignores_them(self) -> None:
        response = json.dumps({
            "clarified_for_user": "Status check",
            "query_for_search": "status",
            "extra_key": "ignored",
        })

        with patch.object(ollama, "generate", return_value=response):
            result = ollama.clarify_query_with_llm("status?")

        self.assertEqual(result, {"clarified_for_user": "Status check", "query_for_search": "status"})

    def test_clarify_query_includes_user_query_in_prompt(self) -> None:
        prompts: list[str] = []

        def fake_generate(prompt: str):
            prompts.append(prompt)
            return '{"clarified_for_user": "X", "query_for_search": "Y"}'

        with patch.object(ollama, "generate", side_effect=fake_generate):
            ollama.clarify_query_with_llm("What shows are airing next week?")

        self.assertIn("What shows are airing next week?", prompts[0])
        self.assertIn("query_for_search", prompts[0])


class SynthesizeAnswerExtendedTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        state.settings = SimpleNamespace(
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
            ollama_timeout=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings

    def test_synthesize_prompt_includes_all_sections(self) -> None:
        prompts: list[str] = []

        def fake_generate(prompt: str):
            prompts.append(prompt)
            return "Answer text"

        with patch.object(ollama, "generate", side_effect=fake_generate):
            ollama.synthesize_answer_with_llm(
                "Original Q", "Clarified Q", ["chunk1", "chunk2"]
            )

        prompt = prompts[0]
        self.assertIn("Original user question:", prompt)
        self.assertIn("Original Q", prompt)
        self.assertIn("Clarified interpretation", prompt)
        self.assertIn("Clarified Q", prompt)
        self.assertIn("[Chunk 1]", prompt)
        self.assertIn("chunk1", prompt)
        self.assertIn("[Chunk 2]", prompt)
        self.assertIn("chunk2", prompt)
        self.assertIn("PBS Wisconsin", prompt)

    def test_synthesize_fallback_formats_multiple_chunks_as_sources(self) -> None:
        with patch.object(ollama, "generate", return_value=None):
            out = ollama.synthesize_answer_with_llm("Q", "C", ["Alpha", "Beta", "Gamma"])

        self.assertIn("[Source 1]\nAlpha", out)
        self.assertIn("[Source 2]\nBeta", out)
        self.assertIn("[Source 3]\nGamma", out)
        self.assertIn("Ollama unreachable", out)

    def test_synthesize_with_single_chunk(self) -> None:
        with patch.object(ollama, "generate", return_value="Single chunk answer"):
            out = ollama.synthesize_answer_with_llm("Q", "C", ["only one chunk"])

        self.assertEqual(out, "Single chunk answer")
