from datetime import datetime
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from app.report_storage import (
    create_report_storage,
    create_two_dimensional_statistics_dataframe,
    create_two_dimensional_statistics_table,
)


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

    def test_create_two_dimensional_statistics_table_renders_jira_response(
        self,
    ) -> None:
        result = create_two_dimensional_statistics_table(
            {
                "firstRow": {
                    "cells": [
                        {"markup": "False Positive"},
                        {"markup": "T:"},
                    ]
                },
                "rows": [
                    {
                        "cells": [
                            {"markup": "AWS"},
                            {
                                "classes": ["totals"],
                                "markup": "<a href='https://example.com'>3</a>",
                            },
                        ]
                    }
                ],
                "xHeading": "Resolution",
                "yHeading": "Incident Type",
            }
        )

        self.assertIn("<th>Incident Type / Resolution</th>", result)
        self.assertIn("<th>False Positive</th>", result)
        self.assertIn("<th>AWS</th>", result)
        self.assertIn(
            '<td class="totals"><a href="https://example.com">3</a></td>',
            result,
        )

    def test_create_two_dimensional_statistics_table_returns_empty_string(
        self,
    ) -> None:
        result = create_two_dimensional_statistics_table(
            {
                "firstRow": {"cells": []},
                "rows": [],
                "xHeading": "Resolution",
                "yHeading": "Incident Type",
            }
        )

        self.assertEqual(result, "")

    def test_create_two_dimensional_statistics_table_sanitizes_markup(self) -> None:
        result = create_two_dimensional_statistics_table(
            {
                "firstRow": {"cells": [{"markup": "Count"}]},
                "rows": [
                    {
                        "cells": [
                            {"markup": "<script>alert('x')</script>"},
                            {"markup": "<a href='javascript:alert(1)'>1</a>"},
                        ]
                    }
                ],
                "xHeading": "X <heading>",
                "yHeading": "Y & heading",
            }
        )

        self.assertNotIn("<script>", result)
        self.assertNotIn("javascript:", result)
        self.assertIn("alert(&#x27;x&#x27;)", result)
        self.assertIn("Y &amp; heading / X &lt;heading&gt;", result)

    def test_create_two_dimensional_statistics_dataframe_extracts_values(
        self,
    ) -> None:
        result = create_two_dimensional_statistics_dataframe(
            {
                "firstRow": {
                    "cells": [
                        {"markup": "False Positive"},
                        {"markup": "T:"},
                    ]
                },
                "rows": [
                    {
                        "cells": [
                            {"markup": "AWS"},
                            {"markup": "<a href='https://example.com'>1</a>"},
                            {"markup": "<a href='https://example.com'>3</a>"},
                        ]
                    },
                    {
                        "cells": [
                            {"markup": "Total Unique Issues:"},
                            {"markup": "<a href='https://example.com'>2</a>"},
                            {"markup": "<a href='https://example.com'>4</a>"},
                        ]
                    },
                ],
                "xHeading": "Resolution",
                "yHeading": "Incident Type",
            }
        )

        expected = pd.DataFrame(
            [
                ["AWS", 1, 3],
                ["Total Unique Issues:", 2, 4],
            ],
            columns=["Incident Type", "False Positive", "T:"],
        ).set_index("Incident Type")
        assert_frame_equal(result, expected)
        self.assertEqual(result.at["AWS", "False Positive"], 1)

    def test_create_two_dimensional_statistics_dataframe_preserves_empty_columns(
        self,
    ) -> None:
        result = create_two_dimensional_statistics_dataframe(
            {
                "firstRow": {"cells": []},
                "rows": [],
                "xHeading": "Resolution",
                "yHeading": "Incident Type",
            }
        )

        expected = pd.DataFrame(columns=["Incident Type"]).set_index("Incident Type")
        assert_frame_equal(result, expected)


if __name__ == "__main__":
    unittest.main()
