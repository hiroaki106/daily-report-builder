from __future__ import annotations

import argparse
import html
import os
from datetime import date

from app.confluence_client import ConfluenceClient


def main() -> None:
    args = parse_args()
    report_date = date.fromisoformat(args.date) if args.date else date.today()

    base_url = require_env("CONFLUENCE_BASE_URL")
    email = require_env("CONFLUENCE_EMAIL")
    api_token = require_env("CONFLUENCE_API_TOKEN")
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
