"""Temporarily retained helpers from the previous CLI workflow."""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import TypedDict


class StatusChange(TypedDict):
    from_status: str | None
    to_status: str | None
    changed_at: str | None


def find_first_status_change(
    status_changes: list[StatusChange], status: str
) -> StatusChange | None:
    """Return the earliest transition to the specified Jira status."""
    matching_changes = (
        change
        for change in status_changes
        if change["to_status"] == status and change["changed_at"] is not None
    )
    return min(
        matching_changes,
        key=lambda change: datetime.fromisoformat(change["changed_at"]),
        default=None,
    )


def exclude_immediate_reverse_transitions(
    status_changes: list[StatusChange],
) -> list[StatusChange]:
    """Exclude adjacent reverse transitions until no reverse pairs remain."""
    filtered_changes: list[StatusChange] = []

    for current in status_changes:
        if filtered_changes:
            previous = filtered_changes[-1]
            from_status = previous["from_status"]
            to_status = previous["to_status"]
            is_immediate_reverse = (
                from_status is not None
                and to_status is not None
                and from_status != to_status
                and current["from_status"] == to_status
                and current["to_status"] == from_status
            )
            if is_immediate_reverse:
                filtered_changes.pop()
                continue

        filtered_changes.append(current)

    return filtered_changes


def build_daily_report_body(*, report_date: date, content: str) -> str:
    escaped_content = html.escape(content).replace("\n", "<br />")
    if not escaped_content:
        escaped_content = "<em>No report content provided.</em>"

    return "\n".join(
        [
            f"<h1>Daily Report {report_date.isoformat()}</h1>",
            "<h2>Summary</h2>",
            f"<p>{escaped_content}</p>",
        ]
    )


def build_web_url(base_url: str, page: dict[str, object]) -> str | None:
    links = page.get("_links")
    if not isinstance(links, dict):
        return None

    webui = links.get("webui")
    if not isinstance(webui, str):
        return None

    link_base = links.get("base")
    if isinstance(link_base, str):
        return link_base.rstrip("/") + webui

    return base_url.rstrip("/") + webui
