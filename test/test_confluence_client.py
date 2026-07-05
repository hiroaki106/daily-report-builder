import json
import unittest
from unittest.mock import Mock

import httpx

from app.confluence_client import ConfluenceAPIError, ConfluenceClient


class ConfluenceClientTest(unittest.TestCase):
    def test_logs_request_when_logger_is_provided(self) -> None:
        mock_logger = Mock()
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"accountId": "abc123"})
        )

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
            logger=mock_logger,
        ) as client:
            client.get_current_user()

        mock_logger.debug.assert_called_once_with(
            "Confluence API request: %s %s",
            "GET",
            "wiki/rest/api/user/current",
        )

    def test_create_page_posts_expected_payload(self) -> None:
        captured_request: httpx.Request | None = None
        mock_logger = Mock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "_links": {
                        "base": "https://example.atlassian.net/wiki",
                        "webui": "/spaces/DEV/pages/123/Daily+Report",
                    },
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
            logger=mock_logger,
        ) as client:
            page = client.create_page(
                space_id="SPACE123",
                parent_id="PARENT123",
                title="Daily Report",
                body="<p>done</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/api/v2/pages",
        )
        self.assertEqual(captured_request.method, "POST")
        self.assertEqual(
            json.loads(captured_request.content),
            {
                "spaceId": "SPACE123",
                "status": "current",
                "title": "Daily Report",
                "body": {
                    "representation": "storage",
                    "value": "<p>done</p>",
                },
                "parentId": "PARENT123",
            },
        )
        mock_logger.info.assert_called_once_with(
            "Created Confluence page: page_id=%s title=%s parent_id=%s",
            "123",
            "Daily Report",
            "PARENT123",
        )

    def test_create_page_raises_for_api_error(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(400, text="invalid request")
        )

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            with self.assertRaisesRegex(ConfluenceAPIError, "400 Bad Request"):
                client.create_page(
                    space_id="SPACE123",
                    parent_id="PARENT123",
                    title="Daily Report",
                    body="<p>done</p>",
                )

    def test_get_page_id_by_title_returns_first_matching_page_id(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "123",
                            "title": "Daily Report",
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            page_id = client.get_page_id_by_title(
                "Daily Report",
                space_id="SPACE123",
            )

        self.assertEqual(page_id, "123")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/api/v2/pages?title=Daily+Report&limit=1&space-id=SPACE123",
        )

    def test_get_page_id_by_title_returns_none_when_not_found(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": []})
        )

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            self.assertIsNone(client.get_page_id_by_title("Missing Page"))

    def test_get_page_content_returns_body_value(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "body": {
                        "storage": {
                            "representation": "storage",
                            "value": "<p>Daily report body</p>",
                        }
                    },
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            content = client.get_page_content("123")

        self.assertEqual(content, "<p>Daily report body</p>")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/api/v2/pages/123?body-format=storage",
        )

    def test_get_page_returns_raw_page(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "title": "Daily Report",
                    "version": {"number": 4},
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            page = client.get_page("123", body_format="storage")

        self.assertEqual(page["id"], "123")
        self.assertEqual(page["version"]["number"], 4)
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/api/v2/pages/123?body-format=storage",
        )

    def test_update_page_puts_expected_payload(self) -> None:
        captured_request: httpx.Request | None = None
        mock_logger = Mock()

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "title": "Daily Report",
                    "version": {"number": 5},
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
            logger=mock_logger,
        ) as client:
            page = client.update_page(
                "123",
                title="Daily Report",
                body="<p>updated</p>",
                version_number=5,
                parent_id="PARENT123",
                version_message="Update daily report",
                minor_edit=True,
            )

        self.assertEqual(page["version"]["number"], 5)
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "PUT")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/api/v2/pages/123",
        )
        self.assertEqual(
            json.loads(captured_request.content),
            {
                "id": "123",
                "status": "current",
                "title": "Daily Report",
                "body": {
                    "representation": "storage",
                    "value": "<p>updated</p>",
                },
                "version": {
                    "number": 5,
                    "minorEdit": True,
                    "message": "Update daily report",
                },
                "parentId": "PARENT123",
            },
        )
        mock_logger.info.assert_called_once_with(
            "Updated Confluence page: page_id=%s title=%s version=%s",
            "123",
            "Daily Report",
            5,
        )

    def test_create_or_update_page_updates_existing_page(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET" and request.url.path == "/wiki/api/v2/pages":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": "123",
                                "title": "Daily Report",
                            }
                        ]
                    },
                )

            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "id": "123",
                        "title": "Daily Report",
                        "version": {"number": 4},
                    },
                )

            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "title": "Daily Report",
                    "version": {"number": 5},
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            page = client.create_or_update_page(
                space_id="SPACE123",
                parent_id="PARENT123",
                title="Daily Report",
                body="<p>updated</p>",
                version_message="Refresh report",
            )

        self.assertEqual(page["version"]["number"], 5)
        self.assertEqual([request.method for request in requests], ["GET", "GET", "PUT"])
        self.assertEqual(
            str(requests[0].url),
            "https://example.atlassian.net/wiki/api/v2/pages?title=Daily+Report&limit=1&space-id=SPACE123",
        )
        self.assertEqual(
            str(requests[1].url),
            "https://example.atlassian.net/wiki/api/v2/pages/123?body-format=storage",
        )
        self.assertEqual(
            json.loads(requests[2].content)["version"]["number"],
            5,
        )

    def test_create_or_update_page_creates_when_missing(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json={"results": []})

            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "title": "Daily Report",
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            page = client.create_or_update_page(
                space_id="SPACE123",
                parent_id="PARENT123",
                title="Daily Report",
                body="<p>created</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertEqual([request.method for request in requests], ["GET", "POST"])

    def test_get_or_create_page_returns_existing_page_without_updating(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/wiki/api/v2/pages":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": "123",
                                "title": "Daily Report",
                            }
                        ]
                    },
                )

            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "title": "Daily Report",
                    "version": {"number": 4},
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            page = client.get_or_create_page(
                space_id="SPACE123",
                parent_id="PARENT123",
                title="Daily Report",
                body="<p>ignored for existing page</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertEqual([request.method for request in requests], ["GET", "GET"])
        self.assertEqual(
            str(requests[1].url),
            "https://example.atlassian.net/wiki/api/v2/pages/123?body-format=storage",
        )

    def test_get_or_create_page_creates_when_missing(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json={"results": []})

            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "title": "Daily Report",
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            page = client.get_or_create_page(
                space_id="SPACE123",
                parent_id="PARENT123",
                title="Daily Report",
                body="<p>created</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertEqual([request.method for request in requests], ["GET", "POST"])

    def test_get_current_user_returns_user_information(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "accountId": "abc123",
                    "displayName": "Current User",
                    "email": "user@example.com",
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            user = client.get_current_user()

        self.assertEqual(user["accountId"], "abc123")
        self.assertEqual(user["displayName"], "Current User")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/rest/api/user/current",
        )

    def test_get_space_id_by_key_returns_matching_space_id(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "222",
                            "key": "DEV",
                            "name": "Daily Reports",
                        },
                    ]
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            space_id = client.get_space_id_by_key("DEV")

        self.assertEqual(space_id, "222")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(
            str(captured_request.url),
            "https://example.atlassian.net/wiki/api/v2/spaces?keys=DEV&limit=1",
        )

    def test_get_space_id_by_key_returns_none_when_not_found(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"results": []},
            )
        )

        with ConfluenceClient(
            base_url="https://example.atlassian.net",
            email="user@example.com",
            api_token="token",
            transport=transport,
        ) as client:
            self.assertIsNone(client.get_space_id_by_key("DEV"))


if __name__ == "__main__":
    unittest.main()
