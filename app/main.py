from __future__ import annotations

from app.report_workflow import (
    aggregate_slo,
    build_report_body,
    confirm_dashboard_matches_sheet,
    create_confluence_page,
    create_logger,
    parse_date_range,
    update_target_jira_filters,
)


def main() -> None:
    logger = create_logger()
    start_date, end_date = parse_date_range()
    update_target_jira_filters(start_date, end_date, logger)
    slo_results = aggregate_slo(start_date, end_date)
    confirm_dashboard_matches_sheet()
    body = build_report_body(start_date, end_date, slo_results)
    create_confluence_page(start_date, end_date, body)


if __name__ == "__main__":
    main()
