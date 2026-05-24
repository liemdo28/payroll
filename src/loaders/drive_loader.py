"""
Google Drive file loader.

Supports:
  - Listing folder contents
  - Downloading plain CSV / text files
  - Auto-detecting latest timesheet + order-details pair
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import date
from typing import Optional

from src.google_client import api_request

_DRIVE_BASE = "https://www.googleapis.com/drive/v3"


def list_folder(folder_id: str, token: str) -> list[dict]:
    """Return all non-trashed files in a Drive folder, newest-modified first."""
    params = urllib.parse.urlencode({
        "q":        f"'{folder_id}' in parents and trashed = false",
        "orderBy":  "modifiedTime desc",
        "fields":   "files(id,name,modifiedTime,mimeType,size)",
        "pageSize": 100,
    })
    data = api_request("GET", f"{_DRIVE_BASE}/files?{params}", token)
    return data.get("files", [])


def download_text(file_id: str, token: str) -> str:
    """Download a Drive file and return decoded text (UTF-8 with latin-1 fallback)."""
    import urllib.request, urllib.error
    url = f"{_DRIVE_BASE}/files/{file_id}?alt=media"
    import json as _json
    # api_request parses JSON, but we need raw bytes here
    import urllib.request as _req
    request = _req.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with _req.urlopen(request, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Drive download error {exc.code}: {exc.read().decode()}"
        ) from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def find_latest_pair(folder_id: str, token: str) -> tuple[dict, dict]:
    """
    Scan folder and return (timesheet_file, orders_file) — the most recently
    modified CSV matching each pattern.
    """
    files = list_folder(folder_id, token)
    ts  = [f for f in files if re.search(r"timesheet",    f["name"], re.I)]
    ord = [f for f in files if re.search(r"order.?detail", f["name"], re.I)]

    if not ts:
        raise FileNotFoundError(
            f"No timesheet CSV found in Drive folder {folder_id}. "
            "Upload a file whose name contains 'timesheet'."
        )
    if not ord:
        raise FileNotFoundError(
            f"No Order Details CSV found in Drive folder {folder_id}. "
            "Upload a file whose name contains 'OrderDetail'."
        )
    return ts[0], ord[0]


def detect_period_end(orders_file: dict, fallback_dates: list[date]) -> date:
    """
    Extract period-end date from the order-file name
    (pattern: YYYY_MM_DD-YYYY_MM_DD).  Falls back to max(fallback_dates).
    """
    fn = orders_file.get("name", "")
    m  = re.search(
        r"(\d{4})[_\-](\d{2})[_\-](\d{2})[^_\-\d]*(\d{4})[_\-](\d{2})[_\-](\d{2})",
        fn,
    )
    if m:
        return date(int(m[4]), int(m[5]), int(m[6]))
    return max(fallback_dates) if fallback_dates else date.today()
