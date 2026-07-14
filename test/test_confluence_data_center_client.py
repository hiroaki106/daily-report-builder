import json
import unittest
from unittest.mock import Mock, patch

import httpx

from app.utils.confluence_data_center_client import (
    ConfluenceDataCenterAPIError,
    ConfluenceDataCenterClient,
)
from app.utils.browser_cookies import BrowserCookieError


class ConfluenceDataCenterClientTest(unittest.TestCase):
    @patch("app.utils.confluence_data_center_client.load_chrome_cookies")
    def test_uses_chrome_cookies_when_either_credential_is_missing(
        self, load_cookies: Mock
    ) -> None:
        load_cookies.return_value = {"session": "cookie-value"}
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json={"username": "admin"})

        with ConfluenceDataCenterClient(
            "https://confluence.example.com/confluence", username="admin",
            transport=httpx.MockTransport(handler)
        ) as client:
            client.fetch_current_user()

        load_cookies.assert_called_once_with(
            "https://confluence.example.com/confluence"
        )
        self.assertEqual(captured_request.headers["cookie"], "session=cookie-value")
        self.assertNotIn("authorization", captured_request.headers)

    @patch("app.utils.confluence_data_center_client.load_chrome_cookies")
    def test_raises_api_error_when_chrome_cookies_cannot_be_loaded(
        self, load_cookies: Mock
    ) -> None:
        load_cookies.side_effect = BrowserCookieError("cookie load failed")

        with self.assertRaisesRegex(
            ConfluenceDataCenterAPIError, "cookie load failed"
        ):
            ConfluenceDataCenterClient("https://confluence.example.com/confluence")

    def test_logs_request_when_logger_is_provided(self) -> None:
        mock_logger = Mock()
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"username": "admin"})
        )

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
            logger=mock_logger,
        ) as client:
            client.fetch_current_user()

        mock_logger.debug.assert_called_once_with(
            "Confluence Data Center API request: %s %s",
            "GET",
            "rest/api/user/current",
        )

    def test_fetch_current_user_returns_user_information(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "username": "admin",
                    "displayName": "Administrator",
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            user = client.fetch_current_user()

        self.assertEqual(user["username"], "admin")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/user/current",
        )

    def test_fetch_space_id_by_key_returns_space_id(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "id": 4030468,
                    "key": "DEV",
                    "name": "Daily Reports",
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            space_id = client.fetch_space_id_by_key("DEV")

        self.assertEqual(space_id, "4030468")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/space/DEV",
        )

    def test_fetch_page_id_by_title_returns_first_matching_page_id(self) -> None:
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

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            page_id = client.fetch_page_id_by_title(
                "Daily Report",
                space_key="DEV",
            )

        self.assertEqual(page_id, "123")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/content?title=Daily+Report&type=page&limit=1&spaceKey=DEV",
        )

    def test_fetch_page_id_by_title_returns_none_when_not_found(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": []})
        )

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            self.assertIsNone(client.fetch_page_id_by_title("Missing Page"))

    def test_fetch_page_returns_raw_page(self) -> None:
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

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            page = client.fetch_page("123", body_format="storage")

        self.assertEqual(page["id"], "123")
        self.assertEqual(page["version"]["number"], 4)
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/content/123?expand=body.storage%2Cversion%2Cspace",
        )

    def test_fetch_page_content_returns_body_value(self) -> None:
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

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            content = client.fetch_page_content("123")

        self.assertEqual(content, "<p>Daily report body</p>")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "GET")
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/content/123?expand=body.storage%2Cversion%2Cspace",
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
                        "base": "https://confluence.example.com/confluence",
                        "webui": "/display/DEV/Daily+Report",
                    },
                },
            )

        transport = httpx.MockTransport(handler)

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
            logger=mock_logger,
        ) as client:
            page = client.create_page(
                space_key="DEV",
                parent_id=456,
                title="Daily Report",
                body="<p>done</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/content",
        )
        self.assertEqual(captured_request.method, "POST")
        self.assertEqual(
            json.loads(captured_request.content),
            {
                "type": "page",
                "title": "Daily Report",
                "space": {"key": "DEV"},
                "ancestors": [{"id": "456"}],
                "body": {
                    "storage": {
                        "representation": "storage",
                        "value": "<p>done</p>",
                    }
                },
            },
        )
        mock_logger.info.assert_called_once_with(
            "Created Confluence Data Center page: page_id=%s title=%s parent_id=%s",
            "123",
            "Daily Report",
            456,
        )

    def test_create_page_raises_for_api_error(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(400, text="invalid request")
        )

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            with self.assertRaisesRegex(
                ConfluenceDataCenterAPIError,
                "400 Bad Request",
            ):
                client.create_page(
                    space_key="DEV",
                    parent_id="456",
                    title="Daily Report",
                    body="<p>done</p>",
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

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
            logger=mock_logger,
        ) as client:
            page = client.update_page(
                "123",
                space_key="DEV",
                title="Daily Report",
                body="<p>updated</p>",
                version_number=5,
                parent_id="456",
                version_message="Update daily report",
                minor_edit=True,
            )

        self.assertEqual(page["version"]["number"], 5)
        self.assertIsNotNone(captured_request)

        assert captured_request is not None
        self.assertEqual(captured_request.method, "PUT")
        self.assertEqual(
            str(captured_request.url),
            "https://confluence.example.com/confluence/rest/api/content/123",
        )
        self.assertEqual(
            json.loads(captured_request.content),
            {
                "id": "123",
                "type": "page",
                "status": "current",
                "title": "Daily Report",
                "space": {"key": "DEV"},
                "body": {
                    "storage": {
                        "representation": "storage",
                        "value": "<p>updated</p>",
                    }
                },
                "version": {
                    "number": 5,
                    "minorEdit": True,
                    "message": "Update daily report",
                },
                "ancestors": [{"id": "456"}],
            },
        )
        mock_logger.info.assert_called_once_with(
            "Updated Confluence Data Center page: page_id=%s title=%s version=%s",
            "123",
            "Daily Report",
            5,
        )

    def test_ensure_page_returns_existing_page_without_updating(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/rest/api/content"):
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

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            page = client.ensure_page(
                space_key="DEV",
                parent_id=456,
                title="Daily Report",
                body="<p>ignored for existing page</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertEqual([request.method for request in requests], ["GET", "GET"])
        self.assertEqual(
            str(requests[1].url),
            "https://confluence.example.com/confluence/rest/api/content/123?expand=body.storage%2Cversion%2Cspace",
        )

    def test_ensure_page_creates_when_missing(self) -> None:
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

        with ConfluenceDataCenterClient(
            base_url="https://confluence.example.com/confluence",
            username="admin",
            password="password",
            transport=transport,
        ) as client:
            page = client.ensure_page(
                space_key="DEV",
                parent_id=456,
                title="Daily Report",
                body="<p>created</p>",
            )

        self.assertEqual(page["id"], "123")
        self.assertEqual([request.method for request in requests], ["GET", "POST"])
        self.assertEqual(
            json.loads(requests[1].content)["ancestors"], [{"id": "456"}]
        )


if __name__ == "__main__":
    unittest.main()
