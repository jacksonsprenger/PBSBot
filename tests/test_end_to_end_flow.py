# Full conversation flow: question -> clarify -> confirm -> retrieve -> answer
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.slack import conversation


class FakeStore:
    def __init__(self, responses: list[list[str]]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def retrieve_chunks(self, query: str, n_results=None, where=None):
        self.calls.append({"query": query, "where": where})
        if self.responses:
            return self.responses.pop(0)
        return []


class EndToEndFlowTests(TestCase):

    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(
            max_slack_chars=3500,
            chroma_filter_projects_only=True,
            route_table_ids={"projects": "tblProj", "tasks": "tblTasks", "staff": "tblStaff", "contacts": "tblContacts"},
            chroma_n_results=5,
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b",
            ollama_timeout=5,
        )
        conversation.pending_confirmations.clear()

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store
        conversation.pending_confirmations.clear()

    def test_full_flow_project_question(self) -> None:
        store = FakeStore([["Project Alpha is on track."]])
        state.chroma_store = store

        clarification = {
            "clarified_for_user": "You want to know about Project Alpha.",
            "query_for_search": "Project Alpha status",
        }
        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            answer1 = conversation.handle_user_query_flow("U1", "C1", "How is Project Alpha?")

        self.assertIn("Reply `yes`", answer1)
        self.assertIn("C1:U1", conversation.pending_confirmations)

        with patch("pbsbot.llm.ollama.generate", return_value="Project Alpha is on track."):
            answer2 = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertIn("Project Alpha is on track", answer2)
        self.assertNotIn("C1:U1", conversation.pending_confirmations)
        # Should have used projects table_id filter
        self.assertEqual(store.calls[0]["where"], {"table_id": "tblProj"})

    def test_full_flow_task_question(self) -> None:
        store = FakeStore([["Task 1: Due Friday"]])
        state.chroma_store = store

        clarification = {
            "clarified_for_user": "You want tasks due this week.",
            "query_for_search": "tasks due this week",
        }
        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "What tasks are due?")

        with patch("pbsbot.llm.ollama.generate", return_value="Task 1 is due Friday."):
            answer = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertIn("Task 1", answer)
        self.assertEqual(store.calls[0]["where"], {"table_id": "tblTasks"})

    def test_full_flow_user_says_no_then_re_asks(self) -> None:
        clarification1 = {
            "clarified_for_user": "Wrong interpretation.",
            "query_for_search": "wrong query",
        }
        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification1):
            conversation.handle_user_query_flow("U1", "C1", "vague question")

        self.assertIn("C1:U1", conversation.pending_confirmations)

        # User says no
        answer_no = conversation.handle_user_query_flow("U1", "C1", "no")
        self.assertIn("Please ask your question again", answer_no)
        self.assertNotIn("C1:U1", conversation.pending_confirmations)

        # User asks again
        clarification2 = {
            "clarified_for_user": "Better interpretation.",
            "query_for_search": "better query",
        }
        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification2):
            answer_retry = conversation.handle_user_query_flow("U1", "C1", "clearer question")

        self.assertIn("Reply `yes`", answer_retry)
        self.assertIn("C1:U1", conversation.pending_confirmations)

    def test_two_users_independent_pending_state(self) -> None:
        clarification = {
            "clarified_for_user": "Question.",
            "query_for_search": "query",
        }

        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "question 1")
            conversation.handle_user_query_flow("U2", "C1", "question 2")

        self.assertIn("C1:U1", conversation.pending_confirmations)
        self.assertIn("C1:U2", conversation.pending_confirmations)

        conversation.handle_user_query_flow("U1", "C1", "no")
        self.assertNotIn("C1:U1", conversation.pending_confirmations)
        self.assertIn("C1:U2", conversation.pending_confirmations)

    def test_same_user_different_channels_independent(self) -> None:
        clarification = {
            "clarified_for_user": "Question.",
            "query_for_search": "query",
        }

        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "question in channel 1")
            conversation.handle_user_query_flow("U1", "C2", "question in channel 2")

        self.assertIn("C1:U1", conversation.pending_confirmations)
        self.assertIn("C2:U1", conversation.pending_confirmations)

    def test_task_query_uses_table_id_filter(self) -> None:
        store = FakeStore([["milestone data"]])
        state.chroma_store = store

        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "milestone progress",
            "clarified_for_user": "Milestone progress.",
            "original_user_message": "What milestones are done?",
            "route": "tasks",
        }

        with patch("pbsbot.llm.ollama.generate", return_value="Here is the progress."):
            answer = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertIn("progress", answer.lower())
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["where"], {"table_id": "tblTasks"})
