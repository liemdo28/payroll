"""
Input data validator and error collector.

Collects warnings/errors during parsing without crashing the pipeline.
Errors are written to the 'Errors' output tab.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationError:
    source: str          # "timesheet" | "orders"
    row_number: int
    field: str
    raw_value: Any
    message: str
    severity: str = "warning"   # "warning" | "error"

    def as_row(self) -> list:
        return [self.source, self.row_number, self.field,
                str(self.raw_value)[:100], self.message, self.severity]


class Validator:
    def __init__(self) -> None:
        self.errors: list[ValidationError] = []

    def warn(self, source: str, row: int, field: str, value: Any, msg: str) -> None:
        self.errors.append(ValidationError(source, row, field, value, msg, "warning"))

    def error(self, source: str, row: int, field: str, value: Any, msg: str) -> None:
        self.errors.append(ValidationError(source, row, field, value, msg, "error"))

    def check_required(self, source: str, row: int, field: str, value: Any) -> bool:
        if value is None or str(value).strip() == "":
            self.warn(source, row, field, value, f"Missing required field '{field}'")
            return False
        return True

    def check_positive(self, source: str, row: int, field: str, value: float) -> bool:
        if value < 0:
            self.warn(source, row, field, value, f"Negative value for '{field}'")
            return False
        return True

    def check_duplicate_employees(
        self, source: str, names: list[str]
    ) -> list[str]:
        seen: dict[str, int] = {}
        dupes = []
        for name in names:
            key = name.strip().lower()
            seen[key] = seen.get(key, 0) + 1
        for name, count in seen.items():
            if count > 1:
                dupes.append(name)
                self.warn(source, 0, "employee_name", name,
                          f"Duplicate employee name appears {count} times")
        return dupes

    @property
    def has_errors(self) -> bool:
        return any(e.severity == "error" for e in self.errors)

    def summary(self) -> str:
        errs  = sum(1 for e in self.errors if e.severity == "error")
        warns = sum(1 for e in self.errors if e.severity == "warning")
        return f"{errs} errors, {warns} warnings"

    def as_rows(self) -> list[list]:
        header = [["Source", "Row #", "Field", "Raw Value", "Message", "Severity"]]
        return header + [e.as_row() for e in self.errors]
