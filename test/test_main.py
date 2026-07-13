from datetime import date
import os
import unittest
from unittest.mock import patch

from app.main import (
    build_daily_report_body,
    build_web_url,
    exclude_immediate_reverse_transitions,
    find_first_status_change,
    require_env,
)


class MainTest(unittest.TestCase):
    def test_find_first_status_change_returns_earliest_matching_transition(self) -> None:
        first = find_first_status_change(
            [
                {
                    "from_status": "In Review",
                    "to_status": "Done",
                    "changed_at": "2026-06-28T18:00:00.000+0900",
                },
                {
                    "from_status": "In Progress",
                    "to_status": "Done",
                    "changed_at": "2026-06-28T09:00:00.000+0900",
                },
                {
                    "from_status": "To Do",
                    "to_status": "In Progress",
                    "changed_at": "2026-06-28T08:00:00.000+0900",
                },
            ],
            "Done",
        )

        self.assertEqual(
            first,
            {
                "from_status": "In Progress",
                "to_status": "Done",
                "changed_at": "2026-06-28T09:00:00.000+0900",
            },
        )

    def test_find_first_status_change_returns_none_without_match(self) -> None:
        self.assertIsNone(find_first_status_change([], "Done"))

    def test_exclude_immediate_reverse_transitions_removes_reverse_pair(self) -> None:
        changes = [
            {
                "from_status": "Open",
                "to_status": "Assign",
                "changed_at": "2026-06-28T09:00:00.000+0900",
            },
            {
                "from_status": "Assign",
                "to_status": "Open",
                "changed_at": "2026-06-28T09:01:00.000+0900",
            },
            {
                "from_status": "Open",
                "to_status": "In Progress",
                "changed_at": "2026-06-28T10:00:00.000+0900",
            },
        ]

        self.assertEqual(
            exclude_immediate_reverse_transitions(changes),
            [changes[2]],
        )

    def test_exclude_immediate_reverse_transitions_keeps_non_reverse_changes(
        self,
    ) -> None:
        changes = [
            {
                "from_status": "Open",
                "to_status": "Assign",
                "changed_at": "2026-06-28T09:00:00.000+0900",
            },
            {
                "from_status": "Assign",
                "to_status": "In Progress",
                "changed_at": "2026-06-28T09:01:00.000+0900",
            },
        ]

        self.assertEqual(exclude_immediate_reverse_transitions(changes), changes)

    def test_exclude_immediate_reverse_transitions_repeats_after_removal(
        self,
    ) -> None:
        changes = [
            {
                "from_status": "Open",
                "to_status": "Assign",
                "changed_at": "2026-06-28T09:00:00.000+0900",
            },
            {
                "from_status": "Assign",
                "to_status": "In Progress",
                "changed_at": "2026-06-28T09:01:00.000+0900",
            },
            {
                "from_status": "In Progress",
                "to_status": "Assign",
                "changed_at": "2026-06-28T09:02:00.000+0900",
            },
            {
                "from_status": "Assign",
                "to_status": "Open",
                "changed_at": "2026-06-28T09:03:00.000+0900",
            },
            {
                "from_status": "Open",
                "to_status": "Done",
                "changed_at": "2026-06-28T10:00:00.000+0900",
            },
        ]

        self.assertEqual(
            exclude_immediate_reverse_transitions(changes),
            [changes[4]],
        )

    def test_build_daily_report_body_escapes_plain_text(self) -> None:
        body = build_daily_report_body(
            report_date=date(2026, 6, 28),
            content="done <review>\nnext",
        )

        self.assertIn("<h1>Daily Report 2026-06-28</h1>", body)
        self.assertIn("done &lt;review&gt;<br />next", body)

    def test_build_daily_report_body_uses_placeholder_for_empty_content(self) -> None:
        body = build_daily_report_body(report_date=date(2026, 6, 28), content="")

        self.assertIn("<em>No report content provided.</em>", body)

    def test_build_web_url_uses_confluence_link_base_when_available(self) -> None:
        url = build_web_url(
            "https://example.atlassian.net",
            {
                "_links": {
                    "base": "https://example.atlassian.net/wiki",
                    "webui": "/spaces/DEV/pages/123/Daily+Report",
                }
            },
        )

        self.assertEqual(
            url,
            "https://example.atlassian.net/wiki/spaces/DEV/pages/123/Daily+Report",
        )

    def test_build_web_url_returns_none_without_webui(self) -> None:
        self.assertIsNone(build_web_url("https://example.atlassian.net", {}))

    def test_require_env_returns_value(self) -> None:
        with patch.dict(os.environ, {"CONFLUENCE_SPACE_ID": "123"}, clear=True):
            self.assertEqual(require_env("CONFLUENCE_SPACE_ID"), "123")

    def test_require_env_raises_for_missing_value(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CONFLUENCE_SPACE_ID"):
                require_env("CONFLUENCE_SPACE_ID")


if __name__ == "__main__":
    unittest.main()
