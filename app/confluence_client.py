"""Client helpers for Confluence Cloud API endpoints."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urljoin

import httpx


_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.NullHandler())


class ConfluenceAPIError(RuntimeError):
    """Raised when Confluence returns an unsuccessful response."""


class ConfluenceClient:
    """Synchronous client for the Confluence Cloud APIs used by this application."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize an authenticated Confluence API client.

        Args:
            base_url: Atlassian site URL, such as ``https://example.atlassian.net``.
            email: Atlassian account email used for basic authentication.
            api_token: Atlassian API token used for basic authentication.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport, mainly used by tests.
            logger: Optional logger. Defaults to this module's logger.
        """
        self._base_url = base_url.rstrip("/") + "/"
        self._logger = logger or _LOGGER
        self._client = httpx.Client(
            auth=(email, api_token),
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

    def __enter__(self) -> "ConfluenceClient":
        """Return this client for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client when leaving a context manager block."""
        self.close()

    def get_current_user(self) -> dict[str, Any]:
        """Fetch the currently authenticated Confluence user.

        Returns:
            Raw Confluence user response. The ``accountId`` value can be used
            for Confluence user mentions in storage-format page content.
        """
        return self._request("GET", "wiki/rest/api/user/current")

    def get_space_id_by_key(self, key: str) -> str | None:
        """Fetch a Confluence space ID by space key.

        Args:
            key: Confluence space key, such as ``DEV``.

        Returns:
            Space ID when the key exists, otherwise ``None``.
        """
        response = self._request(
            "GET",
            "wiki/api/v2/spaces",
            params={"keys": key, "limit": 1},
        )
        results = response.get("results", [])
        if not isinstance(results, list):
            raise ConfluenceAPIError(
                "Confluence spaces response did not include a results list"
            )

        for space in results:
            if isinstance(space, dict):
                space_id = space.get("id")
                if isinstance(space_id, str):
                    return space_id

        return None

    def get_page_id_by_title(
        self,
        title: str,
        *,
        space_id: str | None = None,
    ) -> str | None:
        """Fetch the first Confluence page ID matching a title.

        Args:
            title: Page title to search for.
            space_id: Optional Confluence space ID used to narrow the search.

        Returns:
            Page ID for the first matching page, otherwise ``None``.
        """
        params: dict[str, str | int] = {
            "title": title,
            "limit": 1,
        }
        if space_id is not None:
            params["space-id"] = space_id

        response = self._request("GET", "wiki/api/v2/pages", params=params)
        results = response.get("results", [])
        if not isinstance(results, list):
            raise ConfluenceAPIError(
                "Confluence pages response did not include a results list"
            )

        for page in results:
            if isinstance(page, dict):
                page_id = page.get("id")
                if isinstance(page_id, str):
                    return page_id

        return None

    def get_page(
        self,
        page_id: str | int,
        *,
        body_format: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a Confluence page by ID.

        Args:
            page_id: Confluence page ID.
            body_format: Optional body representation requested from Confluence,
                such as ``storage`` or ``atlas_doc_format``.

        Returns:
            Raw Confluence page response.
        """
        params: dict[str, str] | None = None
        if body_format is not None:
            params = {"body-format": body_format}

        return self._request(
            "GET",
            f"wiki/api/v2/pages/{quote(str(page_id), safe='')}",
            params=params,
        )

    def get_page_content(
        self, page_id: str | int, *, body_format: str = "storage"
    ) -> str | None:
        """Fetch a Confluence page body value in the requested body format.

        Args:
            page_id: Confluence page ID.
            body_format: Body representation requested from Confluence,
                such as ``storage`` or ``atlas_doc_format``.

        Returns:
            Body value in the requested format, otherwise ``None`` when the
            response does not include that body format.
        """
        response = self.get_page(page_id, body_format=body_format)
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
        space_id: str,
        parent_id: str,
        title: str,
        body: str,
        status: str = "current",
        representation: str = "storage",
    ) -> dict[str, Any]:
        """Create a Confluence page under a required parent page.

        Args:
            space_id: Confluence space ID where the page is created.
            parent_id: Parent page ID. This application always creates pages
                under an existing parent page.
            title: New page title.
            body: Page body value.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.

        Returns:
            Raw Confluence page creation response.
        """
        payload: dict[str, Any] = {
            "spaceId": space_id,
            "status": status,
            "title": title,
            "body": {
                "representation": representation,
                "value": body,
            },
            "parentId": parent_id,
        }

        page = self._request("POST", "wiki/api/v2/pages", json=payload)
        self._logger.info(
            "Created Confluence page: page_id=%s title=%s parent_id=%s",
            page.get("id"),
            title,
            parent_id,
        )
        return page

    def update_page(
        self,
        page_id: str | int,
        *,
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
            page_id: Confluence page ID.
            title: Page title.
            body: Replacement page body value.
            version_number: New Confluence page version number.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.
            parent_id: Optional parent page ID. When provided, the page is kept
                under or moved to that parent.
            version_message: Optional version message.
            minor_edit: Whether the update is a minor edit.

        Returns:
            Raw Confluence page update response.
        """
        version: dict[str, Any] = {
            "number": version_number,
            "minorEdit": minor_edit,
        }
        if version_message is not None:
            version["message"] = version_message

        payload: dict[str, Any] = {
            "id": str(page_id),
            "status": status,
            "title": title,
            "body": {
                "representation": representation,
                "value": body,
            },
            "version": version,
        }
        if parent_id is not None:
            payload["parentId"] = parent_id

        page = self._request(
            "PUT",
            f"wiki/api/v2/pages/{quote(str(page_id), safe='')}",
            json=payload,
        )
        self._logger.info(
            "Updated Confluence page: page_id=%s title=%s version=%s",
            page_id,
            title,
            version_number,
        )
        return page

    def create_or_update_page(
        self,
        *,
        space_id: str,
        parent_id: str,
        title: str,
        body: str,
        status: str = "current",
        representation: str = "storage",
        version_message: str | None = None,
        minor_edit: bool = False,
    ) -> dict[str, Any]:
        """Create a page when missing, otherwise replace the existing page body.

        Args:
            space_id: Confluence space ID where the page is created or searched.
            parent_id: Parent page ID for newly created pages and updated pages.
            title: Page title used to find or create the page.
            body: Page body value.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.
            version_message: Optional version message for updates.
            minor_edit: Whether the update is a minor edit.

        Returns:
            Raw Confluence page creation or update response.
        """
        page_id = self.get_page_id_by_title(title, space_id=space_id)
        if page_id is None:
            return self.create_page(
                space_id=space_id,
                parent_id=parent_id,
                title=title,
                body=body,
                status=status,
                representation=representation,
            )

        page = self.get_page(page_id, body_format=representation)
        version_number = _page_version_number(page) + 1
        return self.update_page(
            page_id,
            title=title,
            body=body,
            version_number=version_number,
            status=status,
            representation=representation,
            parent_id=parent_id,
            version_message=version_message,
            minor_edit=minor_edit,
        )

    def get_or_create_page(
        self,
        *,
        space_id: str,
        parent_id: str,
        title: str,
        body: str,
        status: str = "current",
        representation: str = "storage",
    ) -> dict[str, Any]:
        """Return an existing page by title, or create it when missing.

        Args:
            space_id: Confluence space ID where the page is created or searched.
            parent_id: Parent page ID used when the page must be created.
            title: Page title used to find or create the page.
            body: Page body value used only when the page must be created.
            status: Confluence page status. Defaults to ``current``.
            representation: Body representation. Defaults to ``storage``.

        Returns:
            Existing raw Confluence page response, or the created page response.
        """
        page_id = self.get_page_id_by_title(title, space_id=space_id)
        if page_id is not None:
            return self.get_page(page_id, body_format=representation)

        return self.create_page(
            space_id=space_id,
            parent_id=parent_id,
            title=title,
            body=body,
            status=status,
            representation=representation,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send an HTTP request and raise a ConfluenceAPIError on failure."""
        url = urljoin(self._base_url, path)
        self._logger.debug("Confluence API request: %s %s", method, path)
        response = self._client.request(method, url, **kwargs)
        if response.is_success:
            return response.json()

        detail = response.text[:500]
        self._logger.error(
            "Confluence API request failed: %s %s returned %s %s",
            method,
            path,
            response.status_code,
            response.reason_phrase,
        )
        raise ConfluenceAPIError(
            f"Confluence API request failed: {response.status_code} "
            f"{response.reason_phrase}: {detail}"
        )


def _page_version_number(page: dict[str, Any]) -> int:
    version = page.get("version")
    if not isinstance(version, dict):
        raise ConfluenceAPIError("Confluence page response did not include version")

    number = version.get("number")
    if not isinstance(number, int):
        raise ConfluenceAPIError(
            "Confluence page response did not include an integer version number"
        )

    return number
