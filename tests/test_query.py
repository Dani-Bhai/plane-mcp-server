from __future__ import annotations

import unittest

from plane_mcp.query import build_work_item_pql, escape_pql_value


class QueryTest(unittest.TestCase):
    def test_escape_pql_value_escapes_quotes_and_backslashes(self) -> None:
        self.assertEqual(r'one\\wo\"three', escape_pql_value('one\\wo"three'))

    def test_build_work_item_pql_builds_structured_filters(self) -> None:
        self.assertEqual(
            'state = "state-1" AND priority = "urgent" AND target_date <= "2026-10-01"',
            build_work_item_pql(state="state-1", priority="urgent", target_date_before="2026-10-01"),
        )

    def test_build_work_item_pql_combines_raw_pql_and_date_filters(self) -> None:
        self.assertEqual(
            'target_date >= "2026-01-01" AND (priority = "high")',
            build_work_item_pql(pql='priority = "high"', target_date_after="2026-01-01"),
        )
        self.assertIsNone(build_work_item_pql())


if __name__ == "__main__":
    unittest.main()
