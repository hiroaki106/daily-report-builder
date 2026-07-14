"""Jira client for daily report generation."""

from __future__ import annotations

from math import ceil
from typing import Any

from app.utils.jira_client import JiraClient


class JiraRequestCancelledError(RuntimeError):
    """Raised when the user declines a large Jira request sequence."""


class DailyReportJiraClient(JiraClient):
    """Jira client that derives pagination limits from the JQL issue count."""

    def search_all_issues_by_jql(
        self,
        jql: str,
        *,
        fields: list[str] | None = None,
        max_results: int = 50,
        confirmation_threshold: int = 20,
    ) -> list[dict[str, Any]]:
        """Search all matching issues using a count-derived request limit.

        A console confirmation is required when the estimated issue search
        request count exceeds the threshold. The count request is excluded.
        """
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        if confirmation_threshold < 1:
            raise ValueError("confirmation_threshold must be at least 1")

        issue_count = self.count_issues_by_jql(jql)
        if issue_count == 0:
            return []

        max_requests = ceil(issue_count / max_results)
        estimated_request_count = max_requests
        if (
            estimated_request_count > confirmation_threshold
            and not _confirm_request_count(estimated_request_count)
        ):
            raise JiraRequestCancelledError("Jira issue search was cancelled")

        return super().search_issues_by_jql(
            jql,
            fields=fields,
            max_results=max_results,
            max_requests=max_requests,
        )


def _confirm_request_count(request_count: int) -> bool:
    prompt = (
        f"This Jira search may send up to {request_count} requests. "
        "Continue? [y/N]: "
    )
    try:
        response = input(prompt)
    except EOFError:
        return False

    return response.strip().lower() in {"y", "yes"}
