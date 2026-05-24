"""
Comparator: our computed Payroll Output vs. the reference Sheet Supper.

Each row in Sheet Supper is matched to our super_sheet by normalized name.
Every numeric column is compared; results carry MATCH / DIFF / MISSING_* status.

Tolerance: abs(our_value - supper_value) <= TOLERANCE  →  MATCH
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.payroll.rules import parse_dollar

TOLERANCE = 1.0   # $1 tolerance

Status = Literal["MATCH", "DIFF", "MISSING_IN_OUTPUT", "MISSING_IN_SUPPER"]

# Columns we compare (header text → index offset from "Name" column)
# Matches our gen_current_sheet_csv / super_sheet_as_rows header:
#   Search Name(0) | Other name(1) | Name(2) | Total hours(3) | Over(4) |
#   Regular(5) | Tip(6) | Busser/Cashier(7) | Sushi(8) | Kitchen(9) |
#   Bartender(10) | Total(11)
COMPARE_COLS = {
    "total_hours":    3,
    "ot_hours":       4,
    "tip":            6,
    "busser_cashier": 7,
    "sushi_tip":      8,
    "kitchen_tip":    9,
    "bartender_tip":  10,
    "grand_total":    11,
}


@dataclass
class CompareRow:
    employee_name: str
    field_name: str
    our_value: float
    supper_value: float
    diff: float
    status: Status
    note: str = ""

    def as_row(self) -> list:
        return [
            self.employee_name,
            self.field_name,
            f"${self.our_value:,.2f}",
            f"${self.supper_value:,.2f}",
            f"${self.diff:+,.2f}",
            self.status,
            self.note,
        ]


def _normalize_name(name: str) -> str:
    """Lower-case, strip extra spaces, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _parse_row_as_dict(row: list[str], header_map: dict[str, int]) -> dict[str, float]:
    """Extract numeric fields from a sheet row using header_map."""
    result = {}
    for field, idx in header_map.items():
        raw = row[idx] if idx < len(row) else ""
        result[field] = parse_dollar(raw)
    return result


def parse_supper_rows(rows: list[list[str]]) -> dict[str, dict[str, float]]:
    """
    Parse Sheet Supper into {normalized_name: {field: value}}.

    The sheet may have multiple header rows (one per period block) and
    blank separators — we skip those and read only employee data rows.
    """
    result: dict[str, dict[str, float]] = {}
    active_col_map: dict[str, int] | None = None

    for row in rows:
        if not any(c.strip() for c in row):
            continue

        first = row[0].strip() if row else ""

        # Detect header row by "Search Name" or "Name" in first columns
        lower_row = [c.strip().lower() for c in row[:5]]
        if "search name" in lower_row or ("name" in lower_row and "total" in [c.strip().lower() for c in row]):
            # Build column index map
            active_col_map = {}
            for i, cell in enumerate(row):
                cl = cell.strip().lower()
                if cl == "total":
                    active_col_map["grand_total"] = i
                elif "total" in cl and "hour" in cl:
                    active_col_map["total_hours"] = i
                elif "over" in cl or cl in ("ot", "o.t."):
                    active_col_map["ot_hours"] = i
                elif cl == "tip":
                    active_col_map["tip"] = i
                elif "busser" in cl or "cashier" in cl or "hostess" in cl:
                    active_col_map["busser_cashier"] = i
                elif "sushi" in cl:
                    active_col_map["sushi_tip"] = i
                elif "kitchen" in cl:
                    active_col_map["kitchen_tip"] = i
                elif "bartender" in cl:
                    active_col_map["bartender_tip"] = i
            continue

        if active_col_map is None:
            continue

        # Skip period-header rows (e.g. "Period: 04/27/2026 – 05/10/2026")
        if first.startswith("Period") or first.startswith("==="):
            continue

        # Employee row: must have a name in col 0 or 2
        name = ""
        if len(row) > 2 and row[2].strip():
            name = row[2].strip()
        elif first:
            name = first

        if not name or not any(c.strip() for c in row[3:]):
            continue

        normalized = _normalize_name(name)
        values = _parse_row_as_dict(row, active_col_map)

        # Merge (a person may appear in multiple period blocks; keep latest)
        if normalized in result:
            # Sum across periods if same employee appears multiple times
            for k, v in values.items():
                result[normalized][k] = result[normalized].get(k, 0.0) + v
        else:
            result[normalized] = values

    return result


def compare(
    our_super_sheet: list,    # list[EmployeePaySummary]
    supper_rows: list[list[str]],
    tolerance: float = TOLERANCE,
) -> list[CompareRow]:
    """
    Compare our computed super_sheet against Sheet Supper rows.

    Returns a list of CompareRow — one per (employee, field) combination.
    """
    supper = parse_supper_rows(supper_rows)

    our_lookup: dict[str, object] = {}
    for row in our_super_sheet:
        key = _normalize_name(row.display_name or row.search_name)
        our_lookup[key] = row

    results: list[CompareRow] = []

    all_names = set(our_lookup) | set(supper)

    for norm_name in sorted(all_names):
        our  = our_lookup.get(norm_name)
        them = supper.get(norm_name)

        display = (our.display_name if our else None) or norm_name.title()

        if our is None:
            # In Supper but not in our output
            for field in COMPARE_COLS:
                sv = (them or {}).get(field, 0.0)
                results.append(CompareRow(
                    employee_name=display, field_name=field,
                    our_value=0.0, supper_value=sv,
                    diff=-sv, status="MISSING_IN_OUTPUT",
                    note="Employee in Sheet Supper but not computed",
                ))
            continue

        if them is None:
            # In our output but not in Supper — may be new employee
            for field in COMPARE_COLS:
                ov = getattr(our, field, 0.0)
                if ov:
                    results.append(CompareRow(
                        employee_name=display, field_name=field,
                        our_value=ov, supper_value=0.0,
                        diff=ov, status="MISSING_IN_SUPPER",
                        note="Employee computed but not in Sheet Supper",
                    ))
            continue

        # Both present — compare field by field
        field_map = {
            "total_hours":    "total_hours",
            "ot_hours":       "ot_hours",
            "tip":            "tip",
            "busser_cashier": "busser_cashier",
            "sushi_tip":      "sushi_tip",
            "kitchen_tip":    "kitchen_tip",
            "bartender_tip":  "bartender_tip",
            "grand_total":    "grand_total",
        }
        for field, attr in field_map.items():
            ov = round(getattr(our, attr, 0.0), 2)
            sv = round(them.get(field, 0.0), 2)
            diff = round(ov - sv, 2)
            if abs(diff) <= tolerance:
                status: Status = "MATCH"
            else:
                status = "DIFF"
            results.append(CompareRow(
                employee_name=display,
                field_name=field,
                our_value=ov,
                supper_value=sv,
                diff=diff,
                status=status,
            ))

    return results


def summary_stats(rows: list[CompareRow]) -> dict:
    """Count MATCH / DIFF / MISSING_* rows."""
    counts: dict[str, int] = {"MATCH": 0, "DIFF": 0,
                               "MISSING_IN_OUTPUT": 0, "MISSING_IN_SUPPER": 0}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def as_sheet_rows(rows: list[CompareRow]) -> list[list]:
    header = [["Employee", "Field", "Our Value", "Supper Value", "Diff",
               "Status", "Note"]]
    return header + [r.as_row() for r in rows]
