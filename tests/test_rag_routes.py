from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.rag.pipeline import retrieval_filter_for_route, route_query
from pbsbot.slack import conversation


class RagRouteTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            chroma_projects_table_id="tblProjects",
            max_slack_chars=3500,
        )
        conversation.pending_confirmations.clear()

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store
        conversation.pending_confirmations.clear()

    def test_route_query_detects_supported_tables(self) -> None:
        self.assertEqual(route_query("What tasks are due this week?"), "tasks")
        self.assertEqual(route_query("What is Jane's email?"), "contacts")
        self.assertEqual(route_query("Who is the producer?"), "staff")
        self.assertEqual(route_query("Tell me about Big Red Barn"), "projects")

    def test_retrieval_filter_for_route_uses_metadata(self) -> None:
        self.assertEqual(retrieval_filter_for_route("projects"), {"table_id": "tblProjects"})
        self.assertEqual(retrieval_filter_for_route("tasks"), {"table_name": "Tasks"})
        self.assertEqual(retrieval_filter_for_route("contacts"), {"table_name": "Contacts"})
        self.assertEqual(retrieval_filter_for_route("staff"), {"table_name": "Staff"})

    def test_confirmed_task_question_calls_rag(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "tasks due this week",
            "clarified_for_user": "You want tasks due this week.",
            "original_user_message": "What tasks are due this week?",
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="task answer") as rag:
            answer = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertEqual(answer, "task answer")
        rag.assert_called_once_with(
            "tasks due this week",
            "What tasks are due this week?",
            "You want tasks due this week.",
            route="tasks",
        )
