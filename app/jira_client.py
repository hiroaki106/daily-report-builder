"""Client helpers for Jira Cloud API and Jira gadget endpoints."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urljoin

import httpx


_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.NullHandler())


class JiraAPIError(RuntimeError):
    """Raised when Jira returns an unsuccessful response."""


class JiraClient:
    """Synchronous client for the Jira Cloud APIs used by this application."""

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
        """Initialize an authenticated Jira API client.

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

    def __enter__(self) -> "JiraClient":
        """Return this client for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client when leaving a context manager block."""
        self.close()

    def search_issues_by_jql(
        self,
        jql: str,
        *,
        max_results: int = 50,
        fields: list[str] | None = None,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        """Search Jira issues by JQL and return the raw search response.

        Args:
            jql: Jira Query Language string to execute.
            max_results: Maximum number of issues to return in this request.
            fields: Optional issue field IDs or names to include in the response.
            next_page_token: Token from a previous response for fetching the next page.

        Returns:
            Raw Jira issue search response.
        """
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
        """Fetch all changelog history entries for an issue.

        Args:
            issue_id_or_key: Jira issue ID or issue key, such as ``DEV-123``.
            max_results: Page size used when fetching changelog entries.

        Returns:
            List of changelog history objects from every fetched page.
        """
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
        """Fetch a Jira filter by ID.

        Args:
            filter_id: Numeric filter ID as an int or string.

        Returns:
            Raw Jira filter response.
        """
        return self._request(
            "GET", f"rest/api/3/filter/{quote(str(filter_id), safe='')}"
        )

    def get_filter_statistics(
        self,
        filter_id: str | int,
        stat_type: str,
        *,
        include_resolved_issues: bool = True,
    ) -> dict[str, Any]:
        """Fetch one-dimensional gadget statistics for a Jira filter.

        Args:
            filter_id: Numeric filter ID, with or without the ``filter-`` prefix.
            stat_type: Jira statistic type, such as ``statuses`` or ``assignees``.
            include_resolved_issues: Whether resolved issues are included.

        Returns:
            Raw Jira gadget statistics response.
        """
        return self._request(
            "GET",
            "rest/gadget/1.0/statistics",
            params={
                "filterId": _format_gadget_filter_id(filter_id),
                "statType": stat_type,
                "includeResolvedIssues": _bool_param(include_resolved_issues),
            },
        )

    def get_two_dimensional_filter_statistics(
        self,
        filter_id: str | int,
        *,
        x_stat_type: str,
        y_stat_type: str,
        sort_by: str = "natural",
        sort_direction: str = "asc",
        number_to_show: int = 50,
    ) -> dict[str, Any]:
        """Fetch two-dimensional gadget statistics for a Jira filter.

        Args:
            filter_id: Numeric filter ID, with or without the ``filter-`` prefix.
            x_stat_type: Statistic type for the X axis.
            y_stat_type: Statistic type for the Y axis.
            sort_by: Jira gadget sort key, for example ``natural`` or ``total``.
            sort_direction: Sort direction, usually ``asc`` or ``desc``.
            number_to_show: Maximum number of rows/columns returned by the gadget API.

        Returns:
            Raw Jira two-dimensional gadget statistics response.
        """
        return self._request(
            "GET",
            "rest/gadget/1.0/twoDimensionalFilterStats/generate",
            params={
                "filterId": _format_gadget_filter_id(filter_id),
                "xstattype": x_stat_type,
                "ystattype": y_stat_type,
                "sortBy": sort_by,
                "sortDirection": sort_direction,
                "numberToShow": number_to_show,
            },
        )

    def update_filter_jql(self, filter_id: str | int, jql: str) -> dict[str, Any]:
        """Update only the JQL of a Jira filter, preserving its name and description.

        Args:
            filter_id: Numeric filter ID as an int or string.
            jql: Replacement JQL expression for the filter.

        Returns:
            Raw Jira filter update response.
        """
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

        updated_filter = self._request(
            "PUT",
            f"rest/api/3/filter/{quote(str(filter_id), safe='')}",
            json=payload,
        )
        self._logger.info("Updated Jira filter JQL: filter_id=%s", filter_id)
        return updated_filter

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send an HTTP request and raise a JiraAPIError for unsuccessful responses."""
        url = urljoin(self._base_url, path)
        self._logger.debug("Jira API request: %s %s", method, path)
        response = self._client.request(method, url, **kwargs)
        if response.is_success:
            return response.json()

        detail = response.text[:500]
        self._logger.error(
            "Jira API request failed: %s %s returned %s %s",
            method,
            path,
            response.status_code,
            response.reason_phrase,
        )
        raise JiraAPIError(
            f"Jira API request failed: {response.status_code} "
            f"{response.reason_phrase}: {detail}"
        )


def extract_status_changes(
    changelog: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, str | None]]:
    """Extract status transitions from a Jira changelog response or history list.

    Args:
        changelog: Raw changelog response, ``values``/``histories`` container,
            or a list of changelog history objects.

    Returns:
        List of status transition dictionaries with ``from_status``, ``to_status``,
        and ``changed_at`` keys.
    """
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


def _format_gadget_filter_id(filter_id: str | int) -> str:
    filter_id_text = str(filter_id)
    if filter_id_text.startswith("filter-"):
        return filter_id_text
    return f"filter-{filter_id_text}"


def _bool_param(value: bool) -> str:
    return str(value).lower()
