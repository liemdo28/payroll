"""
End-to-end pipeline tests using the real test CSV files.

These tests exercise the full parse → compute → compare chain
without hitting any external API.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

_TS_FILE  = Path("/tmp/timesheet.csv")
_ORD_FILE = Path("/tmp/orders.csv")

# Skip entire module if test data files are absent
pytestmark = pytest.mark.skipif(
    not (_TS_FILE.exists() and _ORD_FILE.exists()),
    reason="Test CSV files not found at /tmp/timesheet.csv and /tmp/orders.csv",
)


@pytest.fixture(scope="module")
def payroll_result():
    from src.payroll.processor import process
    ts_text  = _TS_FILE.read_text(encoding="utf-8", errors="replace")
    ord_text = _ORD_FILE.read_text(encoding="utf-8", errors="replace")
    return process(ts_text, ord_text)


class TestParsing:
    def test_shifts_parsed(self, payroll_result):
        assert len(payroll_result.shifts) > 0

    def test_tip_records_parsed(self, payroll_result):
        assert len(payroll_result.tip_records) > 0

    def test_super_sheet_not_empty(self, payroll_result):
        assert len(payroll_result.super_sheet) > 0

    def test_no_critical_errors(self, payroll_result):
        assert not payroll_result.validator.has_errors


class TestNameNormalization:
    def test_ali_arevalo_unified(self, payroll_result):
        """Ali Arevalo (timesheet) and Ali Arevalov (orders) must merge."""
        names = [row.display_name for row in payroll_result.super_sheet]
        assert "Ali Arevalo" in names
        assert "Ali Arevalov" not in names

    def test_no_duplicate_employees(self, payroll_result):
        names = [row.search_name.strip().lower() for row in payroll_result.super_sheet]
        assert len(names) == len(set(names)), f"Duplicate employees: {names}"


class TestPoolCalculations:
    def test_foh_card_tips_positive(self, payroll_result):
        assert payroll_result.foh_card_tips > 0

    def test_t30_equals_foh_two_thirds_minus_cashier(self, payroll_result):
        from src.payroll.rules import t30
        import config as cfg
        expected = t30(payroll_result.foh_card_tips,
                       sum(r.cashier_tip for r in payroll_result.tip_records
                           if r.job == "Cashier"),
                       cfg.CASHIER_FOH_PCT)
        assert abs(payroll_result.T30 - expected) < 0.02

    def test_total_val_pool(self, payroll_result):
        """Total VAL = server VAL + FOH VAL."""
        total = payroll_result.total_server_val + payroll_result.foh_val
        assert total > 0

    def test_kitchen_tips_distributed(self, payroll_result):
        kitchen = sum(payroll_result.kitchen_tips.values())
        # With M22=0, kitchen pool = T30; allow rounding
        assert abs(kitchen - payroll_result.kitchen_pool_total) < 0.10


class TestOutputFormat:
    def test_current_csv_non_empty(self, payroll_result):
        assert len(payroll_result.current_csv) > 100

    def test_tip_records_csv_has_header(self, payroll_result):
        first_line = payroll_result.tip_records_csv.splitlines()[0]
        assert "Date" in first_line or "date" in first_line.lower()

    def test_super_sheet_rows_have_12_columns(self, payroll_result):
        rows = payroll_result.super_sheet_as_rows()
        assert len(rows) > 1
        assert len(rows[0]) == 12   # header has 12 columns

    def test_period_dates_detected(self, payroll_result):
        assert payroll_result.period_start is not None
        assert payroll_result.period_end   is not None
        assert payroll_result.period_start <= payroll_result.period_end


class TestCompareLogic:
    def test_compare_with_self_all_match(self, payroll_result):
        """Comparing our output against itself should produce all MATCH rows."""
        from src.compare.supper_compare import compare
        # Build a fake Supper using our own super_sheet rows
        rows = payroll_result.super_sheet_as_rows()
        result = compare(payroll_result.super_sheet, rows)
        diffs = [r for r in result if r.status == "DIFF"]
        assert len(diffs) == 0, f"Self-compare produced DIFFs: {diffs[:3]}"
