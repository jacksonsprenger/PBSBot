# selected_route param in handle_user_query_flow + route stored in pending
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.slack import conversation


class SelectedRouteOverrideTests(TestCase):

    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(max_slack_chars=3500)
        state.chroma_store = None
        conversation.pending_confirmations.clear()

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store
        conversation.pending_confirmations.clear()

    def test_selected_route_overrides_auto_detected_route(self) -> None:
        clarification = {
            "clarified_for_user": "You want project info.",
            "query_for_search": "project info",
        }

        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "project info", selected_route="tasks")

        pending = conversation.pending_confirmations["C1:U1"]
        self.assertEqual(pending["route"], "tasks")

    def test_selected_route_none_uses_auto_detection(self) -> None:
        clarification = {
            "clarified_for_user": "You want task deadlines.",
            "query_for_search": "task deadlines",
        }

        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "What tasks are due?")

        pending = conversation.pending_confirmations["C1:U1"]
        self.assertEqual(pending["route"], "tasks")

    def test_selected_route_contacts(self) -> None:
        clarification = {
            "clarified_for_user": "Contact info.",
            "query_for_search": "contact info",
        }

        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "something", selected_route="contacts")

        pending = conversation.pending_confirmations["C1:U1"]
        self.assertEqual(pending["route"], "contacts")

    def test_selected_route_staff(self) -> None:
        clarification = {
            "clarified_for_user": "Staff info.",
            "query_for_search": "staff info",
        }

        with patch.object(conversation, "clarify_query_with_llm", return_value=clarification):
            conversation.handle_user_query_flow("U1", "C1", "something", selected_route="staff")

        pending = conversation.pending_confirmations["C1:U1"]
        self.assertEqual(pending["route"], "staff")


class PendingRouteConfirmationTests(TestCase):

    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(max_slack_chars=3500)
        state.chroma_store = None
        conversation.pending_confirmations.clear()

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store
        conversation.pending_confirmations.clear()

    def test_stored_route_is_used_on_yes_confirmation(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "budget info",
            "clarified_for_user": "Budget info.",
            "original_user_message": "Tell me the budget",
            "route": "contacts",
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer") as rag:
            conversation.handle_user_query_flow("U1", "C1", "yes")

        rag.assert_called_once_with(
            "budget info",
            "Tell me the budget",
            "Budget info.",
            route="contacts",
        )

    def test_missing_route_key_in_pending_falls_back_to_auto_detection(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "tasks due this week",
            "clarified_for_user": "Tasks due.",
            "original_user_message": "What tasks are due?",
            # no "route" key
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer") as rag:
            conversation.handle_user_query_flow("U1", "C1", "yes")

        rag.assert_called_once_with(
            "tasks due this week",
            "What tasks are due?",
            "Tasks due.",
            route="tasks",
        )

    def test_empty_route_in_pending_falls_back_to_auto_detection(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "email for Jane",
            "clarified_for_user": "Jane's email.",
            "original_user_message": "What is Jane's email?",
            "route": "",
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer") as rag:
            conversation.handle_user_query_flow("U1", "C1", "yes")

        rag.assert_called_once_with(
            "email for Jane",
            "What is Jane's email?",
            "Jane's email.",
            route="contacts",
        )
