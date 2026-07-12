import unittest
import json
from unittest.mock import Mock, patch

import httpx

from app.jira_client import JiraAPIError, JiraClient, extract_status_changes
from app.browser_cookies import BrowserCookieError


class JiraClientTest(unittest.TestCase):
    @patch("app.jira_client.load_chrome_cookies")
    def test_uses_chrome_cookies_when_either_credential_is_missing(
        self, load_cookies: Mock
    ) -> None:
        load_cookies.return_value = {"session": "cookie-value"}
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json={"count": 0})

        with JiraClient(
            "https://example.atlassian.net", email="user@example.com",
            transport=httpx.MockTransport(handler)
        ) as client:
            client.count_issues_by_jql("project = DEV")

        load_cookies.assert_called_once_with("https://example.atlassian.net")
        self.assertEqual(captured_request.headers["cookie"], "session=cookie-value")
        self.assertNotIn("authorization", captured_request.headers)

    @patch("app.jira_client.load_chrome_cookies")
    def test_raises_api_error_when_chrome_cookies_cannot_be_loaded(
        self, load_cookies: Mock
    ) -> None:
        load_cookies.side_effect = BrowserCookieError("cookie load failed")

        with self.assertRaisesRegex(JiraAPIError, "cookie load failed"):
            JiraClient("https://example.atlassian.net")

    def test_logs_request_when_logger_is_provided(self) -> None:
        mock_logger = Mock()
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"issues": []})
        )

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
            logger=mock_logger,
        ) as client:
            client.fetch_issues_by_jql("project = DEV")

        mock_logger.debug.assert_called_once_with(
            "Jira API request: %s %s",
            "POST",
            "rest/api/3/search/jql",
        )

    def test_private_fetch_issue_search_page_posts_expected_payload(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "issues": [
                        {
                            "id": "10001",
                            "key": "DEV-1",
                        }
                    ],
                    "nextPageToken": "next-token",
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            result = client._fetch_issue_search_page(
                "project = DEV ORDER BY updated DESC",
                max_results=10,
                fields=["summary", "status"],
                next_page_token="current-token",
            )

        self.assertEqual(result["issues"][0]["key"], "DEV-1")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "POST")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/rest/api/3/search/jql",
        )
        self.assertEqual(
            json.loads(captured_request.content),
            {
                "jql": "project = DEV ORDER BY updated DESC",
                "maxResults": 10,
                "fields": ["summary", "status"],
                "nextPageToken": "current-token",
            },
        )

    def test_fetch_issues_by_jql_fetches_pages_until_last(self) -> None:
        request_payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            request_payloads.append(payload)
            if "nextPageToken" not in payload:
                return httpx.Response(
                    200,
                    json={
                        "issues": [{"id": "10001", "key": "DEV-1"}],
                        "nextPageToken": "next-token",
                    },
                )

            return httpx.Response(
                200,
                json={
                    "isLast": True,
                    "issues": [{"id": "10002", "key": "DEV-2"}],
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            issues = client.fetch_issues_by_jql(
                "project = DEV",
                fields=["summary"],
            )

        self.assertEqual([issue["key"] for issue in issues], ["DEV-1", "DEV-2"])
        self.assertEqual(
            request_payloads,
            [
                {
                    "jql": "project = DEV",
                    "maxResults": 50,
                    "fields": ["summary"],
                },
                {
                    "jql": "project = DEV",
                    "maxResults": 50,
                    "fields": ["summary"],
                    "nextPageToken": "next-token",
                },
            ],
        )

    def test_fetch_issues_by_jql_stops_at_max_requests(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                200,
                json={
                    "issues": [{"id": str(request_count), "key": f"DEV-{request_count}"}],
                    "nextPageToken": f"token-{request_count}",
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            issues = client.fetch_issues_by_jql(
                "project = DEV",
                max_requests=2,
            )

        self.assertEqual(request_count, 2)
        self.assertEqual([issue["key"] for issue in issues], ["DEV-1", "DEV-2"])

    def test_count_issues_by_jql_returns_count(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json={"count": 153})

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            count = client.count_issues_by_jql("project = DEV")

        self.assertEqual(count, 153)
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "POST")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/rest/api/3/search/approximate-count",
        )
        self.assertEqual(
            json.loads(captured_request.content),
            {"jql": "project = DEV"},
        )

    def test_get_issue_fetches_issue_by_key(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "id": "10001",
                    "key": "DEV-1",
                    "fields": {
                        "summary": "Implement report builder",
                    },
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            issue = client.fetch_issue(
                "DEV-1",
                fields=["summary", "status"],
                expand=["renderedFields"],
            )

        self.assertEqual(issue["key"], "DEV-1")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/rest/api/3/issue/DEV-1?fields=summary%2Cstatus&expand=renderedFields",
        )

    def test_fetch_issue_comments_fetches_pages_until_total(self) -> None:
        requested_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            start_at = request.url.params.get("startAt")
            if start_at == "0":
                return httpx.Response(
                    200,
                    json={
                        "startAt": 0,
                        "maxResults": 1,
                        "total": 2,
                        "comments": [{"id": "10001", "body": "first"}],
                    },
                )

            return httpx.Response(
                200,
                json={
                    "startAt": 1,
                    "maxResults": 1,
                    "total": 2,
                    "comments": [{"id": "10002", "body": "second"}],
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            comments = client.fetch_issue_comments(
                "DEV-123",
                max_results=1,
                order_by="created",
                expand=["renderedBody"],
                max_requests=3,
            )

        self.assertEqual([comment["id"] for comment in comments], ["10001", "10002"])
        self.assertEqual(len(requested_urls), 2)
        self.assertEqual(
            requested_urls[0],
            "https://example.atlassian.net/rest/api/3/issue/DEV-123/comment?startAt=0&maxResults=1&orderBy=created&expand=renderedBody",
        )
        self.assertEqual(
            requested_urls[1],
            "https://example.atlassian.net/rest/api/3/issue/DEV-123/comment?startAt=1&maxResults=1&orderBy=created&expand=renderedBody",
        )

    def test_fetch_issue_changelog_fetches_all_pages(self) -> None:
        requested_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            start_at = request.url.params.get("startAt")
            if start_at == "0":
                return httpx.Response(
                    200,
                    json={
                        "startAt": 0,
                        "maxResults": 1,
                        "total": 2,
                        "values": [{"id": "10001", "items": []}],
                    },
                )

            return httpx.Response(
                200,
                json={
                    "startAt": 1,
                    "maxResults": 1,
                    "total": 2,
                    "isLast": True,
                    "values": [{"id": "10002", "items": []}],
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            changelog = client.fetch_issue_changelog("DEV-123", max_results=1)

        self.assertEqual([entry["id"] for entry in changelog], ["10001", "10002"])
        self.assertEqual(len(requested_urls), 2)
        self.assertEqual(
            requested_urls[0],
            "https://example.atlassian.net/rest/api/3/issue/DEV-123/changelog?startAt=0&maxResults=1",
        )
        self.assertEqual(
            requested_urls[1],
            "https://example.atlassian.net/rest/api/3/issue/DEV-123/changelog?startAt=1&maxResults=1",
        )

    def test_fetch_issue_changelog_stops_at_max_requests(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                200,
                json={
                    "startAt": request_count - 1,
                    "maxResults": 1,
                    "total": 10,
                    "values": [{"id": str(request_count), "items": []}],
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            changelog = client.fetch_issue_changelog(
                "DEV-123",
                max_results=1,
                max_requests=2,
            )

        self.assertEqual(request_count, 2)
        self.assertEqual([entry["id"] for entry in changelog], ["1", "2"])

    def test_fetch_issue_changelog_raises_for_api_error(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(404, text="issue not found")
        )

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            with self.assertRaisesRegex(JiraAPIError, "404 Not Found"):
                client.fetch_issue_changelog("DEV-404")

    def test_update_filter_jql_keeps_existing_name_and_description(self) -> None:
        captured_update: httpx.Request | None = None
        mock_logger = Mock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_update
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "id": "10000",
                        "name": "My Filter",
                        "description": "Existing description",
                        "jql": "project = OLD",
                    },
                )

            captured_update = request
            return httpx.Response(
                200,
                json={
                    "id": "10000",
                    "name": "My Filter",
                    "description": "Existing description",
                    "jql": "project = NEW ORDER BY updated DESC",
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
            logger=mock_logger,
        ) as client:
            updated_filter = client.update_filter_jql(
                "10000",
                "project = NEW ORDER BY updated DESC",
            )

        self.assertEqual(updated_filter["jql"], "project = NEW ORDER BY updated DESC")
        self.assertIsNotNone(captured_update)

        assert captured_update is not None
        self.assertEqual(captured_update.method, "PUT")
        self.assertEqual(
            str(captured_update.url),
            "https://example.atlassian.net/rest/api/3/filter/10000",
        )
        self.assertEqual(
            json.loads(captured_update.content),
            {
                "name": "My Filter",
                "jql": "project = NEW ORDER BY updated DESC",
                "description": "Existing description",
            },
        )
        mock_logger.info.assert_called_once_with(
            "Updated Jira filter JQL: filter_id=%s",
            "10000",
        )

    def test_update_filter_jql_omits_description_when_filter_has_no_description(self) -> None:
        captured_update: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_update
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "id": "10000",
                        "name": "My Filter",
                        "jql": "project = OLD",
                    },
                )

            captured_update = request
            return httpx.Response(
                200,
                json={
                    "id": "10000",
                    "name": "My Filter",
                    "jql": "assignee = currentUser()",
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            client.update_filter_jql(
                10000,
                "assignee = currentUser()",
            )

        self.assertIsNotNone(captured_update)

        assert captured_update is not None
        self.assertEqual(captured_update.method, "PUT")
        self.assertEqual(
            json.loads(captured_update.content),
            {
                "name": "My Filter",
                "jql": "assignee = currentUser()",
            },
        )

    def test_fetch_one_dimensional_filter_statistics_uses_statistics_endpoint(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "filterTitle": "My Filter",
                    "statType": "statuses",
                    "results": [],
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            result = client.fetch_one_dimensional_filter_statistics(
                10000,
                "statuses",
                include_resolved_issues=False,
            )

        self.assertEqual(result["statType"], "statuses")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/rest/gadget/1.0/statistics?filterId=10000&statType=statuses&includeResolvedIssues=false",
        )

    def test_fetch_two_dimensional_filter_statistics_uses_generate_endpoint(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "filterTitle": "My Filter",
                    "xstatType": "statuses",
                    "ystatType": "assignees",
                    "cells": [],
                },
            )

        transport = httpx.MockTransport(handler)

        with JiraClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            result = client.fetch_two_dimensional_filter_statistics(
                "filter-10000",
                x_stat_type="statuses",
                y_stat_type="assignees",
                sort_by="total",
                sort_direction="desc",
                number_to_show=10,
            )

        self.assertEqual(result["xstatType"], "statuses")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/rest/gadget/1.0/twodimensionalfilterstats/generate?filterId=filter-10000&xstattype=statuses&ystattype=assignees&sortBy=total&sortDirection=desc&numberToShow=10",
        )


class ExtractStatusChangesTest(unittest.TestCase):
    def test_extract_status_changes_from_values_response(self) -> None:
        changes = extract_status_changes(
            {
                "values": [
                    {
                        "created": "2026-06-28T09:00:00.000+0900",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "To Do",
                                "toString": "In Progress",
                            },
                            {
                                "field": "assignee",
                                "fromString": "A",
                                "toString": "B",
                            },
                        ],
                    },
                    {
                        "created": "2026-06-28T18:00:00.000+0900",
                        "items": [
                            {
                                "fieldId": "status",
                                "fromString": "In Progress",
                                "toString": "Done",
                            }
                        ],
                    },
                ]
            }
        )

        self.assertEqual(
            changes,
            [
                {
                    "from_status": "To Do",
                    "to_status": "In Progress",
                    "changed_at": "2026-06-28T09:00:00.000+0900",
                },
                {
                    "from_status": "In Progress",
                    "to_status": "Done",
                    "changed_at": "2026-06-28T18:00:00.000+0900",
                },
            ],
        )

    def test_extract_status_changes_accepts_history_list(self) -> None:
        changes = extract_status_changes(
            [
                {
                    "created": "2026-06-28T09:00:00.000+0900",
                    "items": [
                        {
                            "field": "status",
                            "fromString": None,
                            "toString": "To Do",
                        }
                    ],
                }
            ]
        )

        self.assertEqual(
            changes,
            [
                {
                    "from_status": None,
                    "to_status": "To Do",
                    "changed_at": "2026-06-28T09:00:00.000+0900",
                }
            ],
        )

if __name__ == "__main__":
    unittest.main()
