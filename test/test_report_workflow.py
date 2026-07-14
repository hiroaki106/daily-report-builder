from datetime import datetime
import sys
import unittest
from unittest.mock import Mock, patch

from app.report_workflow import (
    aggregate_slo,
    build_report_body,
    confirm_dashboard_matches_sheet,
    parse_date_range,
    update_target_jira_filters,
)
from app.utils.jira_client import JiraAPIError


class ReportWorkflowTest(unittest.TestCase):
    def test_parse_date_range_returns_datetime_arguments(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "main.py",
                "--start-date",
                "2026/07/01 09:00",
                "--end-date",
                "2026/07/01 18:00",
            ],
        ):
            start_date, end_date = parse_date_range()

        self.assertEqual(
            start_date, datetime(2026, 7, 1, 9, 0)
        )
        self.assertEqual(
            end_date, datetime(2026, 7, 1, 18, 0)
        )

    @patch("builtins.input", side_effect=["2026/07/01 09:00", "2026/07/01 18:00"])
    def test_parse_date_range_prompts_for_missing_arguments(
        self, mock_input: Mock
    ) -> None:
        with patch.object(sys, "argv", ["main.py"]):
            start_date, end_date = parse_date_range()

        self.assertEqual(start_date, datetime(2026, 7, 1, 9))
        self.assertEqual(end_date, datetime(2026, 7, 1, 18))
        self.assertEqual(mock_input.call_count, 2)

    @patch(
        "builtins.input",
        side_effect=[
            "invalid",
            "2026/07/01 18:00",
            "2026/07/02 09:00",
            "2026/07/01 18:00",
            "2026/07/01 09:00",
            "2026/07/01 18:00",
        ],
    )
    @patch("builtins.print")
    def test_parse_date_range_reprompts_for_invalid_format_and_order(
        self,
        mock_print: Mock,
        mock_input: Mock,
    ) -> None:
        with patch.object(sys, "argv", ["main.py"]):
            start_date, end_date = parse_date_range()

        self.assertEqual(start_date, datetime(2026, 7, 1, 9))
        self.assertEqual(end_date, datetime(2026, 7, 1, 18))
        self.assertEqual(mock_input.call_count, 6)
        self.assertEqual(mock_print.call_count, 2)

    @patch("builtins.input", side_effect=["no", "n", "yes"])
    def test_confirm_dashboard_matches_sheet_repeats_until_yes(
        self, mock_input: Mock
    ) -> None:
        confirm_dashboard_matches_sheet()

        self.assertEqual(mock_input.call_count, 3)

    def test_update_target_jira_filters_skips_empty_filter_list(self) -> None:
        logger = Mock()
        start_date = datetime(2026, 7, 1, 9)
        end_date = datetime(2026, 7, 1, 18)

        with patch("app.report_workflow.config.TARGET_JIRA_FILTER_IDS", []):
            update_target_jira_filters(start_date, end_date, logger)

        logger.info.assert_called_once_with("No target Jira filters configured")

    @patch("app.report_workflow.config.JIRA_API_TOKEN", "token")
    @patch("app.report_workflow.config.JIRA_EMAIL", "user@example.com")
    @patch("app.report_workflow.config.JIRA_BASE_URL", "https://example.atlassian.net")
    @patch("app.report_workflow.config.TARGET_JIRA_FILTER_IDS", [100, 200])
    @patch("app.report_workflow.rewrite_filter_jql")
    @patch("app.report_workflow.JiraClient")
    def test_update_target_jira_filters_fetches_rewrites_and_updates_jql(
        self,
        jira_client_class: Mock,
        rewrite_jql: Mock,
    ) -> None:
        logger = Mock()
        client = jira_client_class.return_value.__enter__.return_value
        client.fetch_filter.side_effect = [
            {"id": "100", "jql": "project = DEV"},
            {"id": "200", "jql": "project = OPS"},
        ]
        rewrite_jql.side_effect = [
            'project = DEV AND updated >= "2026-07-01"',
            'project = OPS AND updated >= "2026-07-01"',
        ]
        start_date = datetime(2026, 7, 1, 9)
        end_date = datetime(2026, 7, 1, 18)

        update_target_jira_filters(start_date, end_date, logger)

        jira_client_class.assert_called_once_with(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            logger=logger,
        )
        self.assertEqual(client.fetch_filter.call_count, 2)
        self.assertEqual(rewrite_jql.call_count, 2)
        client.update_filter_jql.assert_any_call(
            100, 'project = DEV AND updated >= "2026-07-01"'
        )
        client.update_filter_jql.assert_any_call(
            200, 'project = OPS AND updated >= "2026-07-01"'
        )

    @patch("app.report_workflow.config.JIRA_BASE_URL", "https://example.atlassian.net")
    @patch("app.report_workflow.config.TARGET_JIRA_FILTER_IDS", [100])
    @patch("app.report_workflow.JiraClient")
    def test_update_target_jira_filters_rejects_missing_jql(
        self, jira_client_class: Mock
    ) -> None:
        client = jira_client_class.return_value.__enter__.return_value
        client.fetch_filter.return_value = {"id": "100"}

        with self.assertRaisesRegex(JiraAPIError, "100"):
            update_target_jira_filters(
                datetime(2026, 7, 1, 9),
                datetime(2026, 7, 1, 18),
                Mock(),
            )

    @patch("app.report_workflow.create_report_storage", return_value="<p>report</p>")
    def test_placeholder_operations_return_empty_slo_results(
        self, create_storage: Mock
    ) -> None:
        start_date = datetime(2026, 7, 1, 9)
        end_date = datetime(2026, 7, 1, 18)

        slo_results = aggregate_slo(start_date, end_date)

        self.assertEqual(slo_results, [])
        self.assertEqual(
            build_report_body(start_date, end_date, slo_results), "<p>report</p>"
        )
        create_storage.assert_called_once_with(start_date, end_date, slo_results)


if __name__ == "__main__":
    unittest.main()
