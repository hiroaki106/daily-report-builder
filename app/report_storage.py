"""Render Confluence storage-format report bodies."""

from __future__ import annotations

from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


_TEMPLATE_DIRECTORY = Path(__file__).parent.parent / "templates"
_DEFAULT_TEMPLATE = "report_storage.html.j2"


class _JiraMarkupParser(HTMLParser):
    """Preserve Jira links while escaping all other markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._anchor_open = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "a" or self._anchor_open:
            return

        href = next((value for name, value in attrs if name == "href"), None)
        if href is None or not _is_safe_href(href):
            return

        self.parts.append(f'<a href="{escape(href, quote=True)}">')
        self._anchor_open = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_open:
            self.parts.append("</a>")
            self._anchor_open = False

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data))

    def rendered(self) -> str:
        if self._anchor_open:
            self.parts.append("</a>")
            self._anchor_open = False
        return "".join(self.parts)


class _TextExtractor(HTMLParser):
    """Extract visible text from Jira cell markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def create_report_storage(
    start_date: datetime,
    end_date: datetime,
    slo_results: list[dict[str, Any]],
    *,
    template_name: str = _DEFAULT_TEMPLATE,
) -> str:
    """Render a Confluence storage-format report body from a Jinja template."""
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml", "j2"),
            default=True,
        ),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(template_name)
    return template.render(
        start_date=start_date,
        end_date=end_date,
        slo_results=slo_results,
    )


def create_two_dimensional_statistics_table(response: dict[str, Any]) -> str:
    """Convert a Jira two-dimensional statistics response to an HTML table."""
    rows = response.get("rows")
    first_row = response.get("firstRow")
    if not isinstance(rows, list) or not rows:
        return ""
    if not isinstance(first_row, dict):
        raise ValueError("Statistics response did not include firstRow")

    header_cells = _extract_cells(first_row, "firstRow")
    x_heading = _required_string(response, "xHeading")
    y_heading = _required_string(response, "yHeading")
    lines = [
        "<table>",
        "  <thead>",
        "    <tr>",
        f"      <th>{escape(y_heading)} / {escape(x_heading)}</th>",
    ]
    lines.extend(
        f"      <th>{_sanitize_jira_markup(cell)}</th>" for cell in header_cells
    )
    lines.extend(["    </tr>", "  </thead>", "  <tbody>"])

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Statistics row {index} is not an object")
        cells = _extract_cells(row, f"row {index}")
        lines.append("    <tr>")
        for cell_index, cell in enumerate(cells):
            tag = "th" if cell_index == 0 else "td"
            classes = cell.get("classes")
            class_attribute = _render_class_attribute(classes)
            lines.append(
                f"      <{tag}{class_attribute}>"
                f"{_sanitize_jira_markup(cell)}</{tag}>"
            )
        lines.append("    </tr>")

    lines.extend(["  </tbody>", "</table>"])
    return "\n".join(lines)


def create_two_dimensional_statistics_dataframe(
    response: dict[str, Any],
) -> pd.DataFrame:
    """Convert a Jira two-dimensional statistics response to a DataFrame."""
    first_row = response.get("firstRow")
    rows = response.get("rows")
    if not isinstance(first_row, dict):
        raise ValueError("Statistics response did not include firstRow")
    if not isinstance(rows, list):
        raise ValueError("Statistics response did not include rows")

    header_cells = _extract_cells(first_row, "firstRow")
    columns = [
        _required_string(response, "yHeading"),
        *(_extract_cell_text(cell) for cell in header_cells),
    ]
    records: list[list[str | int]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Statistics row {index} is not an object")
        cells = _extract_cells(row, f"row {index}")
        if len(cells) != len(columns):
            raise ValueError(
                f"Statistics row {index} has {len(cells)} cells; "
                f"expected {len(columns)}"
            )
        records.append([_coerce_cell_value(cell) for cell in cells])

    dataframe = pd.DataFrame.from_records(records, columns=columns)
    return dataframe.set_index(columns[0])


def _extract_cells(container: dict[str, Any], location: str) -> list[dict[str, Any]]:
    cells = container.get("cells")
    if not isinstance(cells, list):
        raise ValueError(f"Statistics {location} did not include cells")
    if not all(isinstance(cell, dict) for cell in cells):
        raise ValueError(f"Statistics {location} included an invalid cell")
    return cells


def _required_string(response: dict[str, Any], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Statistics response did not include {key}")
    return value


def _sanitize_jira_markup(cell: dict[str, Any]) -> str:
    markup = cell.get("markup")
    if not isinstance(markup, str):
        raise ValueError("Statistics cell did not include markup")
    parser = _JiraMarkupParser()
    parser.feed(markup)
    parser.close()
    return parser.rendered()


def _extract_cell_text(cell: dict[str, Any]) -> str:
    markup = cell.get("markup")
    if not isinstance(markup, str):
        raise ValueError("Statistics cell did not include markup")
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts).strip()


def _coerce_cell_value(cell: dict[str, Any]) -> str | int:
    value = _extract_cell_text(cell)
    try:
        return int(value)
    except ValueError:
        return value


def _render_class_attribute(classes: Any) -> str:
    if not isinstance(classes, list):
        return ""
    safe_classes = [value for value in classes if value == "totals"]
    if not safe_classes:
        return ""
    return f' class="{" ".join(safe_classes)}"'


def _is_safe_href(href: str) -> bool:
    parsed = urlparse(href)
    return not parsed.scheme or parsed.scheme in {"http", "https"}
