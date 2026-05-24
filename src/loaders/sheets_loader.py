"""
Google Sheets reader.
"""

from __future__ import annotations

import urllib.parse
from src.google_client import api_request

_SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def read_range(spreadsheet_id: str, range_: str, token: str) -> list[list[str]]:
    """Return values[[row][col]] for the given A1 range."""
    url = (f"{_SHEETS_BASE}/{spreadsheet_id}/values/"
           f"{urllib.parse.quote(range_)}")
    resp = api_request("GET", url, token)
    return resp.get("values", [])


def read_tab(spreadsheet_id: str, tab_name: str, token: str,
             max_col: str = "Z", max_row: int = 2000) -> list[list[str]]:
    """Read an entire tab (up to max_col / max_row)."""
    return read_range(spreadsheet_id, f"'{tab_name}'!A1:{max_col}{max_row}", token)


def list_tabs(spreadsheet_id: str, token: str) -> list[dict]:
    """Return [{sheetId, title}] for each tab in the spreadsheet."""
    url  = f"{_SHEETS_BASE}/{spreadsheet_id}?fields=sheets.properties"
    resp = api_request("GET", url, token)
    return [
        {"sheetId": s["properties"]["sheetId"], "title": s["properties"]["title"]}
        for s in resp.get("sheets", [])
    ]


def add_tab(spreadsheet_id: str, tab_name: str, token: str) -> int:
    """Create a new blank tab and return its sheetId."""
    url  = f"{_SHEETS_BASE}/{spreadsheet_id}:batchUpdate"
    resp = api_request("POST", url, token,
                       {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]})
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def ensure_tab(spreadsheet_id: str, tab_name: str, token: str) -> int:
    """Return existing sheetId or create the tab and return the new id."""
    existing = {t["title"]: t["sheetId"] for t in list_tabs(spreadsheet_id, token)}
    if tab_name in existing:
        return existing[tab_name]
    return add_tab(spreadsheet_id, tab_name, token)


def clear_tab(spreadsheet_id: str, tab_name: str, token: str) -> None:
    url = (f"{_SHEETS_BASE}/{spreadsheet_id}/values/"
           f"{urllib.parse.quote(repr(tab_name)+'!A1:Z2000')}:clear")
    # Use a safe range string
    safe = urllib.parse.quote(f"'{tab_name}'!A1:Z2000")
    api_request("POST", f"{_SHEETS_BASE}/{spreadsheet_id}/values/{safe}:clear", token, {})


def write_values(spreadsheet_id: str, range_: str, values: list[list],
                 token: str) -> None:
    """Write 2-D list to the range (USER_ENTERED input)."""
    url = (f"{_SHEETS_BASE}/{spreadsheet_id}/values/"
           f"{urllib.parse.quote(range_)}?valueInputOption=USER_ENTERED")
    body = {"range": range_, "majorDimension": "ROWS", "values": values}
    api_request("PUT", url, token, body)


def format_header_row(spreadsheet_id: str, sheet_id: int,
                      token: str, num_cols: int = 12) -> None:
    """Bold the first row and freeze it."""
    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                               "backgroundColor": {"red": 0.22, "green": 0.42, "blue": 0.64}}},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    url = f"{_SHEETS_BASE}/{spreadsheet_id}:batchUpdate"
    api_request("POST", url, token, {"requests": requests})
