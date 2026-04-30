# retrieval_filter_for_route() with different route_table_ids combos
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from pbsbot import state
from pbsbot.rag.pipeline import retrieval_filter_for_route


class RetrievalFilterComboTests(TestCase):

    def setUp(self) -> None:
        self.original_settings = state.settings

    def tearDown(self) -> None:
        state.settings = self.original_settings

    def test_projects_with_table_id_returns_filter(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"projects": "tblProj"},
        )

        result = retrieval_filter_for_route("projects")

        self.assertEqual(result, {"table_id": "tblProj"})

    def test_projects_without_table_id_returns_none(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"projects": ""},
        )

        result = retrieval_filter_for_route("projects")

        self.assertIsNone(result)

    def test_tasks_with_table_id_returns_filter(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"tasks": "tblTasks"},
        )

        result = retrieval_filter_for_route("tasks")

        self.assertEqual(result, {"table_id": "tblTasks"})

    def test_contacts_with_table_id_returns_filter(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"contacts": "tblContacts"},
        )

        result = retrieval_filter_for_route("contacts")

        self.assertEqual(result, {"table_id": "tblContacts"})

    def test_staff_with_table_id_returns_filter(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"staff": "tblStaff"},
        )

        result = retrieval_filter_for_route("staff")

        self.assertEqual(result, {"table_id": "tblStaff"})

    def test_empty_table_id_returns_none(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"tasks": "", "staff": ""},
        )

        self.assertIsNone(retrieval_filter_for_route("tasks"))
        self.assertIsNone(retrieval_filter_for_route("staff"))

    def test_missing_route_key_returns_none(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={},
        )

        self.assertIsNone(retrieval_filter_for_route("projects"))
        self.assertIsNone(retrieval_filter_for_route("tasks"))

    def test_unknown_route_returns_none(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"projects": "tblP"},
        )

        self.assertIsNone(retrieval_filter_for_route("unknown"))
        self.assertIsNone(retrieval_filter_for_route("something_else"))
