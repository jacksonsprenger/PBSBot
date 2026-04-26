from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from pbsbot import state
from pbsbot.slack import conversation


class ConversationFlowTests(TestCase):
    def setUp(self) -> None:
        self.original_settings = state.settings
        self.original_store = state.chroma_store
        state.settings = SimpleNamespace(max_slack_chars=80)
        state.chroma_store = None
        conversation.pending_confirmations.clear()

    def tearDown(self) -> None:
        state.settings = self.original_settings
        state.chroma_store = self.original_store
        conversation.pending_confirmations.clear()

    def test_normalize_mention_text_removes_all_slack_mentions(self) -> None:
        text = "  <@BOT123>   <@USER456>   What tasks are due?  "

        self.assertEqual(
            conversation.normalize_mention_text(text),
            "What tasks are due?",
        )

    def test_normalize_mention_text_returns_empty_for_only_mentions(self) -> None:
        self.assertEqual(conversation.normalize_mention_text(" <@BOT123> <@U456> "), "")

    def test_get_conversation_key_is_channel_user_scoped(self) -> None:
        self.assertEqual(conversation.get_conversation_key("C123", "U456"), "C123:U456")

    def test_yes_and_no_detection_accepts_expected_variants(self) -> None:
        for text in ("yes", "Y", "yeah", "Yep", "correct"):
            with self.subTest(text=text):
                self.assertTrue(conversation.is_yes(text))

        for text in ("no", "N", "nope", "incorrect"):
            with self.subTest(text=text):
                self.assertTrue(conversation.is_no(text))

        self.assertFalse(conversation.is_yes("maybe"))
        self.assertFalse(conversation.is_no("maybe"))

    def test_truncate_for_slack_uses_settings_cap(self) -> None:
        text = "A" * 120

        out = conversation.truncate_for_slack(text)

        self.assertLessEqual(len(out), 80)
        self.assertTrue(out.endswith("_(Message truncated.)_"))

    def test_truncate_for_slack_leaves_exact_cap_unchanged(self) -> None:
        text = "A" * 80

        self.assertEqual(conversation.truncate_for_slack(text), text)

    def test_truncate_for_slack_honors_explicit_cap(self) -> None:
        text = "B" * 100

        out = conversation.truncate_for_slack(text, max_chars=60)

        self.assertLessEqual(len(out), 60)
        self.assertTrue(out.endswith("_(Message truncated.)_"))

    def test_new_question_stores_pending_confirmation(self) -> None:
        clarification = {
            "clarified_for_user": "You want project status.",
            "query_for_search": "project status",
        }

        with patch.object(
            conversation,
            "clarify_query_with_llm",
            return_value=clarification,
        ) as clarify:
            answer = conversation.handle_user_query_flow("U1", "D1", "status?")

        clarify.assert_called_once_with("status?")
        self.assertIn("Reply `yes` to continue", answer)
        self.assertEqual(
            conversation.pending_confirmations["D1:U1"],
            {
                **clarification,
                "original_user_message": "status?",
            },
        )

    def test_no_reply_clears_pending_confirmation(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "clarified_for_user": "Project status",
        }

        answer = conversation.handle_user_query_flow("U1", "C1", "no")

        self.assertNotIn("C1:U1", conversation.pending_confirmations)
        self.assertIn("Please ask your question again", answer)

    def test_non_yes_no_reply_keeps_pending_confirmation(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "clarified_for_user": "Project status",
        }

        answer = conversation.handle_user_query_flow("U1", "C1", "maybe")

        self.assertIn("C1:U1", conversation.pending_confirmations)
        self.assertEqual(answer, "Please reply with one of: `yes` or `no`.")

    def test_yes_reply_clears_pending_confirmation_after_search(self) -> None:
        conversation.pending_confirmations["C1:U1"] = {
            "query_for_search": "project status",
            "clarified_for_user": "Project status",
            "original_user_message": "What is the project status?",
        }

        with patch.object(conversation, "rag_answer_with_retrieval", return_value="answer"):
            answer = conversation.handle_user_query_flow("U1", "C1", "yes")

        self.assertEqual(answer, "answer")
        self.assertNotIn("C1:U1", conversation.pending_confirmations)
