# RAG pipeline: auto-routing, case insensitivity, filter combos, retry logic
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


class RouteQueryExtendedTests(TestCase):
    def test_route_query_phone_keyword_routes_to_contacts(self) -> None:
        self.assertEqual(pipeline.route_query("What is the phone number?"), "contacts")

    def test_route_query_email_keyword_routes_to_contacts(self) -> None:
        self.assertEqual(pipeline.route_query("Send me the email address"), "contacts")

    def test_route_query_who_is_routes_to_staff(self) -> None:
        self.assertEqual(pipeline.route_query("who is the lead producer?"), "staff")

    def test_route_query_staff_keyword_routes_to_staff(self) -> None:
        self.assertEqual(pipeline.route_query("List all staff members"), "staff")

    def test_route_query_is_case_insensitive(self) -> None:
        self.assertEqual(pipeline.route_query("TASK deadlines"), "tasks")
        self.assertEqual(pipeline.route_query("EMAIL for John"), "contacts")
        self.assertEqual(pipeline.route_query("STAFF directory"), "staff")
        self.assertEqual(pipeline.route_query("WHO IS the manager"), "staff")

    def test_route_query_defaults_to_projects_for_general_queries(self) -> None:
        self.assertEqual(pipeline.route_query("Tell me about Big Red Barn"), "projects")
        self.assertEqual(pipeline.route_query("What is the budget?"), "projects")
        self.assertEqual(pipeline.route_query("show details"), "projects")

    def test_route_query_prefers_task_when_multiple_keywords_present(self) -> None:
        self.assertEqual(pipeline.route_query("task email from staff"), "tasks")

    def test_route_query_contact_over_staff_when_both_present(self) -> None:
        self.assertEqual(pipeline.route_query("contact info for staff member"), "contacts")


class RetrievalFilterExtendedTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            route_table_ids={"projects": "tblProjects", "tasks": "", "staff": "", "contacts": ""},
            chroma_n_results=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings

    def test_retrieval_filter_for_unknown_route_returns_none(self) -> None:
        self.assertIsNone(pipeline.retrieval_filter_for_route("unknown"))

    def test_retrieval_filter_for_projects_disabled_and_empty_id(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=False,
            route_table_ids={"projects": "", "tasks": "", "staff": "", "contacts": ""},
            chroma_n_results=5,
        )

        self.assertIsNone(pipeline.retrieval_filter_for_route("projects"))

    def test_retrieval_filter_for_projects_enabled_but_empty_id(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            route_table_ids={"projects": "", "tasks": "", "staff": "", "contacts": ""},
            chroma_n_results=5,
        )

        self.assertIsNone(pipeline.retrieval_filter_for_route("projects"))


class RagAnswerAutoRoutingTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            route_table_ids={"projects": "tblProjects", "tasks": "", "staff": "", "contacts": ""},
            chroma_n_results=5,
        )

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store

    def test_auto_routes_task_query_when_route_is_none(self) -> None:
        store = FakeStore([["task chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval(
                "What tasks are due?", "tasks due?", "Tasks due", route=None
            )

        self.assertEqual(store.calls[0]["where"], {"table_name": "Tasks"})

    def test_auto_routes_contact_query_when_route_is_none(self) -> None:
        store = FakeStore([["contact chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval(
                "What is the email for Jane?", "email Jane?", "Email Jane", route=None
            )

        self.assertEqual(store.calls[0]["where"], {"table_name": "Contacts"})

    def test_auto_routes_project_query_when_route_is_none(self) -> None:
        store = FakeStore([["project chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval(
                "Tell me about Big Red Barn", "Big Red Barn?", "Big Red Barn", route=None
            )

        self.assertEqual(store.calls[0]["where"], {"table_id": "tblProjects"})

    def test_staff_route_with_empty_results_retries_without_filter(self) -> None:
        store = FakeStore([[], ["fallback chunk"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval(
                "who is the producer?", "Who is the producer?", "Producer info", route="staff"
            )

        self.assertEqual(store.calls[0]["where"], {"table_name": "Staff"})
        self.assertIsNone(store.calls[1]["where"])

    def test_contacts_route_with_results_does_not_retry(self) -> None:
        store = FakeStore([["contact info"]])
        state.chroma_store = store

        with patch.object(pipeline, "synthesize_answer_with_llm", return_value="answer"):
            pipeline.rag_answer_with_retrieval(
                "email", "Email?", "email", route="contacts"
            )

        self.assertEqual(len(store.calls), 1)
