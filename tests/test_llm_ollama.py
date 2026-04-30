from __future__ import annotations

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


class OllamaClientTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        state.settings = SimpleNamespace(
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
            ollama_timeout=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings

    def test_extract_json_object_accepts_raw_json(self) -> None:
        self.assertEqual(
            ollama._extract_json_object('{"query_for_search": "status"}'),
            {"query_for_search": "status"},
        )

    def test_extract_json_object_finds_json_inside_extra_text(self) -> None:
        text = 'Here you go:\n{"clarified_for_user": "A", "query_for_search": "B"}\nThanks'

        self.assertEqual(
            ollama._extract_json_object(text),
            {"clarified_for_user": "A", "query_for_search": "B"},
        )

    def test_extract_json_object_returns_none_for_bad_json(self) -> None:
        self.assertIsNone(ollama._extract_json_object(""))
        self.assertIsNone(ollama._extract_json_object("not json"))
        self.assertIsNone(ollama._extract_json_object("{bad json}"))

    def test_clarify_query_falls_back_when_ollama_disabled(self) -> None:
        state.settings = SimpleNamespace(ollama_base_url="")

        with patch.object(ollama, "generate") as generate:
            out = ollama.clarify_query_with_llm("What is due?")

        generate.assert_not_called()
        self.assertEqual(
            out,
            {
                "clarified_for_user": "What is due?",
                "query_for_search": "What is due?",
            },
        )

    def test_clarify_query_uses_parsed_json_and_trims_values(self) -> None:
        with patch.object(
            ollama,
            "generate",
            return_value='{"clarified_for_user": "  Project status  ", "query_for_search": "  status  "}',
        ):
            out = ollama.clarify_query_with_llm("status?")

        self.assertEqual(
            out,
            {
                "clarified_for_user": "Project status",
                "query_for_search": "status",
            },
        )

    def test_clarify_query_falls_back_for_empty_or_bad_model_output(self) -> None:
        for model_output in (None, "not json", '{"clarified_for_user": "", "query_for_search": ""}'):
            with self.subTest(model_output=model_output), patch.object(
                ollama,
                "generate",
                return_value=model_output,
            ):
                self.assertEqual(
                    ollama.clarify_query_with_llm("Who owns this?"),
                    {
                        "clarified_for_user": "Who owns this?",
                        "query_for_search": "Who owns this?",
                    },
                )

    def test_synthesize_returns_no_context_message_without_calling_model(self) -> None:
        with patch.object(ollama, "generate") as generate:
            out = ollama.synthesize_answer_with_llm("Q", "Q", [])

        generate.assert_not_called()
        self.assertIn("could not find relevant information", out)

    def test_synthesize_returns_model_answer_when_available(self) -> None:
        prompts: list[str] = []

        def fake_generate(prompt: str) -> str:
            prompts.append(prompt)
            return "The project is on track."

        with patch.object(ollama, "generate", side_effect=fake_generate):
            out = ollama.synthesize_answer_with_llm("Status?", "status", ["Chunk A", "Chunk B"])

        self.assertEqual(out, "The project is on track.")
        self.assertIn("Chunk A", prompts[0])
        self.assertIn("Chunk B", prompts[0])
        self.assertIn("using ONLY the provided context", prompts[0])

    def test_synthesize_falls_back_to_raw_chunks_when_model_unreachable(self) -> None:
        with patch.object(ollama, "generate", return_value=None):
            out = ollama.synthesize_answer_with_llm("Status?", "status", ["Chunk A"])

        self.assertIn("Ollama unreachable", out)
        self.assertIn("[Source 1]\nChunk A", out)

    def test_generate_returns_none_on_url_error(self) -> None:
        with patch("pbsbot.llm.ollama.urllib.request.urlopen") as urlopen:
            urlopen.side_effect = urllib.error.URLError("connection refused")

            self.assertIsNone(ollama.generate("hello"))

    def test_generate_returns_none_when_ollama_base_url_is_empty(self) -> None:
        state.settings = SimpleNamespace(
            ollama_base_url="",
            ollama_model="llama3.1:8b",
            ollama_timeout=5,
        )

        with patch("pbsbot.llm.ollama.urllib.request.urlopen") as urlopen:
            self.assertIsNone(ollama.generate("hello"))

        urlopen.assert_not_called()

    def test_generate_returns_none_for_empty_model_response(self) -> None:
        with patch(
            "pbsbot.llm.ollama.urllib.request.urlopen",
            return_value=FakeResponse(b'{"response": "   "}'),
        ):
            self.assertIsNone(ollama.generate("hello"))

    def test_generate_returns_none_for_invalid_json_response(self) -> None:
        with patch(
            "pbsbot.llm.ollama.urllib.request.urlopen",
            return_value=FakeResponse(b"not json"),
        ):
            self.assertIsNone(ollama.generate("hello"))
