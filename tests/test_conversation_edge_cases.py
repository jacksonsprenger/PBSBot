# Conversation flow edge cases: empty input, whitespace, missing pending keys
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.slack import conversation


class ConversationEdgeCaseTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(max_slack_chars=100)
        state.chroma_store = None
        conversation.pending_confirmations.clear()

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store
        conversation.pending_confirmations.clear()


    def test_normalize_mention_text_with_empty_string(self) -> None:
        self.assertEqual(conversation.normalize_mention_text(""), "")

    def test_normalize_mention_text_preserves_non_mention_angle_brackets(self) -> None:
        self.assertEqual(
            conversation.normalize_mention_text("Is 5 < 10 and 10 > 5?"),
            "Is 5 < 10 and 10 > 5?",
        )

    def test_normalize_mention_text_with_only_whitespace(self) -> None:
        self.assertEqual(conversation.normalize_mention_text("   "), "")


    def test_is_yes_strips_surrounding_whitespace(self) -> None:
        self.assertTrue(conversation.is_yes("  yes  "))
        self.assertTrue(conversation.is_yes("\tyep\n"))

    def test_is_no_strips_surrounding_whitespace(self) -> None:
        self.assertTrue(conversation.is_no("  no  "))
        self.assertTrue(conversation.is_no("\tnope\n"))

    def test_is_yes_rejects_partial_matches(self) -> None:
        self.assertFalse(conversation.is_yes("yes please"))
        self.assertFalse(conversation.is_yes("oh yes"))

    def test_is_no_rejects_partial_matches(self) -> None:
        self.assertFalse(conversation.is_no("no way"))
        self.assertFalse(conversation.is_no("say no"))


    def test_truncate_for_slack_leaves_shorter_text_unchanged(self) -> None:
        text = "Short message"
        self.assertEqual(conversation.truncate_for_slack(text), text)

    def test_truncate_for_slack_with_exactly_one_over_cap(self) -> None:
        text = "A" * 101
        out = conversation.truncate_for_slack(text)
        self.assertLessEqual(len(out), 100)
        self.assertTrue(out.endswith("_(Message truncated.)_"))

    def test_truncate_for_slack_with_zero_explicit_cap(self) -> None:
        text = "Hello world"
        out = conversation.truncate_for_slack(text, max_chars=40)
        self.assertLessEqual(len(out), 40)


    def test_yes_reply_uses_query_for_search_when_original_user_message_is_missing(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "clarified_for_user": "Project status",
            # omit original_user_message
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer") as rag:
            answer = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertEqual(answer, "answer")
        rag.assert_called_once()
        call_args = rag.call_args
        self.assertEqual(call_args[0][0], "project status")
        self.assertEqual(call_args[0][1], "project status")

    def test_yes_reply_uses_query_for_search_when_clarified_for_user_is_missing(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "original_user_message": "What is the project status?",
            # omit clarified_for_user
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer") as rag:
            answer = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertEqual(answer, "answer")
        call_args = rag.call_args
        self.assertEqual(call_args[0][2], "project status")


    def test_yes_variant_yep_triggers_confirmation_flow(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "clarified_for_user": "Project status",
            "original_user_message": "status?",
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer"):
            answer = conversation.handle_user_query_flow("U1", "C1", "yep")

        self.assertEqual(answer, "answer")
        self.assertNotIn("C1:U1", conversation.pending_confirmations)

    def test_no_variant_nope_clears_pending(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "clarified_for_user": "Project status",
        }

        answer = conversation.handle_user_query_flow("U1", "C1", "nope")

        self.assertNotIn("C1:U1", conversation.pending_confirmations)
        self.assertIn("Please ask your question again", answer)


    def test_new_question_with_empty_text_still_calls_clarify(self) -> None:
        clarification = {
            "clarified_for_user": "",
            "query_for_search": "",
        }

        with patch.object(
            conversation,
            "clarify_query_with_llm",
            return_value=clarification,
        ) as clarify:
            answer = conversation.handle_user_query_flow("U1", "C1", "")

        clarify.assert_called_once_with("")
        self.assertIn("Reply `yes` to continue", answer)


    def test_get_conversation_key_with_dm_channel_prefix(self) -> None:
        self.assertEqual(
            conversation.get_conversation_key("D123", "U456"),
            "D123:U456",
        )

    def test_get_conversation_key_with_group_channel_prefix(self) -> None:
        self.assertEqual(
            conversation.get_conversation_key("G789", "U456"),
            "G789:U456",
        )
