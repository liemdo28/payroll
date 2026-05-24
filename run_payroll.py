#!/usr/bin/env python3
"""
Raw Sushi Bistro – Full Payroll Pipeline
=========================================

Usage (with .env configured):
    python3 run_payroll.py

Usage (explicit arguments):
    python3 run_payroll.py \\
        --source-file-1 <TIMESHEET_FILE_ID> \\
        --source-file-2 <ORDERS_FILE_ID> \\
        --supper-sheet  <SUPPER_SHEET_ID> \\
        --output-sheet  <OUTPUT_SHEET_ID>

    # Local CSV files (skip Drive download):
    python3 run_payroll.py \\
        --timesheet path/to/timesheet.csv \\
        --orders    path/to/orders.csv \\
        --no-upload

Expected terminal output:
    Loaded source file 1: X rows
    Loaded source file 2: Y rows
    Calculated payroll: Z employees
    Compared with Supper: A match, B diff, C missing
    Output written to: <Google Sheet URL>
"""

# ── Load .env before importing config ────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import config as cfg
from src.google_client import get_access_token
from src.loaders.drive_loader import download_text, find_latest_pair, detect_period_end
from src.loaders.sheets_loader import read_tab
from src.payroll.processor import process
from src.compare.supper_compare import compare as do_compare, summary_stats
from src.writers.sheets_writer import write_all
from src.payroll.validator import Validator


def _detect_period_end_from_local(orders_path: str, ts_text: str) -> date:
    fn = Path(orders_path).name
    m  = re.search(
        r"(\d{4})[_\-](\d{2})[_\-](\d{2})[^_\-\d]*(\d{4})[_\-](\d{2})[_\-](\d{2})",
        fn,
    )
    if m:
        return date(int(m[4]), int(m[5]), int(m[6]))
    from payroll_processor import parse_timesheet
    shifts, _ = parse_timesheet(ts_text)
    dates = [s.work_date for s in shifts if s.work_date]
    return max(dates) if dates else date.today()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Raw Sushi Bistro – Payroll Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Source files (Drive file IDs or auto-discover from folder)
    ap.add_argument("--source-file-1",
                    default=os.getenv("SOURCE_FILE_1_ID", ""),
                    help="Drive file ID for timesheet CSV (env: SOURCE_FILE_1_ID)")
    ap.add_argument("--source-file-2",
                    default=os.getenv("SOURCE_FILE_2_ID", ""),
                    help="Drive file ID for order details CSV (env: SOURCE_FILE_2_ID)")

    # Local override (skips Drive download)
    ap.add_argument("--timesheet", help="Local timesheet CSV path")
    ap.add_argument("--orders",    help="Local order details CSV path")

    # Google Sheets targets
    ap.add_argument("--supper-sheet",
                    default=os.getenv("SUPPER_SHEET_ID", cfg.ADMIN_FILE_ID),
                    help="Spreadsheet ID of Sheet Supper (env: SUPPER_SHEET_ID)")
    ap.add_argument("--output-sheet",
                    default=os.getenv("OUTPUT_SHEET_ID", cfg.PAYROLL_FILE_ID),
                    help="Spreadsheet ID for output (env: OUTPUT_SHEET_ID)")

    ap.add_argument("--supper-tab",
                    default=os.getenv("SUPPER_TAB_NAME", "Sheet Supper"),
                    help="Tab name inside the Supper spreadsheet")
    ap.add_argument("--period-end",
                    help="Period end date YYYY-MM-DD (auto-detected if omitted)")
    ap.add_argument("--key",
                    default=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", cfg.SERVICE_ACCOUNT_KEY),
                    help="Service-account JSON key path")
    ap.add_argument("--out-dir",   default="output",
                    help="Directory for local CSV output (default: output/)")
    ap.add_argument("--dry-run",   action="store_true",
                    help="Compute and compare; skip writing to Sheets")
    ap.add_argument("--no-upload", action="store_true",
                    help="Compute locally; write local CSVs but skip Sheets upload")
    ap.add_argument("--no-compare", action="store_true",
                    help="Skip Sheet Supper comparison step")

    args = ap.parse_args()

    # ── Validate key early ────────────────────────────────────────────────────
    uploading = not args.no_upload and not args.dry_run
    if uploading and not Path(args.key).exists():
        print(f"ERROR: Service-account key not found: {args.key}")
        print("  Set GOOGLE_SERVICE_ACCOUNT_FILE in .env, or use --no-upload to skip.")
        sys.exit(1)

    # ── Step 1: Load source CSVs ──────────────────────────────────────────────
    validator = Validator()

    if args.timesheet and args.orders:
        print("  Loading local CSV files…")
        ts_text  = Path(args.timesheet).read_text(encoding="utf-8", errors="replace")
        ord_text = Path(args.orders).read_text(encoding="utf-8", errors="replace")
        file_1_id = args.source_file_1 or Path(args.timesheet).name
        file_2_id = args.source_file_2 or Path(args.orders).name

        if args.period_end:
            period_end = date.fromisoformat(args.period_end)
        else:
            period_end = _detect_period_end_from_local(args.orders, ts_text)

    elif args.source_file_1 and args.source_file_2:
        print("  Fetching source files from Google Drive by ID…")
        token = get_access_token(args.key)
        ts_text  = download_text(args.source_file_1, token)
        ord_text = download_text(args.source_file_2, token)
        file_1_id = args.source_file_1
        file_2_id = args.source_file_2
        period_end = (
            date.fromisoformat(args.period_end)
            if args.period_end
            else detect_period_end({"name": ""}, [])
        )

    else:
        print("  Auto-discovering latest CSVs from Drive folder…")
        token    = get_access_token(args.key)
        ts_meta, ord_meta = find_latest_pair(cfg.RAW_FOLDER_ID, token)
        print(f"  Timesheet : {ts_meta['name']}  (modified {ts_meta['modifiedTime'][:10]})")
        print(f"  Orders    : {ord_meta['name']}  (modified {ord_meta['modifiedTime'][:10]})")
        ts_text  = download_text(ts_meta["id"],  token)
        ord_text = download_text(ord_meta["id"], token)
        file_1_id = ts_meta["id"]
        file_2_id = ord_meta["id"]

        from payroll_processor import parse_timesheet
        shifts_tmp, _ = parse_timesheet(ts_text)
        dates = [s.work_date for s in shifts_tmp if s.work_date]
        period_end = (
            date.fromisoformat(args.period_end) if args.period_end
            else detect_period_end(ord_meta, dates)
        )

    ts_row_count  = ts_text.count("\n")
    ord_row_count = ord_text.count("\n")
    print(f"  Loaded source file 1: {ts_row_count} rows")
    print(f"  Loaded source file 2: {ord_row_count} rows")
    print(f"  Period end: {period_end}")

    # ── Step 2: Process payroll ───────────────────────────────────────────────
    print("\n  Running payroll calculation…")
    result = process(ts_text, ord_text, period_end, validator=validator)
    n_emp  = len(result.super_sheet)
    print(f"  Calculated payroll: {n_emp} employees")
    _print_pool_summary(result)

    if validator.errors:
        print(f"\n  Validation: {validator.summary()}")

    # ── Step 3: Write local CSVs ──────────────────────────────────────────────
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = result.period_end.strftime("%m-%d")
    (out / f"current_sheet_{tag}.csv").write_text(result.current_csv)
    (out / f"tip_records_{tag}.csv").write_text(result.tip_records_csv)
    (out / f"val_summary_{tag}.csv").write_text(result.val_summary_csv)
    print(f"\n  Local CSVs written → {out.resolve()}")

    # ── Step 4: Compare with Sheet Supper ─────────────────────────────────────
    compare_rows = []
    if not args.no_compare and (uploading or args.dry_run):
        print(f"\n  Reading Sheet Supper from spreadsheet {args.supper_sheet} …")
        try:
            token_cmp = get_access_token(args.key)
            supper_raw = read_tab(args.supper_sheet, args.supper_tab, token_cmp)
            compare_rows = do_compare(result.super_sheet, supper_raw)
            stats = summary_stats(compare_rows)
            match   = stats.get("MATCH", 0)
            diff    = stats.get("DIFF", 0)
            missing = stats.get("MISSING_IN_OUTPUT", 0) + stats.get("MISSING_IN_SUPPER", 0)
            print(f"  Compared with Supper: {match} match, {diff} diff, {missing} missing")
            if diff:
                _print_diffs(compare_rows)
        except Exception as exc:
            print(f"  WARNING: Could not read Sheet Supper: {exc}")
            print("  Skipping comparison. Set SUPPER_SHEET_ID in .env to enable.")

    # ── Step 5: Upload to Sheets ──────────────────────────────────────────────
    if args.no_upload or args.dry_run:
        if args.dry_run:
            print("\n  [dry-run] Skipping Sheets write.")
        return

    print(f"\n  Writing output to spreadsheet {args.output_sheet} …")
    token_write = get_access_token(args.key)
    url = write_all(
        result, compare_rows, args.output_sheet, token_write,
        supper_sheet_id=args.supper_sheet,
        source_file_1_id=file_1_id,
        source_file_2_id=file_2_id,
    )
    print(f"  Output written to: {url}")


