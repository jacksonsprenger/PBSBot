# route_table_ids loading from AIRTABLE_*_TABLE_ID env vars
from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from pbsbot import config


class RouteTableIdsEnvTests(TestCase):

    def test_all_table_ids_empty_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids["projects"], "")
        self.assertEqual(settings.route_table_ids["tasks"], "")
        self.assertEqual(settings.route_table_ids["staff"], "")
        self.assertEqual(settings.route_table_ids["contacts"], "")

    def test_only_projects_table_id_set(self) -> None:
        with patch.dict(os.environ, {"AIRTABLE_PROJECTS_TABLE_ID": "tblProj"}, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids["projects"], "tblProj")
        self.assertEqual(settings.route_table_ids["tasks"], "")
        self.assertEqual(settings.route_table_ids["staff"], "")
        self.assertEqual(settings.route_table_ids["contacts"], "")

    def test_only_tasks_table_id_set(self) -> None:
        with patch.dict(os.environ, {"AIRTABLE_TASKS_TABLE_ID": "tblTasks"}, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids["tasks"], "tblTasks")
        self.assertEqual(settings.route_table_ids["projects"], "")

    def test_only_staff_table_id_set(self) -> None:
        with patch.dict(os.environ, {"AIRTABLE_STAFF_TABLE_ID": "tblStaff"}, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids["staff"], "tblStaff")

    def test_only_contacts_table_id_set(self) -> None:
        with patch.dict(os.environ, {"AIRTABLE_CONTACTS_TABLE_ID": "tblContacts"}, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids["contacts"], "tblContacts")

    def test_all_table_ids_set(self) -> None:
        env = {
            "AIRTABLE_PROJECTS_TABLE_ID": "tblP",
            "AIRTABLE_TASKS_TABLE_ID": "tblT",
            "AIRTABLE_STAFF_TABLE_ID": "tblS",
            "AIRTABLE_CONTACTS_TABLE_ID": "tblC",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids, {
            "projects": "tblP",
            "tasks": "tblT",
            "staff": "tblS",
            "contacts": "tblC",
        })

    def test_table_ids_are_stripped_of_whitespace(self) -> None:
        env = {
            "AIRTABLE_PROJECTS_TABLE_ID": "  tblP  ",
            "AIRTABLE_TASKS_TABLE_ID": "\ttblT\n",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = config.load_settings()

        self.assertEqual(settings.route_table_ids["projects"], "tblP")
        self.assertEqual(settings.route_table_ids["tasks"], "tblT")

    def test_filter_default_is_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = config.load_settings()

        self.assertFalse(settings.chroma_filter_projects_only)

    def test_filter_can_be_enabled_with_true(self) -> None:
        with patch.dict(os.environ, {"CHROMA_FILTER_TO_PROJECTS_TABLE": "true"}, clear=True):
            settings = config.load_settings()

        self.assertTrue(settings.chroma_filter_projects_only)
