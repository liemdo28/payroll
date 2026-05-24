"""Tests for the Sheet Supper comparator."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.compare.supper_compare import (
    compare, parse_supper_rows, summary_stats, CompareRow, TOLERANCE,
)


# ── Minimal mock objects ──────────────────────────────────────────────────────

class _Row:
    """Minimal EmployeePaySummary stand-in."""
    def __init__(self, name, **kwargs):
        self.search_name   = name
        self.other_name    = ""
        self.display_name  = name
        self.total_hours   = kwargs.get("total_hours", 0.0)
        self.ot_hours      = kwargs.get("ot_hours", 0.0)
        self.regular_hours = kwargs.get("regular_hours", 0.0)
        self.tip           = kwargs.get("tip", 0.0)
        self.busser_cashier= kwargs.get("busser_cashier", 0.0)
        self.sushi_tip     = kwargs.get("sushi_tip", 0.0)
        self.kitchen_tip   = kwargs.get("kitchen_tip", 0.0)
        self.bartender_tip = kwargs.get("bartender_tip", 0.0)
        self.grand_total   = kwargs.get("grand_total", 0.0)


SUPPER_HEADER = [
    "Search Name", "Other name", "Name",
    "Total hours", "Over (OT)", "Regular",
    "Tip", "Busser/Cashier/Hostess", "Sushi chef",
    "Kitchen", "Bartender", "Total",
]


def _supper_row(name, total_hours=0, ot=0, regular=0,
                tip=0, busser=0, sushi=0, kitchen=0, bar=0, grand=0):
    def f(v):
        return f"${v:,.2f}" if v else ""
    return [
        name, "", name,
        str(total_hours) if total_hours else "",
        str(ot)          if ot          else "",
        str(regular)     if regular     else "0.00",
        f(tip), f(busser), f(sushi), f(kitchen), f(bar), f(grand),
    ]


# ── Tests ────────────────────────────────────────────────────────────────────

class TestParseSupperRows:
    def test_parses_employee_row(self):
        rows = [
            SUPPER_HEADER,
            _supper_row("Alice", total_hours=40, tip=100, grand=100),
        ]
        result = parse_supper_rows(rows)
        assert "alice" in result
        assert result["alice"]["grand_total"] == 100.0

    def test_skips_blank_rows(self):
        rows = [SUPPER_HEADER, [], _supper_row("Bob", grand=50)]
        result = parse_supper_rows(rows)
        assert "bob" in result

    def test_skips_period_header(self):
        rows = [
            SUPPER_HEADER,
            ["Period: 04/27 – 05/10", "", "", "", "", "", "", "", "", "", "", ""],
            _supper_row("Charlie", grand=75),
        ]
        result = parse_supper_rows(rows)
        assert "charlie" in result
        assert "period: 04/27" not in result

    def test_empty_sheet(self):
        assert parse_supper_rows([]) == {}


class TestCompare:
    def test_perfect_match(self):
        our  = [_Row("Alice", grand_total=100.0, tip=100.0)]
        them = [SUPPER_HEADER, _supper_row("Alice", tip=100, grand=100)]
        rows = compare(our, them, tolerance=TOLERANCE)
        statuses = {r.status for r in rows}
        assert "DIFF" not in statuses
        assert "MATCH" in statuses

    def test_diff_detected(self):
        our  = [_Row("Bob", grand_total=100.0)]
        them = [SUPPER_HEADER, _supper_row("Bob", grand=50)]
        rows = compare(our, them, tolerance=TOLERANCE)
        diffs = [r for r in rows if r.status == "DIFF" and r.field_name == "grand_total"]
        assert len(diffs) == 1
        assert diffs[0].diff == 50.0

    def test_within_tolerance_is_match(self):
        our  = [_Row("Carol", grand_total=100.50)]
        them = [SUPPER_HEADER, _supper_row("Carol", grand=100)]
        rows = compare(our, them, tolerance=TOLERANCE)
        totals = [r for r in rows if r.field_name == "grand_total"]
        assert totals[0].status == "MATCH"

    def test_missing_in_output(self):
        our  = []
        them = [SUPPER_HEADER, _supper_row("Dave", grand=200)]
        rows = compare(our, them, tolerance=TOLERANCE)
        missing = [r for r in rows if r.status == "MISSING_IN_OUTPUT"]
        assert any(r.employee_name.lower() == "dave" for r in missing)

    def test_missing_in_supper(self):
        our  = [_Row("Eve", grand_total=150.0, tip=150.0)]
        them = [SUPPER_HEADER]   # Eve not in Supper
        rows = compare(our, them, tolerance=TOLERANCE)
        missing = [r for r in rows if r.status == "MISSING_IN_SUPPER"]
        assert any("eve" in r.employee_name.lower() for r in missing)

    def test_name_case_insensitive(self):
        our  = [_Row("Frank Smith", grand_total=80.0, tip=80.0)]
        them = [SUPPER_HEADER, _supper_row("FRANK SMITH", tip=80, grand=80)]
        rows = compare(our, them, tolerance=TOLERANCE)
        statuses = {r.status for r in rows}
        assert "MISSING_IN_OUTPUT" not in statuses
        assert "MISSING_IN_SUPPER" not in statuses

    def test_dollar_string_in_supper(self):
        our  = [_Row("Grace", grand_total=1234.56)]
        them = [SUPPER_HEADER, _supper_row("Grace", grand=1234.56)]
        rows = compare(our, them, tolerance=TOLERANCE)
        totals = [r for r in rows if r.field_name == "grand_total"]
        assert totals[0].status == "MATCH"


class TestSummaryStats:
    def test_counts(self):
        rows = [
            CompareRow("A", "tip", 100, 100, 0, "MATCH"),
            CompareRow("B", "tip", 100, 50,  50, "DIFF"),
            CompareRow("C", "tip", 0,   50,  -50, "MISSING_IN_OUTPUT"),
        ]
        stats = summary_stats(rows)
        assert stats["MATCH"] == 1
        assert stats["DIFF"] == 1
        assert stats["MISSING_IN_OUTPUT"] == 1
        assert stats.get("MISSING_IN_SUPPER", 0) == 0
