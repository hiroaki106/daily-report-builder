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

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-jql-post

        Permissions:
            Requires Browse projects permission for matching issue projects, plus
            issue-level security permission when issue security is configured.
            OAuth scopes: classic ``read:jira-work``; granular scopes include
            ``read:issue-details:jira``. Connect scope: ``READ``.
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

    def search_all_issues_by_jql(
        self,
        jql: str,
        *,
        max_results: int = 50,
        fields: list[str] | None = None,
        max_requests: int = 10,
    ) -> list[dict[str, Any]]:
        """Search Jira issues by JQL across pages, bounded by request count.

        Args:
            jql: Jira Query Language string to execute.
            max_results: Maximum number of issues to return per request.
            fields: Optional issue field IDs or names to include in the response.
            max_requests: Maximum number of API requests to send.

        Returns:
            Issue objects from every fetched page.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-jql-post

        Permissions:
            Same as ``search_issues_by_jql``.
        """
        _validate_max_requests(max_requests)

        issues: list[dict[str, Any]] = []
        next_page_token: str | None = None

        for _ in range(max_requests):
            response = self.search_issues_by_jql(
                jql,
                max_results=max_results,
                fields=fields,
                next_page_token=next_page_token,
            )
            page_issues = response.get("issues", [])
            if not isinstance(page_issues, list):
                raise JiraAPIError("Jira search response did not include an issues list")

            issues.extend(issue for issue in page_issues if isinstance(issue, dict))

            next_page_token_value = response.get("nextPageToken")
            next_page_token = (
                next_page_token_value
                if isinstance(next_page_token_value, str)
                and next_page_token_value
                else None
            )
            if response.get("isLast") is True or next_page_token is None:
                break
        else:
            self._logger.warning(
                "Stopped Jira issue search after max_requests=%s", max_requests
            )

        return issues

    def count_issues_by_jql(self, jql: str) -> int:
        """Return Jira's approximate count for a bounded JQL query.

        Args:
            jql: Jira Query Language string to count.

        Returns:
            Approximate number of matching issues.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-approximate-count-post

        Permissions:
            Counts only issues visible through Browse projects permission and
            issue-level security. OAuth scopes: classic ``read:jira-work``;
            granular scopes include ``read:issue-details:jira``. Connect scope:
            ``READ``.
        """
        response = self._request(
            "POST",
            "rest/api/3/search/approximate-count",
            json={"jql": jql},
        )
        count = response.get("count")
        if not isinstance(count, int):
            raise JiraAPIError("Jira count response did not include an integer count")

        return count

    def get_issue(
        self,
        issue_id_or_key: str,
        *,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch a Jira issue by issue ID or key.

        Args:
            issue_id_or_key: Jira issue ID or issue key, such as ``DEV-123``.
            fields: Optional issue field IDs or names to include in the response.
            expand: Optional Jira expand values, such as ``changelog`` or ``renderedFields``.

        Returns:
            Raw Jira issue response.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-get

        Permissions:
            Requires Browse projects permission for the issue project, plus
            issue-level security permission when issue security is configured.
            OAuth scopes: classic ``read:jira-work``; granular scopes include
            ``read:issue-details:jira``. Connect scope: ``READ``.
        """
        params: dict[str, str] = {}
        if fields is not None:
            params["fields"] = ",".join(fields)
        if expand is not None:
            params["expand"] = ",".join(expand)

        return self._request(
            "GET",
            f"rest/api/3/issue/{quote(issue_id_or_key)}",
            params=params or None,
        )

    def get_issue_comments(
        self,
        issue_id_or_key: str,
        *,
        max_results: int = 100,
        order_by: str | None = None,
        expand: list[str] | None = None,
        max_requests: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch issue comments across pages, bounded by request count.

        Args:
            issue_id_or_key: Jira issue ID or issue key, such as ``DEV-123``.
            max_results: Maximum number of comments to return per request.
            order_by: Optional Jira ordering expression, such as ``created``.
            expand: Optional Jira expand values for comments.
            max_requests: Maximum number of API requests to send.

        Returns:
            Comment objects from every fetched page.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-get

        Permissions:
            Requires Browse projects permission, issue-level security permission
            when configured, and membership in the comment visibility group or
            role when the comment is restricted. OAuth scopes: classic
            ``read:jira-work``; granular scopes include ``read:comment:jira``.
            Connect scope: ``READ``.
        """
        _validate_max_requests(max_requests)

        start_at = 0
        comments: list[dict[str, Any]] = []

        for _ in range(max_requests):
            params: dict[str, str | int] = {
                "startAt": start_at,
                "maxResults": max_results,
            }
            if order_by is not None:
                params["orderBy"] = order_by
            if expand is not None:
                params["expand"] = ",".join(expand)

            response = self._request(
                "GET",
                f"rest/api/3/issue/{quote(issue_id_or_key)}/comment",
                params=params,
            )
            page_comments = response.get("comments", [])
            if not isinstance(page_comments, list):
                raise JiraAPIError(
                    "Jira comments response did not include a comments list"
                )

            comments.extend(
                comment for comment in page_comments if isinstance(comment, dict)
            )

            total = response.get("total")
            is_last = response.get("isLast")
            start_at = int(response.get("startAt", start_at)) + len(page_comments)
            if (
                is_last is True
                or not page_comments
                or (isinstance(total, int) and start_at >= total)
            ):
                break
        else:
            self._logger.warning(
                "Stopped Jira comment fetch after max_requests=%s", max_requests
            )

        return comments

    def get_issue_changelog(
        self,
        issue_id_or_key: str,
        *,
        max_results: int = 100,
        max_requests: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch changelog history entries for an issue, bounded by request count.

        Args:
            issue_id_or_key: Jira issue ID or issue key, such as ``DEV-123``.
            max_results: Page size used when fetching changelog entries.
            max_requests: Maximum number of API requests to send.

        Returns:
            List of changelog history objects from every fetched page.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-changelog-get

        Permissions:
            Requires Browse projects permission for the issue project, plus
            issue-level security permission when issue security is configured.
            OAuth scopes: classic ``read:jira-work``; granular scopes include
            ``read:issue.changelog:jira``. Connect scope: ``READ``.
        """
        _validate_max_requests(max_requests)

        start_at = 0
        histories: list[dict[str, Any]] = []

        for _ in range(max_requests):
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
        else:
            self._logger.warning(
                "Stopped Jira changelog fetch after max_requests=%s", max_requests
            )

        return histories

    def get_bulk_changelogs(
        self,
        issue_ids_or_keys: list[str],
        *,
        field_ids: list[str] | None = None,
        max_results: int = 100,
        max_requests: int = 10,
    ) -> list[dict[str, Any]]:
        """Bulk fetch changelogs for multiple issues, bounded by request count.

        Args:
            issue_ids_or_keys: Jira issue IDs or issue keys to fetch changelogs for.
            field_ids: Optional field IDs used to filter changelog items.
            max_results: Maximum number of changelog groups to return per request.
            max_requests: Maximum number of API requests to send.

        Returns:
            ``issueChangeLogs`` objects from every fetched page.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-changelog-bulkfetch-post

        Permissions:
            Requires Browse projects permission for the issue projects, plus
            issue-level security permission when issue security is configured.
            OAuth scopes: classic ``read:jira-work``; granular scopes include
            ``read:issue.changelog:jira``. Connect apps cannot access this
            resource.
        """
        _validate_max_requests(max_requests)
        if not issue_ids_or_keys:
            return []

        issue_changelogs: list[dict[str, Any]] = []
        next_page_token: str | None = None

        for _ in range(max_requests):
            payload: dict[str, Any] = {
                "issueIdsOrKeys": issue_ids_or_keys,
                "maxResults": max_results,
            }
            if field_ids is not None:
                payload["fieldIds"] = field_ids
            if next_page_token is not None:
                payload["nextPageToken"] = next_page_token

            response = self._request(
                "POST",
                "rest/api/3/changelog/bulkfetch",
                json=payload,
            )
            values = response.get("issueChangeLogs", [])
            if not isinstance(values, list):
                raise JiraAPIError(
                    "Jira bulk changelog response did not include an issueChangeLogs list"
                )

            issue_changelogs.extend(value for value in values if isinstance(value, dict))

            next_page_token_value = response.get("nextPageToken")
            next_page_token = (
                next_page_token_value
                if isinstance(next_page_token_value, str)
                and next_page_token_value
                else None
            )
            if next_page_token is None:
                break
        else:
            self._logger.warning(
                "Stopped Jira bulk changelog fetch after max_requests=%s",
                max_requests,
            )

        return issue_changelogs

    def get_filter(self, filter_id: str | int) -> dict[str, Any]:
        """Fetch a Jira filter by ID.

        Args:
            filter_id: Numeric filter ID as an int or string.

        Returns:
            Raw Jira filter response.

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-filters/#api-rest-api-3-filter-id-get

        Permissions:
            Returns filters owned by the user or shared with the user through
            group, project, public project, or public sharing. OAuth scopes:
            classic ``read:jira-work``; granular scopes include
            ``read:filter:jira``. Connect scope: ``READ``.
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

        Reference:
            No public Atlassian REST API v3 reference was found for this gadget
            endpoint.

        Permissions:
            Uses the Jira gadget statistics endpoint; access depends on the
            filter visibility and the user's issue permissions.
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

        Reference:
            No public Atlassian REST API v3 reference was found for this gadget
            endpoint.

        Permissions:
            Uses the Jira gadget statistics endpoint; access depends on the
            filter visibility and the user's issue permissions.
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

        Reference:
            https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-filters/#api-rest-api-3-filter-id-put

        Permissions:
            Requires Jira access and ownership of the filter. OAuth scopes:
            classic ``write:jira-work``; granular scopes include
            ``write:filter:jira`` and ``read:filter:jira``. Connect scope:
            ``WRITE``.
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


def _validate_max_requests(max_requests: int) -> None:
    if max_requests < 1:
        raise ValueError("max_requests must be at least 1")


def _format_gadget_filter_id(filter_id: str | int) -> str:
    filter_id_text = str(filter_id)
    if filter_id_text.startswith("filter-"):
        return filter_id_text
    return f"filter-{filter_id_text}"


def _bool_param(value: bool) -> str:
    return str(value).lower()
