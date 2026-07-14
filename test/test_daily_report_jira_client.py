import json
import unittest
from unittest.mock import patch

import httpx

from app.daily_report_jira_client import (
    DailyReportJiraClient,
    JiraRequestCancelledError,
)


class DailyReportJiraClientTest(unittest.TestCase):
    def test_search_all_issues_by_jql_derives_request_limit_from_count(self) -> None:
        search_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search/approximate-count"):
                return httpx.Response(200, json={"count": 101})

            payload = json.loads(request.content)
            search_payloads.append(payload)
            page_number = len(search_payloads)
            return httpx.Response(
                200,
                json={
                    "issues": [{"id": str(page_number), "key": f"DEV-{page_number}"}],
                    "nextPageToken": f"token-{page_number}",
                },
            )

        with DailyReportJiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=httpx.MockTransport(handler),
        ) as client:
            issues = client.search_all_issues_by_jql(
                "project = DEV",
                fields=["summary"],
                max_results=50,
            )

        self.assertEqual([issue["key"] for issue in issues], ["DEV-1", "DEV-2", "DEV-3"])
        self.assertEqual(len(search_payloads), 3)
        self.assertTrue(
            all(payload["maxResults"] == 50 for payload in search_payloads)
        )
        self.assertTrue(all(payload["fields"] == ["summary"] for payload in search_payloads))

    def test_search_all_issues_by_jql_skips_search_when_count_is_zero(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"count": 0})

        with DailyReportJiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=httpx.MockTransport(handler),
        ) as client:
            issues = client.search_all_issues_by_jql("project = DEV")

        self.assertEqual(issues, [])
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0].url.path.endswith("/search/approximate-count"))

    def test_search_all_issues_by_jql_rejects_non_positive_page_size(self) -> None:
        with DailyReportJiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
        ) as client:
            with self.assertRaisesRegex(ValueError, "max_results"):
                client.search_all_issues_by_jql("project = DEV", max_results=0)

    @patch("builtins.input", return_value="yes")
    def test_search_all_issues_by_jql_confirms_large_request_sequence(
        self, mock_input: object
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/search/approximate-count"):
                return httpx.Response(200, json={"count": 1050})
            return httpx.Response(200, json={"issues": [], "isLast": True})

        with DailyReportJiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=httpx.MockTransport(handler),
        ) as client:
            client.search_all_issues_by_jql("project = DEV")

        mock_input.assert_called_once_with(  # type: ignore[attr-defined]
            "This Jira search may send up to 21 requests. Continue? [y/N]: "
        )
        self.assertEqual(len(requests), 2)

    @patch("builtins.input", return_value="n")
    def test_search_all_issues_by_jql_cancels_when_confirmation_is_declined(
        self, mock_input: object
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"count": 1050})

        with DailyReportJiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaisesRegex(JiraRequestCancelledError, "cancelled"):
                client.search_all_issues_by_jql("project = DEV")

        mock_input.assert_called_once()  # type: ignore[attr-defined]
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
