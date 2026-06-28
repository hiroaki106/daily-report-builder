import json
import unittest

import httpx

from app.confluence_client import ConfluenceAPIError, ConfluenceClient


class ConfluenceClientTest(unittest.TestCase):
    def test_create_page_posts_expected_payload(self) -> None:
        captured_request: httpx.Request | None = None

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
