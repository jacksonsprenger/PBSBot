# retrieval_filter_for_route() with different route_table_ids / filter flag combos
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


    def test_projects_filter_enabled_with_id(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            route_table_ids={"projects": "tblProj"},
        )

        result = retrieval_filter_for_route("projects")

        self.assertEqual(result, {"table_id": "tblProj"})

    def test_projects_filter_enabled_without_id(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            route_table_ids={"projects": ""},
        )

        result = retrieval_filter_for_route("projects")

        self.assertIsNone(result)

    def test_projects_filter_disabled_with_id(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=False,
            route_table_ids={"projects": "tblProj"},
        )

        result = retrieval_filter_for_route("projects")

        self.assertIsNone(result)

    def test_projects_filter_disabled_without_id(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=False,
            route_table_ids={"projects": ""},
        )

        result = retrieval_filter_for_route("projects")

        self.assertIsNone(result)

    def test_projects_missing_from_route_table_ids(self) -> None:
        state.settings = SimpleNamespace(
            chroma_filter_projects_only=True,
            route_table_ids={},
        )

        result = retrieval_filter_for_route("projects")

        self.assertIsNone(result)


    def test_tasks_always_uses_table_name(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"tasks": "tblTasks"},
        )

        result = retrieval_filter_for_route("tasks")

        self.assertEqual(result, {"table_name": "Tasks"})

    def test_contacts_always_uses_table_name(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"contacts": "tblContacts"},
        )

        result = retrieval_filter_for_route("contacts")

        self.assertEqual(result, {"table_name": "Contacts"})

    def test_staff_always_uses_table_name(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"staff": "tblStaff"},
        )

        result = retrieval_filter_for_route("staff")

        self.assertEqual(result, {"table_name": "Staff"})


    def test_unknown_route_returns_none(self) -> None:
        state.settings = SimpleNamespace(
            route_table_ids={"projects": "tblP"},
        )

        self.assertIsNone(retrieval_filter_for_route("unknown"))
        self.assertIsNone(retrieval_filter_for_route(""))
        self.assertIsNone(retrieval_filter_for_route("something_else"))