# ── Helper print functions ────────────────────────────────────────────────────

def _print_pool_summary(result) -> None:
    print(f"\n  {'='*55}")
    print(f"  Payroll  {result.period_start}  →  {result.period_end}")
    print(f"  {'='*55}")
    print(f"  FOH Card Tips   : ${result.foh_card_tips:>9,.2f}")
    print(f"  T30 Kitchen     : ${result.T30:>9,.2f}")
    print(f"  Kitchen Pool E89: ${result.kitchen_pool_total:>9,.2f}")
    print(f"  Sushi Pool F3   : ${result.sushi_pool_total:>9,.2f}")
    print(f"  Total VAL pool  : ${result.foh_val + result.total_server_val:>9,.2f}")
    print()
    print(f"  {'Name':<28} {'Hrs':>6} {'OT':>5} {'Tip':>9} {'Total':>9}")
    print(f"  {'-'*59}")
    for row in result.super_sheet:
        if row.total_hours or row.grand_total:
            print(f"  {row.display_name:<28} {row.total_hours:>6.2f} "
                  f"{row.ot_hours:>5.2f} {row.tip:>9.2f} {row.grand_total:>9.2f}")


def _print_diffs(compare_rows) -> None:
    diffs = [r for r in compare_rows if r.status == "DIFF"][:10]
    print(f"\n  Top diffs (first {len(diffs)}):")
    print(f"  {'Employee':<24} {'Field':<18} {'Ours':>9} {'Supper':>9} {'Diff':>8}")
    print(f"  {'-'*72}")
    for r in diffs:
        print(f"  {r.employee_name:<24} {r.field_name:<18} "
              f"{r.our_value:>9.2f} {r.supper_value:>9.2f} {r.diff:>+8.2f}")


if __name__ == "__main__":
    main()
