#!/usr/bin/env python3
"""
Google Sheets writer for Raw Sushi Bistro payroll.

Uses a service-account JSON key to authenticate, then calls the
Google Sheets API v4 directly (no gspread / google-auth needed).

Usage (from CLI, after running payroll_processor.py):
    python3 sheets_writer.py --key service_account.json \\
        --timesheet FILE --orders FILE [--period-end YYYY-MM-DD]

Or import and call push_period() from your own script.
"""

import base64
import hashlib
import hmac
import json
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any

import rsa


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers – build a service-account JWT and exchange for OAuth2 token
# ─────────────────────────────────────────────────────────────────────────────

_SCOPES = "https://www.googleapis.com/auth/spreadsheets"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def get_access_token(key_file: str) -> str:
    """Load a service-account JSON key and return a short-lived OAuth2 token."""
    with open(key_file) as f:
        sa = json.load(f)

    now = int(time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss":   sa["client_email"],
        "scope": _SCOPES,
        "aud":   _TOKEN_URL,
        "iat":   now,
        "exp":   now + 3600,
    }).encode())

    signing_input = f"{header}.{payload}".encode()
    private_key   = rsa.PrivateKey.load_pkcs1_openssl_pem(
        sa["private_key"].encode()
    )
    signature = rsa.sign(signing_input, private_key, "SHA-256")
    jwt_token = f"{header}.{payload}.{_b64url(signature)}"

    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt_token,
    }).encode()
    req = urllib.request.Request(_TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


# ─────────────────────────────────────────────────────────────────────────────
# Sheets API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sheets_request(method: str, url: str, token: str, body: Any = None) -> Any:
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError(f"Sheets API {method} {url} → {e.code}: {detail}") from e


def get_sheet_metadata(spreadsheet_id: str, token: str) -> dict:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields=sheets.properties"
    return _sheets_request("GET", url, token)


def list_sheet_tabs(spreadsheet_id: str, token: str) -> list[dict]:
    """Returns list of {sheetId, title} for each tab."""
    meta = get_sheet_metadata(spreadsheet_id, token)
    return [
        {"sheetId": s["properties"]["sheetId"], "title": s["properties"]["title"]}
        for s in meta.get("sheets", [])
    ]


def add_sheet_tab(spreadsheet_id: str, tab_name: str, token: str) -> int:
    """Create a new tab with the given name; return its sheetId."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
    body = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
    resp = _sheets_request("POST", url, token, body)
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def delete_sheet_tab(spreadsheet_id: str, sheet_id: int, token: str) -> None:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
    body = {"requests": [{"deleteSheet": {"sheetId": sheet_id}}]}
    _sheets_request("POST", url, token, body)


def clear_range(spreadsheet_id: str, range_: str, token: str) -> None:
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/"
           f"{spreadsheet_id}/values/{urllib.parse.quote(range_)}:clear")
    _sheets_request("POST", url, token, {})


def write_values(
    spreadsheet_id: str,
    range_: str,
    values: list[list],
    token: str,
) -> None:
    """Write a 2D list of values to the given A1 range."""
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/"
           f"{spreadsheet_id}/values/{urllib.parse.quote(range_)}"
           f"?valueInputOption=USER_ENTERED")
    body = {"range": range_, "majorDimension": "ROWS", "values": values}
    _sheets_request("PUT", url, token, body)


def append_values(
    spreadsheet_id: str,
    range_: str,
    values: list[list],
    token: str,
) -> None:
    """Append rows after the last data row in range_."""
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/"
           f"{spreadsheet_id}/values/{urllib.parse.quote(range_)}:append"
           f"?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS")
    body = {"range": range_, "majorDimension": "ROWS", "values": values}
    _sheets_request("POST", url, token, body)


def read_values(spreadsheet_id: str, range_: str, token: str) -> list[list]:
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/"
           f"{spreadsheet_id}/values/{urllib.parse.quote(range_)}")
    resp = _sheets_request("GET", url, token)
    return resp.get("values", [])


# ─────────────────────────────────────────────────────────────────────────────
# CSV → 2-D list conversion
# ─────────────────────────────────────────────────────────────────────────────

import csv, io as _io


def _csv_to_rows(text: str) -> list[list[str]]:
    return list(csv.reader(_io.StringIO(text)))


# ─────────────────────────────────────────────────────────────────────────────
# High-level upload operations
# ─────────────────────────────────────────────────────────────────────────────

import config as cfg
from payroll_processor import (
    EmployeePaySummary, run as processor_run, print_summary,
)
from pathlib import Path


def _super_sheet_rows(super_sheet: list[EmployeePaySummary]) -> list[list]:
    """Convert EmployeePaySummary list → 2-D list for Sheets."""
    def _d(v: float) -> str:
        return f"${v:,.2f}" if v else ""
    rows = [[
        "Search Name", "Other name", "Name",
        "Total hours", "Over (OT)", "Regular",
        "Tip", "Busser/Cashier/Hostess", "Sushi chef",
        "Kitchen", "Bartender", "Total",
    ]]
    for r in super_sheet:
        rows.append([
            r.search_name, r.other_name, r.display_name,
            f"{r.total_hours:.2f}" if r.total_hours else "",
            f"{r.ot_hours:.2f}"    if r.ot_hours    else "",
            f"{r.regular_hours:.2f}" if r.regular_hours else "0.00",
            _d(r.tip), _d(r.busser_cashier), _d(r.sushi_tip),
            _d(r.kitchen_tip), _d(r.bartender_tip), _d(r.grand_total),
        ])
    return rows


def push_period(result: dict, key_file: str, dry_run: bool = False) -> None:
    """
    Write one payroll period's data to Google Sheets.

    Writes to two files:
      PAYROLL_FILE_ID  – new tab named by period-end date (e.g. "05-10")
      ADMIN_FILE_ID    – "Sheet Supper" tab updated with new Super Sheet rows

    Args:
        result:   return value of payroll_processor.run(...)
        key_file: path to service-account JSON key
        dry_run:  if True, print what would be written without calling the API
    """
    period_end: date = result["period_end"]
    tab_name = period_end.strftime("%m-%d")

    print(f"\n{'─'*60}")
    print(f"  Uploading period  {result['period_start']}  →  {period_end}")
    print(f"  Tab name: '{tab_name}'")
    print(f"{'─'*60}\n")

    current_rows   = _csv_to_rows(result["current_csv"])
    tip_rec_rows   = _csv_to_rows(result["tip_records_csv"])
    val_sum_rows   = _csv_to_rows(result["val_summary_csv"])
    super_rows     = _super_sheet_rows(result["super_sheet"])

    if dry_run:
        print(f"[dry-run] Would write {len(current_rows)} rows to Payroll tab '{tab_name}'")
        print(f"[dry-run] Would write {len(tip_rec_rows)} tip-record rows to Admin tab 'Tip Records'")
        print(f"[dry-run] Would update Admin 'Sheet Supper' with {len(super_rows)} rows")
        return

    token = get_access_token(key_file)
    print("  ✓ OAuth2 token obtained")

    # ── Payroll file: new period tab ──────────────────────────────────────────
    existing = list_sheet_tabs(cfg.PAYROLL_FILE_ID, token)
    existing_titles = {t["title"]: t["sheetId"] for t in existing}

    if tab_name in existing_titles:
        print(f"  Tab '{tab_name}' exists – clearing and overwriting")
        clear_range(cfg.PAYROLL_FILE_ID, f"'{tab_name}'!A1:Z2000", token)
        sheet_id = existing_titles[tab_name]
    else:
        sheet_id = add_sheet_tab(cfg.PAYROLL_FILE_ID, tab_name, token)
        print(f"  ✓ Created new tab '{tab_name}' (sheetId={sheet_id})")

    write_values(cfg.PAYROLL_FILE_ID, f"'{tab_name}'!A1", current_rows, token)
    print(f"  ✓ Wrote {len(current_rows)} rows to Payroll > '{tab_name}'")

    # ── Admin file: Tip Records tab ───────────────────────────────────────────
    admin_tabs = {t["title"]: t["sheetId"] for t in list_sheet_tabs(cfg.ADMIN_FILE_ID, token)}

    TIP_TAB = "Tip Records"
    if TIP_TAB not in admin_tabs:
        add_sheet_tab(cfg.ADMIN_FILE_ID, TIP_TAB, token)
        print(f"  ✓ Created Admin tab '{TIP_TAB}'")

    # Find last row to append after existing records (keep history)
    existing_tip = read_values(cfg.ADMIN_FILE_ID, f"'{TIP_TAB}'!A:A", token)
    start_row = len(existing_tip) + 1

    # Write period header then rows
    header_row = [[f"=== Period {tab_name} ==="]]
    append_values(cfg.ADMIN_FILE_ID, f"'{TIP_TAB}'!A{start_row}", header_row, token)
    append_values(cfg.ADMIN_FILE_ID, f"'{TIP_TAB}'!A{start_row+1}", tip_rec_rows, token)
    print(f"  ✓ Appended {len(tip_rec_rows)} rows to Admin > '{TIP_TAB}'")

    # ── Admin file: Sheet Supper tab ──────────────────────────────────────────
    SUPER_TAB = "Sheet Supper"
    if SUPER_TAB not in admin_tabs:
        add_sheet_tab(cfg.ADMIN_FILE_ID, SUPER_TAB, token)
        print(f"  ✓ Created Admin tab '{SUPER_TAB}'")

    # Append this period's super sheet block
    existing_super = read_values(cfg.ADMIN_FILE_ID, f"'{SUPER_TAB}'!A:A", token)
    super_start    = len(existing_super) + 1

    period_header = [[f"Period: {result['period_start']} – {period_end}"]]
    append_values(cfg.ADMIN_FILE_ID, f"'{SUPER_TAB}'!A{super_start}", period_header, token)
    append_values(cfg.ADMIN_FILE_ID, f"'{SUPER_TAB}'!A{super_start+1}", super_rows, token)
    print(f"  ✓ Appended super sheet ({len(super_rows)} rows) to Admin > '{SUPER_TAB}'")

    print(f"\n  Done. Payroll tab '{tab_name}' is live in Google Sheets.\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse, sys

    ap = argparse.ArgumentParser(description="Upload payroll period to Google Sheets")
    ap.add_argument("--key",        required=True, help="Service-account JSON key file")
    ap.add_argument("--timesheet",  required=True, help="Toast timesheet CSV path")
    ap.add_argument("--orders",     required=True, help="Order Details CSV path")
    ap.add_argument("--period-end", help="Period end date YYYY-MM-DD (auto-detected if omitted)")
    ap.add_argument("--dry-run",    action="store_true", help="Print what would be uploaded, don't write")
    ap.add_argument("--out-dir",    default="output", help="Local output directory for CSV files")
    args = ap.parse_args()

    ts_text  = Path(args.timesheet).read_text()
    ord_text = Path(args.orders).read_text()

    if args.period_end:
        from datetime import date
        period_end = date.fromisoformat(args.period_end)
    else:
        import re
        fn = Path(args.orders).name
        m  = re.search(r"(\d{4})[_\-](\d{2})[_\-](\d{2})[^_\-\d]*(\d{4})[_\-](\d{2})[_\-](\d{2})", fn)
        if m:
            period_end = date(int(m[4]), int(m[5]), int(m[6]))
        else:
            from payroll_processor import parse_timesheet
            tmp_shifts, _ = parse_timesheet(ts_text)
            dates = [s.work_date for s in tmp_shifts if s.work_date]
            period_end = max(dates) if dates else date.today()

    result = processor_run(ts_text, ord_text, period_end)
    print_summary(result)

    # Write local CSVs
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = period_end.strftime("%m-%d")
    (out / f"current_sheet_{tag}.csv").write_text(result["current_csv"])
    (out / f"tip_records_{tag}.csv").write_text(result["tip_records_csv"])
    (out / f"val_summary_{tag}.csv").write_text(result["val_summary_csv"])
    print(f"  Local CSVs written → {out.resolve()}")

    # Upload to Sheets
    push_period(result, args.key, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
