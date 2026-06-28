from datetime import date
import os
import unittest
from unittest.mock import patch

from app.main import build_daily_report_body, build_web_url, require_env


class MainTest(unittest.TestCase):
    def test_build_daily_report_body_escapes_plain_text(self) -> None:
        body = build_daily_report_body(
            report_date=date(2026, 6, 28),
            content="done <review>\nnext",
        )

        self.assertIn("<h1>Daily Report 2026-06-28</h1>", body)
        self.assertIn("done &lt;review&gt;<br />next", body)

    def test_build_daily_report_body_uses_placeholder_for_empty_content(self) -> None:
        body = build_daily_report_body(report_date=date(2026, 6, 28), content="")

        self.assertIn("<em>No report content provided.</em>", body)

    def test_build_web_url_uses_confluence_link_base_when_available(self) -> None:
        url = build_web_url(
            "https://example.atlassian.net",
            {
                "_links": {
                    "base": "https://example.atlassian.net/wiki",
                    "webui": "/spaces/DEV/pages/123/Daily+Report",
                }
            },
        )

        self.assertEqual(
            url,
            "https://example.atlassian.net/wiki/spaces/DEV/pages/123/Daily+Report",
        )

    def test_build_web_url_returns_none_without_webui(self) -> None:
        self.assertIsNone(build_web_url("https://example.atlassian.net", {}))

    def test_require_env_returns_value(self) -> None:
        with patch.dict(os.environ, {"CONFLUENCE_SPACE_ID": "123"}, clear=True):
            self.assertEqual(require_env("CONFLUENCE_SPACE_ID"), "123")

    def test_require_env_raises_for_missing_value(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CONFLUENCE_SPACE_ID"):
                require_env("CONFLUENCE_SPACE_ID")


if __name__ == "__main__":
    unittest.main()
