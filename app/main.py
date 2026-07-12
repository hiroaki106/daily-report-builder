from __future__ import annotations

import argparse
import html
import logging
import os
from datetime import date, datetime
from typing import TypedDict

from app.confluence_client import ConfluenceClient


class StatusChange(TypedDict):
    from_status: str | None
    to_status: str | None
    changed_at: str | None


def main() -> None:
    configure_logging()

    args = parse_args()
    report_date = date.fromisoformat(args.date) if args.date else date.today()

    base_url = require_env("CONFLUENCE_BASE_URL")
    email = os.getenv("CONFLUENCE_EMAIL")
    api_token = os.getenv("CONFLUENCE_API_TOKEN")
    space_id = require_env("CONFLUENCE_SPACE_ID")
    parent_id = args.parent_id or require_env("CONFLUENCE_PARENT_ID")

    title = args.title or f"Daily Report {report_date.isoformat()}"
    body = build_daily_report_body(report_date=report_date, content=args.content)

    with ConfluenceClient(
        base_url=base_url, email=email, api_token=api_token
    ) as client:
        page = client.create_page(
            space_id=space_id,
            parent_id=parent_id,
            title=title,
            body=body,
        )

    web_url = build_web_url(base_url, page)
    print(f"Created Confluence page: {page.get('id')}")
    if web_url:
        print(web_url)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a daily report in Confluence.")
    parser.add_argument(
        "--date",
        help="Report date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--title",
        help="Page title. Defaults to 'Daily Report YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--content",
        default="",
        help="Plain text report body to include in the page.",
    )
    parser.add_argument(
        "--parent-id",
        help="Parent page ID. Overrides CONFLUENCE_PARENT_ID when provided.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
    """Exclude adjacent transitions that immediately reverse each other.

    The input is expected to be in chronological order. For example,
    ``Open -> Assign`` followed by ``Assign -> Open`` is removed as one pair.
    """
    filtered_changes: list[StatusChange] = []
    index = 0

    while index < len(status_changes):
        current = status_changes[index]
        if index + 1 < len(status_changes):
            following = status_changes[index + 1]
            from_status = current["from_status"]
            to_status = current["to_status"]
            is_immediate_reverse = (
                from_status is not None
                and to_status is not None
                and from_status != to_status
                and following["from_status"] == to_status
                and following["to_status"] == from_status
            )
            if is_immediate_reverse:
                index += 2
                continue

        filtered_changes.append(current)
        index += 1

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


if __name__ == "__main__":
    main()
