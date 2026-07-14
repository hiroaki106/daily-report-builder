"""Render Confluence storage-format report bodies."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


_TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")
_DEFAULT_TEMPLATE = "report_storage.html.j2"


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
