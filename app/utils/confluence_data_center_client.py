"""Client helpers for Confluence Data Center REST API endpoints."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from app.utils.browser_cookies import BrowserCookieError, load_chrome_cookies


_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.NullHandler())


class ConfluenceDataCenterAPIError(RuntimeError):
    """Raised when Confluence Data Center returns an unsuccessful response."""


class ConfluenceDataCenterClient:
    """Synchronous client for Confluence Data Center APIs used by this app."""

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize an authenticated Confluence Data Center API client.

        Args:
            base_url: Confluence base URL, such as
                ``https://confluence.example.com`` or
                ``https://example.com/confluence``.
            username: Confluence username used for basic authentication.
            password: Confluence password or API token used for basic authentication.
                If either credential is missing, Chrome cookies are used instead.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport, mainly used by tests.
            logger: Optional logger. Defaults to this module's logger.
        """
        self._base_url = base_url.rstrip("/") + "/"
        self._logger = logger or _LOGGER
        auth: tuple[str, str] | None = None
        cookies = None
        if username is not None and password is not None:
            auth = (username, password)
        else:
            try:
                cookies = load_chrome_cookies(base_url)
            except BrowserCookieError as exc:
                raise ConfluenceDataCenterAPIError(str(exc)) from exc

        self._client = httpx.Client(
            auth=auth,
            cookies=cookies,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "ConfluenceDataCenterClient":
        """Return this client for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client when leaving a context manager block."""
        self.close()

    def fetch_current_user(self) -> dict[str, Any]:
        """Fetch the currently authenticated Confluence user.

        Returns:
            Raw Confluence user response.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/

        Permissions:
            Requires permission to access the Confluence site. Data Center REST
            endpoints use the permissions of the authenticated user.
        """
        return self._request("GET", "rest/api/user/current")

    def fetch_space_id_by_key(self, key: str) -> str | None:
        """Fetch a Confluence space ID by space key.

        Args:
            key: Confluence space key, such as ``DEV``.

        Returns:
            Space ID when the key exists in the response, otherwise ``None``.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/

        Permissions:
            Requires permission to view the space. Data Center REST endpoints
            use the permissions of the authenticated user.
        """
        response = self._request("GET", f"rest/api/space/{quote(key, safe='')}")
        space_id = response.get("id")
        if isinstance(space_id, str):
            return space_id
        if isinstance(space_id, int):
            return str(space_id)

        return None

    def fetch_page_id_by_title(
        self,
        title: str,
        *,
        space_key: str | None = None,
    ) -> str | None:
        """Fetch the first Confluence page ID matching a title.

        Args:
            title: Page title to search for.
            space_key: Optional Confluence space key used to narrow the search.

        Returns:
            Page ID for the first matching page, otherwise ``None``.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/#find-a-page-by-title-and-space-key

        Permissions:
            Requires permission to view the matching page. Data Center REST
            endpoints use the permissions of the authenticated user.
        """
        params: dict[str, str | int] = {
            "title": title,
            "type": "page",
            "limit": 1,
        }
        if space_key is not None:
            params["spaceKey"] = space_key

        response = self._request("GET", "rest/api/content", params=params)
        results = response.get("results", [])
        if not isinstance(results, list):
            raise ConfluenceDataCenterAPIError(
                "Confluence content response did not include a results list"
            )

        for page in results:
            if isinstance(page, dict):
                page_id = page.get("id")
                if isinstance(page_id, str):
                    return page_id
                if isinstance(page_id, int):
                    return str(page_id)

        return None

    def fetch_page(
        self,
        page_id: str | int,
        *,
        body_format: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a Confluence page by content ID.

        Args:
            page_id: Confluence content ID.
            body_format: Optional body representation to expand, such as
                ``storage`` or ``view``.

        Returns:
            Raw Confluence content response.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/

        Permissions:
            Requires permission to view the page. Data Center REST endpoints use
            the permissions of the authenticated user.
        """
        params: dict[str, str] | None = None
        if body_format is not None:
            params = {"expand": f"body.{body_format},version,space"}

        return self._request(
            "GET",
            f"rest/api/content/{quote(str(page_id), safe='')}",
            params=params,
        )

    def fetch_page_content(
        self, page_id: str | int, *, body_format: str = "storage"
    ) -> str | None:
        """Fetch a Confluence page body value in the requested body format.

        Args:
            page_id: Confluence content ID.
            body_format: Body representation requested from Confluence,
                such as ``storage`` or ``view``.

        Returns:
            Body value in the requested format, otherwise ``None`` when the
            response does not include that body format.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/

        Permissions:
            Requires permission to view the page. Data Center REST endpoints use
            the permissions of the authenticated user.
        """
        response = self.fetch_page(page_id, body_format=body_format)
        body = response.get("body")
        if not isinstance(body, dict):
            return None

        formatted_body = body.get(body_format)
        if not isinstance(formatted_body, dict):
            return None

        value = formatted_body.get("value")
        if not isinstance(value, str):
            return None

        return value

    def create_page(
        self,
        *,
        space_key: str,
        parent_id: str | int,
        title: str,
        body: str,
        status: str = "current",
        representation: str = "storage",
    ) -> dict[str, Any]:
        """Create a Confluence page under a required parent page.

        Args:
            space_key: Confluence space key where the page is created.
            parent_id: Parent page content ID.
            title: New page title.
            body: Page body value.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.

        Returns:
            Raw Confluence content creation response.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/#create-a-new-page-as-a-child-of-another-page

        Permissions:
            Requires permission to create pages in the target space and view the
            parent page. Data Center REST endpoints use the permissions of the
            authenticated user.
        """
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": str(parent_id)}],
            "body": {
                representation: {
                    "representation": representation,
                    "value": body,
                }
            },
        }
        if status != "current":
            payload["status"] = status

        page = self._request("POST", "rest/api/content", json=payload)
        self._logger.info(
            "Created Confluence Data Center page: page_id=%s title=%s parent_id=%s",
            page.get("id"),
            title,
            parent_id,
        )
        return page

    def update_page(
        self,
        page_id: str | int,
        *,
        space_key: str,
        title: str,
        body: str,
        version_number: int,
        status: str = "current",
        representation: str = "storage",
        parent_id: str | None = None,
        version_message: str | None = None,
        minor_edit: bool = False,
    ) -> dict[str, Any]:
        """Update a Confluence page.

        Args:
            page_id: Confluence content ID.
            space_key: Confluence space key containing the page.
            title: Page title.
            body: Replacement page body value.
            version_number: New Confluence page version number.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.
            parent_id: Optional parent page content ID.
            version_message: Optional version message.
            minor_edit: Whether the update is a minor edit.

        Returns:
            Raw Confluence content update response.

        Reference:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/#update-a-page

        Permissions:
            Requires permission to edit the page. Data Center REST endpoints use
            the permissions of the authenticated user.
        """
        version: dict[str, Any] = {
            "number": version_number,
            "minorEdit": minor_edit,
        }
        if version_message is not None:
            version["message"] = version_message

        payload: dict[str, Any] = {
            "id": str(page_id),
            "type": "page",
            "status": status,
            "title": title,
            "space": {"key": space_key},
            "body": {
                representation: {
                    "representation": representation,
                    "value": body,
                }
            },
            "version": version,
        }
        if parent_id is not None:
            payload["ancestors"] = [{"id": str(parent_id)}]

        page = self._request(
            "PUT",
            f"rest/api/content/{quote(str(page_id), safe='')}",
            json=payload,
        )
        self._logger.info(
            "Updated Confluence Data Center page: page_id=%s title=%s version=%s",
            page_id,
            title,
            version_number,
        )
        return page

    def ensure_page(
        self,
        *,
        space_key: str,
        parent_id: str | int,
        title: str,
        body: str,
        status: str = "current",
        representation: str = "storage",
    ) -> dict[str, Any]:
        """Return an existing page by title, or create it when missing.

        Args:
            space_key: Confluence space key where the page is created or searched.
            parent_id: Parent page content ID used when the page must be created.
            title: Page title used to find or create the page.
            body: Page body value used only when the page must be created.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.

        Returns:
            Existing raw Confluence page response, or the created page response.

        Reference:
            Uses the Data Center content find, get, and create endpoints:
            https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/

        Permissions:
            Requires permission to view or create the relevant pages. Data Center
            REST endpoints use the permissions of the authenticated user.
        """
        page_id = self.fetch_page_id_by_title(title, space_key=space_key)
        if page_id is not None:
            return self.fetch_page(page_id, body_format=representation)

        return self.create_page(
            space_key=space_key,
            parent_id=parent_id,
            title=title,
            body=body,
            status=status,
            representation=representation,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send an HTTP request and raise ConfluenceDataCenterAPIError on failure."""
        url = urljoin(self._base_url, path)
        self._logger.debug("Confluence Data Center API request: %s %s", method, path)
        response = self._client.request(method, url, **kwargs)
        if response.is_success:
            return response.json()

        detail = response.text[:500]
        self._logger.error(
            "Confluence Data Center API request failed: %s %s returned %s %s",
            method,
            path,
            response.status_code,
            response.reason_phrase,
        )
        raise ConfluenceDataCenterAPIError(
            f"Confluence Data Center API request failed: {response.status_code} "
            f"{response.reason_phrase}: {detail}"
        )
