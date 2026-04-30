# route_query() keyword coverage — make sure each keyword maps to the right table
from __future__ import annotations

from unittest import TestCase

from pbsbot.rag.pipeline import route_query


class RouteQueryExpandedKeywordTests(TestCase):

    # tasks
    def test_due_routes_to_tasks(self) -> None:
        self.assertEqual(route_query("What is due this week?"), "tasks")

    def test_deadline_routes_to_tasks(self) -> None:
        self.assertEqual(route_query("When is the deadline?"), "tasks")

    def test_milestone_routes_to_tasks(self) -> None:
        self.assertEqual(route_query("Show me the milestones"), "tasks")

    def test_due_alone_routes_to_tasks(self) -> None:
        self.assertEqual(route_query("items due tomorrow"), "tasks")


    # contacts
    def test_partner_routes_to_contacts(self) -> None:
        self.assertEqual(route_query("Who is the partner on this?"), "contacts")

    def test_partner_with_other_words_routes_to_contacts(self) -> None:
        self.assertEqual(route_query("Find the partner organization"), "contacts")


    # staff
    def test_role_routes_to_staff(self) -> None:
        self.assertEqual(route_query("What role does John have?"), "staff")

    def test_team_routes_to_staff(self) -> None:
        self.assertEqual(route_query("Who is on the team?"), "staff")

    def test_department_routes_to_staff(self) -> None:
        self.assertEqual(route_query("Which department handles this?"), "staff")

    def test_role_plural_routes_to_staff(self) -> None:
        self.assertEqual(route_query("What are the roles available?"), "staff")

    def test_team_in_sentence_routes_to_staff(self) -> None:
        self.assertEqual(route_query("List all team members"), "staff")


    # priority: tasks > contacts > staff
    def test_task_keyword_beats_staff_keyword(self) -> None:
        self.assertEqual(route_query("task for the team"), "tasks")

    def test_contact_keyword_beats_staff_keyword(self) -> None:
        self.assertEqual(route_query("partner role inquiry"), "contacts")

    def test_deadline_beats_department(self) -> None:
        self.assertEqual(route_query("department deadline"), "tasks")


    # fallback
    def test_no_keyword_match_defaults_to_projects(self) -> None:
        self.assertEqual(route_query("Tell me about the budget"), "projects")
        self.assertEqual(route_query("What is happening next month?"), "projects")
        self.assertEqual(route_query(""), "projects")
