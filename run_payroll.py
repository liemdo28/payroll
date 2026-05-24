#!/usr/bin/env python3
"""
End-to-end payroll runner for Raw Sushi Bistro.

Workflow:
  1. Connects to Google Drive (same service-account key as Sheets)
  2. Finds the latest timesheet + order-details CSVs in RAW_FOLDER_ID
  3. Downloads them
  4. Runs payroll_processor
  5. Writes local CSVs to ./output/
  6. Uploads results to Google Sheets (PAYROLL_FILE_ID + ADMIN_FILE_ID)

Usage:
    python3 run_payroll.py --key service_account.json
    python3 run_payroll.py --key service_account.json --dry-run
    python3 run_payroll.py --key service_account.json --timesheet FILE --orders FILE
"""

import argparse
import json
import re
import urllib.parse
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

import rsa
import time
import base64

import config as cfg
from payroll_processor import parse_timesheet, run as processor_run, print_summary
from sheets_writer import get_access_token, push_period


# ─────────────────────────────────────────────────────────────────────────────
# Drive API helpers (same service account, Drive scope added)
# ─────────────────────────────────────────────────────────────────────────────

_DRIVE_SCOPE  = "https://www.googleapis.com/auth/drive.readonly"
_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_DRIVE_WRITE_SCOPE = "https://www.googleapis.com/auth/drive"
_TOKEN_URL    = "https://oauth2.googleapis.com/token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def get_drive_token(key_file: str) -> str:
    """Get an OAuth2 token with Drive read + Sheets scopes."""
    with open(key_file) as f:
        sa = json.load(f)

    scopes = " ".join([_DRIVE_SCOPE, _SHEETS_SCOPE])
    now    = int(time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss":   sa["client_email"],
        "scope": scopes,
        "aud":   _TOKEN_URL,
        "iat":   now,
        "exp":   now + 3600,
    }).encode())

    signing_input = f"{header}.{payload}".encode()
    private_key   = rsa.PrivateKey.load_pkcs1_openssl_pem(sa["private_key"].encode())
    signature     = rsa.sign(signing_input, private_key, "SHA-256")
    jwt_token     = f"{header}.{payload}.{_b64url(signature)}"

    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt_token,
    }).encode()
    req = urllib.request.Request(
        _TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def _drive_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Drive API error {e.code}: {e.read().decode()}") from e


def list_folder_files(folder_id: str, token: str, name_contains: str = "") -> list[dict]:
    """Return files in a Drive folder, newest-modified first."""
    q = f"'{folder_id}' in parents and trashed = false"
    if name_contains:
        q += f" and name contains '{name_contains}'"
    params = urllib.parse.urlencode({
        "q":       q,
        "orderBy": "modifiedTime desc",
        "fields":  "files(id,name,modifiedTime,mimeType)",
        "pageSize": 50,
    })
    url  = f"https://www.googleapis.com/drive/v3/files?{params}"
    data = _drive_get(url, token)
    return data.get("files", [])


def download_file(file_id: str, token: str) -> str:
    """Download a Drive file (plain text) and return its content."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            # try UTF-8, fall back to latin-1
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Drive download error {e.code}: {e.read().decode()}") from e


# ─────────────────────────────────────────────────────────────────────────────
# Find latest timesheet + order details in the raw folder
# ─────────────────────────────────────────────────────────────────────────────

def find_latest_csvs(folder_id: str, token: str) -> tuple[dict, dict]:
    """
    Returns (timesheet_file, orders_file) – the most recent pair from
    the raw Drive folder.  Matches by file name patterns.
    """
    all_files = list_folder_files(folder_id, token)
    ts_files  = [f for f in all_files if re.search(r"timesheet",  f["name"], re.I)]
    ord_files = [f for f in all_files if re.search(r"order.?detail", f["name"], re.I)]

    if not ts_files:
        raise FileNotFoundError("No timesheet CSV found in Drive folder.")
    if not ord_files:
        raise FileNotFoundError("No Order Details CSV found in Drive folder.")

    return ts_files[0], ord_files[0]


def _detect_period_end(ord_file: dict, ts_text: str) -> date:
    """Auto-detect period end from order-file name, or fall back to latest shift date."""
    fn = ord_file["name"]
    m  = re.search(r"(\d{4})[_\-](\d{2})[_\-](\d{2})[^_\-\d]*(\d{4})[_\-](\d{2})[_\-](\d{2})", fn)
    if m:
        return date(int(m[4]), int(m[5]), int(m[6]))
    # fall back: max shift date from timesheet
    from payroll_processor import parse_timesheet
    shifts, _ = parse_timesheet(ts_text)
    dates = [s.work_date for s in shifts if s.work_date]
    return max(dates) if dates else date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Raw Sushi Bistro – full payroll pipeline")
    ap.add_argument("--key",        required=True, help="Service-account JSON key file path")
    ap.add_argument("--timesheet",  help="Local timesheet CSV (skips Drive download)")
    ap.add_argument("--orders",     help="Local Order Details CSV (skips Drive download)")
    ap.add_argument("--period-end", help="Period end YYYY-MM-DD (auto-detected if omitted)")
    ap.add_argument("--out-dir",    default="output", help="Directory for local CSV output")
    ap.add_argument("--dry-run",    action="store_true",
                    help="Process locally; print what would be uploaded but do not write to Sheets")
    ap.add_argument("--no-upload",  action="store_true",
                    help="Process and write local CSVs only; skip Sheets upload")
    args = ap.parse_args()

    # ── Step 1: Get input CSVs ────────────────────────────────────────────────
    if args.timesheet and args.orders:
        print("  Using local CSV files.")
        ts_text  = Path(args.timesheet).read_text()
        ord_text = Path(args.orders).read_text()
        ord_name = Path(args.orders).name

        if args.period_end:
            period_end = date.fromisoformat(args.period_end)
        else:
            m = re.search(
                r"(\d{4})[_\-](\d{2})[_\-](\d{2})[^_\-\d]*(\d{4})[_\-](\d{2})[_\-](\d{2})",
                ord_name,
            )
            period_end = (
                date(int(m[4]), int(m[5]), int(m[6])) if m
                else _detect_period_end({"name": ord_name}, ts_text)
            )
    else:
        print("  Fetching latest CSVs from Google Drive…")
        token    = get_drive_token(args.key)
        ts_file, ord_file = find_latest_csvs(cfg.RAW_FOLDER_ID, token)
        print(f"  Timesheet : {ts_file['name']}  (modified {ts_file['modifiedTime'][:10]})")
        print(f"  Orders    : {ord_file['name']}  (modified {ord_file['modifiedTime'][:10]})")

        ts_text  = download_file(ts_file["id"],  token)
        ord_text = download_file(ord_file["id"], token)

        period_end = (
            date.fromisoformat(args.period_end)
            if args.period_end
            else _detect_period_end(ord_file, ts_text)
        )

    print(f"  Period end : {period_end}")

    # ── Step 2: Process ───────────────────────────────────────────────────────
    result = processor_run(ts_text, ord_text, period_end)
    print_summary(result)

    # ── Step 3: Write local CSVs ──────────────────────────────────────────────
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = period_end.strftime("%m-%d")
    (out / f"current_sheet_{tag}.csv").write_text(result["current_csv"])
    (out / f"tip_records_{tag}.csv").write_text(result["tip_records_csv"])
    (out / f"val_summary_{tag}.csv").write_text(result["val_summary_csv"])
    print(f"  Local CSVs written → {out.resolve()}")

    # ── Step 4: Upload to Sheets ──────────────────────────────────────────────
    if args.no_upload:
        print("  Skipping Sheets upload (--no-upload).")
        return

    push_period(result, args.key, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
