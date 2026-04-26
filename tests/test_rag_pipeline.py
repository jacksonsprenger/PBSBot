from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.rag import pipeline


class FakeStore:
    def __init__(self, responses: list[list[str]]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def retrieve_chunks(self, query: str, n_results=None, where=None):
        self.calls.append({"query": query, "n_results": n_results, "where": where})
        if self.responses:
            return self.responses.pop(0)
        return []


class RagPipelineTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            chroma_projects_table_id="tblProjects",
            chroma_n_results=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store

    def test_project_route_uses_projects_table_filter(self) -> None:
        store = FakeStore([["project chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer") as synth:
            out = pipeline.rag_answer_with_retrieval("project status", "Project status?", "Project status")

        self.assertEqual(out, "answer")
        self.assertEqual(store.calls, [{"query": "project status", "n_results": None, "where": {"table_id": "tblProjects"}}])
        synth.assert_called_once_with("Project status?", "Project status", ["project chunk"])

    def test_project_route_can_disable_projects_filter(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=False,
            chroma_projects_table_id="tblProjects",
            chroma_n_results=5,
        )
        store = FakeStore([["chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval("project status", "Project status?", "Project status")

        self.assertIsNone(store.calls[0]["where"])

    def test_non_project_route_retries_without_filter_when_filtered_search_is_empty(self) -> None:
        store = FakeStore([[], ["fallback chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer") as synth:
            out = pipeline.rag_answer_with_retrieval(
                "tasks due this week",
                "What tasks are due?",
                "Tasks due this week",
                route="tasks",
            )

        self.assertEqual(out, "answer")
        self.assertEqual(
            store.calls,
            [
                {"query": "tasks due this week", "n_results": None, "where": {"table_name": "Tasks"}},
                {"query": "tasks due this week", "n_results": None, "where": None},
            ],
        )
        synth.assert_called_once_with("What tasks are due?", "Tasks due this week", ["fallback chunk"])

    def test_unknown_route_uses_unfiltered_retrieval(self) -> None:
        store = FakeStore([["chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval("anything", "Anything?", "Anything", route="unknown")

        self.assertIsNone(store.calls[0]["where"])

