"""
Google Sheets output writer.

Creates / updates the following tabs in OUTPUT_SHEET_ID:
  - Payroll Output      Super sheet (one row per employee)
  - Compare With Supper Field-by-field diff vs. Sheet Supper
  - Raw Source 1        Raw timesheet CSV content
  - Raw Source 2        Raw order details CSV content
  - Errors              Validation errors and warnings
  - Run Metadata        Run timestamp, file IDs, summary stats
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
from datetime import datetime, timezone

import config as cfg
from src.loaders.sheets_loader import (
    ensure_tab, clear_tab, write_values, format_header_row, list_tabs,
)
from src.payroll.processor import PayrollResult
from src.compare.supper_compare import CompareRow, summary_stats


# ── Tab names (configurable via env) ─────────────────────────────────────────

TAB_PAYROLL    = os.getenv("OUTPUT_TAB_NAME",  "Payroll Output")
TAB_COMPARE    = os.getenv("COMPARE_TAB_NAME", "Compare With Supper")
TAB_RAW1       = "Raw Source 1"
TAB_RAW2       = "Raw Source 2"
TAB_ERRORS     = "Errors"
TAB_METADATA   = "Run Metadata"


def _csv_to_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def write_all(
    result: PayrollResult,
    compare_rows: list[CompareRow],
    spreadsheet_id: str,
    token: str,
    supper_sheet_id: str = "",
    source_file_1_id: str = "",
    source_file_2_id: str = "",
) -> str:
    """
    Write all output tabs.  Returns the spreadsheet URL.
    """
    stats = summary_stats(compare_rows)
    total_employees = len(result.super_sheet)

    _write_tab(spreadsheet_id, TAB_PAYROLL, result.super_sheet_as_rows(),
               token, bold_header=True)

    _write_tab(spreadsheet_id, TAB_COMPARE, _compare_rows_with_summary(compare_rows, stats),
               token, bold_header=True)

    # Raw source tabs — parse CSV back to rows for clean display
    raw1_rows = _csv_to_rows(result.current_csv)
    raw2_rows = _csv_to_rows(result.tip_records_csv)
    _write_tab(spreadsheet_id, TAB_RAW1, raw1_rows, token)
    _write_tab(spreadsheet_id, TAB_RAW2, raw2_rows, token)

    _write_tab(spreadsheet_id, TAB_ERRORS, result.validator.as_rows(), token, bold_header=True)

    metadata = _build_metadata(
        result, stats, total_employees,
        supper_sheet_id, source_file_1_id, source_file_2_id,
    )
    _write_tab(spreadsheet_id, TAB_METADATA, metadata, token)

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def _write_tab(
    spreadsheet_id: str,
    tab_name: str,
    rows: list[list],
    token: str,
    bold_header: bool = False,
) -> None:
    """Ensure tab exists, clear it, write rows, optionally bold header."""
    sheet_id = ensure_tab(spreadsheet_id, tab_name, token)
    clear_tab(spreadsheet_id, tab_name, token)
    if not rows:
        return
    range_ = f"'{tab_name}'!A1"
    write_values(spreadsheet_id, range_, rows, token)
    if bold_header and rows:
        try:
            format_header_row(spreadsheet_id, sheet_id, token, num_cols=len(rows[0]))
        except Exception:
            pass   # formatting is cosmetic; don't fail the write


def _compare_rows_with_summary(
    rows: list[CompareRow],
    stats: dict,
) -> list[list]:
    from src.compare.supper_compare import as_sheet_rows
    header_rows = as_sheet_rows(rows)
    summary = [
        [],
        ["Summary", "", "", "", "", "", ""],
        ["MATCH",              stats.get("MATCH", 0), "", "", "", "", ""],
        ["DIFF",               stats.get("DIFF", 0),  "", "", "", "", ""],
        ["MISSING_IN_OUTPUT",  stats.get("MISSING_IN_OUTPUT", 0), "", "", "", "", ""],
        ["MISSING_IN_SUPPER",  stats.get("MISSING_IN_SUPPER", 0), "", "", "", "", ""],
    ]
    return header_rows + summary


def _build_metadata(
    result: PayrollResult,
    stats: dict,
    total_employees: int,
    supper_sheet_id: str,
    source_file_1_id: str,
    source_file_2_id: str,
) -> list[list]:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return [
        ["Key", "Value"],
        ["run_at",            now_str],
        ["period_start",      str(result.period_start)],
        ["period_end",        str(result.period_end)],
        ["source_file_1_id",  source_file_1_id or cfg.RAW_FOLDER_ID],
        ["source_file_2_id",  source_file_2_id],
        ["supper_sheet_id",   supper_sheet_id or cfg.ADMIN_FILE_ID],
        ["output_sheet_id",   cfg.PAYROLL_FILE_ID],
        ["total_employees",   total_employees],
        ["compare_match",     stats.get("MATCH", 0)],
        ["compare_diff",      stats.get("DIFF", 0)],
        ["compare_missing_output", stats.get("MISSING_IN_OUTPUT", 0)],
        ["compare_missing_supper", stats.get("MISSING_IN_SUPPER", 0)],
        ["validation_errors", result.validator.summary()],
        ["foh_card_tips",     f"${result.foh_card_tips:,.2f}"],
        ["t30_kitchen",       f"${result.T30:,.2f}"],
        ["kitchen_pool_e89",  f"${result.kitchen_pool_total:,.2f}"],
        ["sushi_pool_f3",     f"${result.sushi_pool_total:,.2f}"],
        ["total_val_pool",    f"${result.foh_val + result.total_server_val:,.2f}"],
        ["git_commit",        _git_hash()],
        ["KITCHEN_SERVER_VAL_FRACTION", cfg.KITCHEN_SERVER_VAL_FRACTION],
        ["SUSHI_VAL_FRACTION",           cfg.SUSHI_VAL_FRACTION],
    ]
