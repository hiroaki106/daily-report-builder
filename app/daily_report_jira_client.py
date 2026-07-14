"""Jira client for daily report generation."""

from __future__ import annotations

from math import ceil
from typing import Any

from app.utils.jira_client import JiraClient


class DailyReportJiraClient(JiraClient):
    """Jira client that derives pagination limits from the JQL issue count."""

    def search_all_issues_by_jql(
        self,
        jql: str,
        *,
        fields: list[str] | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search all matching issues using a count-derived request limit."""
        if max_results < 1:
            raise ValueError("max_results must be at least 1")

        issue_count = self.count_issues_by_jql(jql)
        if issue_count == 0:
            return []

        max_requests = ceil(issue_count / max_results)
        return super().search_issues_by_jql(
            jql,
            fields=fields,
            max_results=max_results,
            max_requests=max_requests,
        )
