"""
Payroll processing orchestrator.

Wraps the existing payroll_processor logic, produces a structured
PayrollResult that carries everything needed for output and comparison.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ── Make project root importable when called from anywhere ───────────────────
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config as cfg
from name_map import normalize
from payroll_processor import (
    parse_timesheet, parse_orders, compute_tips, aggregate_server_tips,
    compute_kitchen_tips, compute_sushi_tips, build_super_sheet,
    gen_current_sheet_csv, gen_tip_records_csv, gen_val_summary_csv,
    EmployeePaySummary, ServerShiftTip, Shift, EmployeeTotals,
)
from src.payroll.rules import r, t30 as calc_t30, kitchen_pool, sushi_pool
from src.payroll.validator import Validator


@dataclass
class PayrollResult:
    period_start: date
    period_end: date

    shifts: list[Shift]
    ts_totals: dict[str, EmployeeTotals]
    tip_records: list[ServerShiftTip]
    server_tips: dict[str, dict]
    kitchen_tips: dict[str, float]
    sushi_tips: dict[str, float]
    super_sheet: list[EmployeePaySummary]

    # Pool summary
    foh_card_tips: float
    foh_val: float
    T30: float
    total_server_val: float
    kitchen_pool_total: float
    sushi_pool_total: float

    # CSV snapshots (for Raw Source tabs)
    ts_raw_text: str = ""
    ord_raw_text: str = ""

    # Pre-rendered CSVs for local output
    current_csv: str = ""
    tip_records_csv: str = ""
    val_summary_csv: str = ""

    validator: Validator = field(default_factory=Validator)

    @property
    def tab_name(self) -> str:
        return self.period_end.strftime("%m-%d")

    def super_sheet_as_rows(self) -> list[list]:
        """Convert super sheet to 2-D list for Sheets API."""
        def _d(v: float) -> str:
            return f"${v:,.2f}" if v else ""

        header = [[
            "Search Name", "Other name", "Name",
            "Total hours", "Over (OT)", "Regular",
            "Tip", "Busser/Cashier/Hostess", "Sushi chef",
            "Kitchen", "Bartender", "Total",
        ]]
        rows = []
        for row in self.super_sheet:
            rows.append([
                row.search_name, row.other_name, row.display_name,
                f"{row.total_hours:.2f}" if row.total_hours else "",
                f"{row.ot_hours:.2f}"    if row.ot_hours    else "",
                f"{row.regular_hours:.2f}" if row.regular_hours else "0.00",
                _d(row.tip), _d(row.busser_cashier), _d(row.sushi_tip),
                _d(row.kitchen_tip), _d(row.bartender_tip), _d(row.grand_total),
            ])
        return header + rows

    def tip_records_as_rows(self) -> list[list]:
        """Convert tip records to 2-D list for Sheets API."""
        header = [[
            "Date", "Shift", "Job", "Name", "Total", "Subtotal",
            "Card Tip", "Gratuity", "Sum Tip+Gratuity", "VAL", "Net Tip",
        ]]
        rows = []
        for r_ in self.tip_records:
            sum_tg = r(r_.card_tip + r_.gratuity)
            rows.append([
                f"{r_.work_date.month}/{r_.work_date.day}/{r_.work_date.year}",
                r_.shift, r_.job, r_.name,
                f"${r_.total:,.2f}" if r_.total else "",
                f"{r_.sub:.2f}"      if r_.sub      else "",
                f"{r_.card_tip:.2f}" if r_.card_tip  else "",
                f"{r_.gratuity:.2f}" if r_.gratuity  else "",
                f"{sum_tg:.2f}"      if sum_tg       else "",
                f"{r_.val:.2f}"      if r_.val       else "",
                f"{r_.tip:.2f}"      if r_.tip       else "",
            ])
        return header + rows

    def pool_summary_rows(self) -> list[list]:
        return [
            ["Metric", "Value"],
            ["FOH Card Tips",   f"${self.foh_card_tips:,.2f}"],
            ["FOH VAL (1/3)",   f"${self.foh_val:,.2f}"],
            ["T30 (kitchen)",   f"${self.T30:,.2f}"],
            ["Total Server VAL (E3)", f"${self.total_server_val:,.2f}"],
            ["Kitchen Pool (E89)",    f"${self.kitchen_pool_total:,.2f}"],
            ["Sushi Pool (F3)",       f"${self.sushi_pool_total:,.2f}"],
        ]


def process(
    ts_text: str,
    ord_text: str,
    period_end: date | None = None,
    validator: Validator | None = None,
) -> PayrollResult:
    """
    Full payroll computation pipeline.

    Args:
        ts_text:    Toast timesheet CSV content
        ord_text:   Toast Order Details CSV content
        period_end: Override period-end date (auto-detected if None)
        validator:  Optional Validator instance for error collection

    Returns:
        PayrollResult with all computed data
    """
    v = validator or Validator()

    shifts, ts_totals = parse_timesheet(ts_text)
    orders            = parse_orders(ord_text)

    if not shifts:
        v.error("timesheet", 0, "rows", "", "No shift rows parsed from timesheet CSV")
    if not orders:
        v.error("orders", 0, "rows", "", "No order rows parsed from Order Details CSV")

    tip_records  = compute_tips(orders)
    server_tips  = aggregate_server_tips(tip_records)
    kitchen_tips = compute_kitchen_tips(shifts, tip_records)
    sushi_tips   = compute_sushi_tips(shifts, tip_records)
    super_sheet  = build_super_sheet(ts_totals, server_tips, kitchen_tips, sushi_tips)

    all_dates    = [s.work_date for s in shifts if s.work_date]
    period_start = min(all_dates) if all_dates else (period_end or date.today())
    if period_end is None:
        period_end = max(all_dates) if all_dates else date.today()

    foh_ct           = r(sum(rec.card_tip for rec in tip_records if rec.job == "FOH"))
    foh_val_amt      = r(foh_ct * cfg.FOH_VAL_PCT)
    cashier_paid     = r(sum(rec.cashier_tip for rec in tip_records if rec.job == "Cashier"))
    t30_val          = calc_t30(foh_ct, cashier_paid, cfg.CASHIER_FOH_PCT)
    total_server_val = r(sum(rec.val for rec in tip_records if rec.job == "Server"))
    sushi_names      = {s.name for s in shifts
                        if s.role.strip().lower() in cfg.SUSHI_ROLES}
    sushi_direct     = r(sum(
        rec.card_tip + rec.gratuity
        for rec in tip_records
        if rec.job == "Server" and rec.name in sushi_names
    ))
    k_pool = kitchen_pool(total_server_val, t30_val, cfg.KITCHEN_SERVER_VAL_FRACTION)
    s_pool = sushi_pool(total_server_val, cfg.SUSHI_VAL_FRACTION,
                        cfg.SUSHI_D123, sushi_direct)

    return PayrollResult(
        period_start=period_start,
        period_end=period_end,
        shifts=shifts,
        ts_totals=ts_totals,
        tip_records=tip_records,
        server_tips=server_tips,
        kitchen_tips=kitchen_tips,
        sushi_tips=sushi_tips,
        super_sheet=super_sheet,
        foh_card_tips=foh_ct,
        foh_val=foh_val_amt,
        T30=t30_val,
        total_server_val=total_server_val,
        kitchen_pool_total=k_pool,
        sushi_pool_total=s_pool,
        ts_raw_text=ts_text,
        ord_raw_text=ord_text,
        current_csv=gen_current_sheet_csv(period_start, period_end, shifts,
                                          ts_totals, super_sheet),
        tip_records_csv=gen_tip_records_csv(tip_records),
        val_summary_csv=gen_val_summary_csv(server_tips, foh_ct, foh_val_amt),
        validator=v,
    )
