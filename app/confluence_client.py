from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin

import httpx


class ConfluenceAPIError(RuntimeError):
    """Raised when Confluence returns an unsuccessful response."""


class ConfluenceClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
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
        self._client.close()

    def __enter__(self) -> "ConfluenceClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_current_user(self) -> dict[str, Any]:
        return self._request("GET", "wiki/rest/api/user/current")

    def get_space_id_by_key(self, key: str) -> str | None:
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

    def get_page_content(
        self, page_id: str | int, *, body_format: str = "storage"
    ) -> str | None:
        response = self._request(
            "GET",
            f"wiki/api/v2/pages/{quote(str(page_id), safe='')}",
            params={"body-format": body_format},
        )
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

        return self._request("POST", "wiki/api/v2/pages", json=payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = urljoin(self._base_url, path)
        response = self._client.request(method, url, **kwargs)
        if response.is_success:
            return response.json()

        detail = response.text[:500]
        raise ConfluenceAPIError(
            f"Confluence API request failed: {response.status_code} "
            f"{response.reason_phrase}: {detail}"
        )
