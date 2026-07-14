"""Daily report workflow operations."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Any

from app import config
from app.report_storage import create_report_storage
from app.utils.confluence_client import ConfluenceClient
from app.utils.jira_client import JiraAPIError, JiraClient


def create_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("daily_report_builder")


def parse_date_range() -> tuple[datetime, datetime]:
    parser = argparse.ArgumentParser(description="Create a daily report in Confluence.")
    parser.add_argument("--start-date", help="Start datetime in yyyy/MM/dd HH:mm.")
    parser.add_argument("--end-date", help="End datetime in yyyy/MM/dd HH:mm.")
    args = parser.parse_args()

    start_value = args.start_date
    end_value = args.end_date

    while True:
        start_value = start_value or input("Start datetime (yyyy/MM/dd HH:mm): ")
        end_value = end_value or input("End datetime (yyyy/MM/dd HH:mm): ")

        try:
            start_date = datetime.strptime(start_value, config.DATETIME_FORMAT)
            end_date = datetime.strptime(end_value, config.DATETIME_FORMAT)
            if start_date > end_date:
                raise ValueError("start_date must not be later than end_date")
        except ValueError as exc:
            print(f"Invalid date range: {exc}")
            start_value = None
            end_value = None
            continue

        return start_date, end_date


def update_target_jira_filters(
    start_date: datetime,
    end_date: datetime,
    logger: logging.Logger,
) -> None:
    if not config.TARGET_JIRA_FILTER_IDS:
        logger.info("No target Jira filters configured")
        return

    with JiraClient(
        base_url=config.JIRA_BASE_URL,
        email=config.JIRA_EMAIL,
        api_token=config.JIRA_API_TOKEN,
        logger=logger,
    ) as client:
        for filter_id in config.TARGET_JIRA_FILTER_IDS:
            jira_filter = client.fetch_filter(filter_id)
            current_jql = jira_filter.get("jql")
            if not isinstance(current_jql, str) or not current_jql:
                raise JiraAPIError(
                    f"Jira filter {filter_id} did not include a non-empty JQL"
                )

            updated_jql = rewrite_filter_jql(current_jql, start_date, end_date)
            if not updated_jql:
                raise ValueError(
                    f"JQL updater returned an empty JQL for filter {filter_id}"
                )

            client.update_filter_jql(filter_id, updated_jql)


def rewrite_filter_jql(
    current_jql: str,
    start_date: datetime,
    end_date: datetime,
) -> str:
    """Return replacement JQL for the reporting period."""
    raise NotImplementedError("Jira filter JQL rewrite rules are not implemented")


def aggregate_slo(start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    return []


def confirm_dashboard_matches_sheet() -> None:
    while True:
        response = input("Do the dashboard and sheet match? [yes/no]: ")
        if response.strip().lower() in {"y", "yes"}:
            return


def build_report_body(
    start_date: datetime,
    end_date: datetime,
    slo_results: list[dict[str, Any]],
) -> str:
    return create_report_storage(start_date, end_date, slo_results)


def create_confluence_page(
    start_date: datetime,
    end_date: datetime,
    body: str,
) -> dict[str, Any]:
    title = f"Daily Report {start_date.isoformat()} - {end_date.isoformat()}"

    with ConfluenceClient(
        base_url=config.CONFLUENCE_BASE_URL,
        email=config.CONFLUENCE_EMAIL,
        api_token=config.CONFLUENCE_API_TOKEN,
    ) as client:
        return client.create_page(
            space_id=config.CONFLUENCE_SPACE_ID,
            parent_id=config.CONFLUENCE_PARENT_ID,
            title=title,
            body=body,
        )
