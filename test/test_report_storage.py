from datetime import datetime
import unittest

from app.report_storage import create_report_storage


class ReportStorageTest(unittest.TestCase):
    def test_create_report_storage_renders_report_values(self) -> None:
        result = create_report_storage(
            datetime(2026, 7, 1, 9),
            datetime(2026, 7, 1, 18),
            [{"name": "Availability", "value": "99.9%"}],
        )

        self.assertIn("2026/07/01 09:00 - 2026/07/01 18:00", result)
        self.assertIn("Availability", result)
        self.assertIn("99.9%", result)

    def test_create_report_storage_escapes_dynamic_values(self) -> None:
        result = create_report_storage(
            datetime(2026, 7, 1, 9),
            datetime(2026, 7, 1, 18),
            [{"name": "<script>", "value": "A & B"}],
        )

        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("A &amp; B", result)

    def test_create_report_storage_renders_empty_state(self) -> None:
        result = create_report_storage(
            datetime(2026, 7, 1, 9),
            datetime(2026, 7, 1, 18),
            [],
        )

        self.assertIn("No SLO results.", result)


if __name__ == "__main__":
    unittest.main()
