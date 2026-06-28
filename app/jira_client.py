from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin

import httpx


class JiraAPIError(RuntimeError):
    """Raised when Jira returns an unsuccessful response."""


class JiraClient:
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

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def search_issues_by_jql(
        self,
        jql: str,
        *,
        max_results: int = 50,
        fields: list[str] | None = None,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
        }
        if fields is not None:
            payload["fields"] = fields
        if next_page_token is not None:
            payload["nextPageToken"] = next_page_token

        return self._request("POST", "rest/api/3/search/jql", json=payload)

    def get_issue_changelog(
        self,
        issue_id_or_key: str,
        *,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        start_at = 0
        histories: list[dict[str, Any]] = []

        while True:
            response = self._request(
                "GET",
                f"rest/api/3/issue/{quote(issue_id_or_key)}/changelog",
                params={"startAt": start_at, "maxResults": max_results},
            )
            values = response.get("values", [])
            if not isinstance(values, list):
                raise JiraAPIError(
                    "Jira changelog response did not include a values list"
                )

            histories.extend(value for value in values if isinstance(value, dict))

            total = response.get("total")
            is_last = response.get("isLast")
            start_at = int(response.get("startAt", start_at)) + len(values)
            if (
                is_last is True
                or not values
                or (isinstance(total, int) and start_at >= total)
            ):
                break

        return histories

    def get_filter(self, filter_id: str | int) -> dict[str, Any]:
        return self._request(
            "GET", f"rest/api/3/filter/{quote(str(filter_id), safe='')}"
        )

    def update_filter_jql(self, filter_id: str | int, jql: str) -> dict[str, Any]:
        current_filter = self.get_filter(filter_id)
        name = current_filter.get("name")
        if not isinstance(name, str) or not name:
            raise JiraAPIError("Jira filter response did not include a filter name")

        payload: dict[str, Any] = {
            "name": name,
            "jql": jql,
        }
        description = current_filter.get("description")
        if isinstance(description, str):
            payload["description"] = description

        return self._request(
            "PUT",
            f"rest/api/3/filter/{quote(str(filter_id), safe='')}",
            json=payload,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = urljoin(self._base_url, path)
        response = self._client.request(method, url, **kwargs)
        if response.is_success:
            return response.json()

        detail = response.text[:500]
        raise JiraAPIError(
            f"Jira API request failed: {response.status_code} "
            f"{response.reason_phrase}: {detail}"
        )


def extract_status_changes(
    changelog: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, str | None]]:
    changes: list[dict[str, str | None]] = []

    for history in _iter_histories(changelog):
        changed_at = history.get("created")
        items = history.get("items", [])
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("field") != "status" and item.get("fieldId") != "status":
                continue

            changes.append(
                {
                    "from_status": _optional_str(item.get("fromString")),
                    "to_status": _optional_str(item.get("toString")),
                    "changed_at": _optional_str(changed_at),
                }
            )

    return changes


def _iter_histories(
    changelog: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(changelog, list):
        return [history for history in changelog if isinstance(history, dict)]

    values = changelog.get("values")
    if isinstance(values, list):
        return [history for history in values if isinstance(history, dict)]

    histories = changelog.get("histories")
    if isinstance(histories, list):
        return [history for history in histories if isinstance(history, dict)]

    return []


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
