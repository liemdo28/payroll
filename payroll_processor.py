#!/usr/bin/env python3
"""
Payroll Processor – Raw Sushi Bistro
=====================================
Usage (standalone with local CSV files):
    python3 payroll_processor.py --timesheet FILE --orders FILE

Outputs to --out-dir (default: ./output/):
    current_sheet_MM-DD.csv   – per-employee timesheet + Super Sheet
    tip_records_MM-DD.csv     – per-server per-shift tip detail (admin file)
    val_summary_MM-DD.csv     – SERVER/BAR/CASHIER VAL table

Key formulas:
    VAL   = Dine-In Sales × 6%   (per server / bartender)
    FOH   = FOH Card Tips         (blue row – takeout/pickup orders)
    T30   = FOH × 2/3  −  cashier_paid
    E89   = total_server_val × E3 + T30   (kitchen pool; E3 in config.py)
    Kitchen tip per employee = (hours / total_kitchen_hours) × E89
    Server net tip = (Card Tip + Gratuity) − VAL
    Lunch  shift : clock-in before 15:00
    Dinner shift : clock-in ≥ 15:00
"""

import argparse
import base64
import csv
import io
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date, time as dtime
from pathlib import Path
from typing import Optional

import config as cfg
from name_map import normalize as _norm


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Shift:
    """One clock-in/out row from the Toast timesheet CSV."""
    name: str
    role: str
    work_date: date
    clock_in_time: Optional[dtime]
    total_hours: float
    regular_hours: float
    ot_hours: float
    wage_rate: float
    estimated_wages: float

    @property
    def shift_label(self) -> str:
        if self.clock_in_time and self.clock_in_time.hour < cfg.LUNCH_CUTOFF_HOUR:
            return "Lunch"
        return "Dinner"


@dataclass
class EmployeeTotals:
    """Aggregated timesheet totals (from 'Totals for …' rows) + shift counts."""
    name: str
    roles: set = field(default_factory=set)
    total_hours: float = 0.0
    regular_hours: float = 0.0
    ot_hours: float = 0.0
    wage_rate: float = 0.0
    estimated_wages: float = 0.0
    lunch_shifts: int = 0
    dinner_shifts: int = 0


@dataclass
class OrderRow:
    """One row from the Order Details CSV."""
    opened: datetime
    server: str
    dining_option: str
    amount: float
    tip: float
    gratuity: float
    voided: bool


@dataclass
class ServerShiftTip:
    """Computed tip record for one server on one date/shift."""
    work_date: date
    shift: str
    job: str
    name: str
    sub: float
    card_tip: float
    gratuity: float
    val: float
    tip: float        # = card_tip + gratuity  (server keeps all)
    total: float      # = tip − val  (net after tip-out)
    cashier_tip: float = 0.0


@dataclass
class EmployeePaySummary:
    """One row of the Super Sheet."""
    search_name: str
    other_name: str
    display_name: str
    total_hours: float = 0.0
    ot_hours: float = 0.0
    regular_hours: float = 0.0
    tip: float = 0.0                  # server / bartender net tip
    busser_cashier: float = 0.0       # amount received from tip pool as busser/cashier
    sushi_tip: float = 0.0
    kitchen_tip: float = 0.0
    bartender_tip: float = 0.0
    grand_total: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _float(val: str) -> float:
    if not val or val.strip() in ("", "-"):
        return 0.0
    return float(re.sub(r"[$,\s]", "", val.strip()))


def _parse_ts_date(val: str) -> Optional[date]:
    """Parse 'May 1 2026' or 'April 27 2026' from timesheet CSV."""
    val = val.strip()
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    return None


def _parse_ts_time(val: str) -> Optional[dtime]:
    """Parse '3:35pm' or '10:28am' from timesheet CSV."""
    val = val.strip().replace(" ", "").lower()
    if not val:
        return None
    for fmt in ("%I:%M%p", "%H:%M"):
        try:
            return datetime.strptime(val, fmt).time()
        except ValueError:
            pass
    return None


def _parse_order_dt(val: str) -> Optional[datetime]:
    """Parse '4/27/26 4:30 PM' from Order Details CSV."""
    val = val.strip()
    for fmt in ("%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
    return None


def _is_foh(server: str) -> bool:
    return server.strip().lower() in cfg.FOH_SERVER_NAMES


def _role_cat(role: str) -> str:
    r = role.strip().lower()
    if r in cfg.SERVER_ROLES:    return "Server"
    if r in cfg.BARTENDER_ROLES: return "Bartender"
    if r in cfg.CASHIER_ROLES:   return "Cashier"
    if r in cfg.BUSSER_ROLES:    return "Busser"
    if r in cfg.KITCHEN_ROLES:   return "Kitchen"
    if r in cfg.SUSHI_ROLES:     return "Sushi"
    return "Other"


def _fmt_dollar(v: float) -> str:
    return f"${v:,.2f}" if v != 0.0 else ""


def _r(v: float) -> float:
    return round(v, 2)


# ─────────────────────────────────────────────────────────────────────────────
# 1 – Parse timesheet CSV
# ─────────────────────────────────────────────────────────────────────────────

def parse_timesheet(text: str) -> tuple[list[Shift], dict[str, EmployeeTotals]]:
    """
    Returns (shifts, totals_by_name).

    Shift rows  → Shift objects (with clock-in time for Lunch/Dinner detection)
    Totals rows → EmployeeTotals (hours aggregated by Toast for the period)
    """
    shifts: list[Shift] = []
    totals: dict[str, EmployeeTotals] = {}
    cur_cols: list[str] = []

    for row in csv.reader(io.StringIO(text)):
        if not any(c.strip() for c in row):
            continue

        # Detect header rows
        if row[0].strip() == "Name" and len(row) > 3 and "Clock in date" in row[1]:
            cur_cols = [c.strip().lower() for c in row]
            continue

        # Skip metadata / separator rows
        first = row[0].strip()
        if first in ("-", "Raw Sushi Bistro", "Payroll Period", ""):
            continue

        col = {c: i for i, c in enumerate(cur_cols)} if cur_cols else {}

        # ── Totals row ────────────────────────────────────────────────────────
        if first.startswith("Totals for "):
            emp = _norm(first[len("Totals for "):].strip())
            if not col:
                continue
            t_h  = _float(row[col.get("total paid hours",  14)])
            r_h  = _float(row[col.get("regular hours",     15)])
            ot_h = _float(row[col.get("ot hours",          17)])
            wage = _float(row[col.get("estimated wages",   18)])
            if emp not in totals:
                totals[emp] = EmployeeTotals(name=emp)
            e = totals[emp]
            e.total_hours     += t_h
            e.regular_hours   += r_h
            e.ot_hours        += ot_h
            e.estimated_wages += wage
            continue

        # ── Individual shift row ──────────────────────────────────────────────
        if not cur_cols:
            continue
        emp = _norm(row[col.get("name", 0)].strip())
        if not emp or emp == "Name":
            continue

        role      = row[col.get("role", 10)].strip()
        clk_date  = _parse_ts_date(row[col.get("clock in date",  1)])
        clk_time  = _parse_ts_time(row[col.get("clock in time",  2)])
        t_h       = _float(row[col.get("total paid hours",  14)])
        r_h       = _float(row[col.get("regular hours",     15)])
        ot_h      = _float(row[col.get("ot hours",          17)])
        wage      = _float(row[col.get("wage rate",         11)])
        wages     = _float(row[col.get("estimated wages",   18)])

        if not clk_date or not emp:
            continue

        # Track in totals dict
        if emp not in totals:
            totals[emp] = EmployeeTotals(name=emp, wage_rate=wage)
        e = totals[emp]
        e.roles.add(role)
        if wage and not e.wage_rate:
            e.wage_rate = wage

        s = Shift(
            name=emp, role=role, work_date=clk_date, clock_in_time=clk_time,
            total_hours=t_h, regular_hours=r_h, ot_hours=ot_h,
            wage_rate=wage, estimated_wages=wages,
        )
        shifts.append(s)

        # Count Lunch / Dinner shifts per kitchen/sushi employee
        cat = _role_cat(role)
        if cat in ("Kitchen", "Sushi"):
            if s.shift_label == "Lunch":
                e.lunch_shifts  += 1
            else:
                e.dinner_shifts += 1

    return shifts, totals


# ─────────────────────────────────────────────────────────────────────────────
# 2 – Parse Order Details CSV
# ─────────────────────────────────────────────────────────────────────────────

def parse_orders(text: str) -> list[OrderRow]:
    orders: list[OrderRow] = []
    for row in csv.DictReader(io.StringIO(text)):
        dt = _parse_order_dt(row.get("Opened", ""))
        if dt is None:
            continue
        orders.append(OrderRow(
            opened=dt,
            server=_norm(row.get("Server", "").strip()),
            dining_option=row.get("Dining Options", "").strip(),
            amount=_float(row.get("Amount", "0")),
            tip=_float(row.get("Tip",     "0")),
            gratuity=_float(row.get("Gratuity", "0")),
            voided=row.get("Voided", "false").strip().lower() == "true",
        ))
    return orders


# ─────────────────────────────────────────────────────────────────────────────
# 3 – Compute per-shift tip records
# ─────────────────────────────────────────────────────────────────────────────

def compute_tips(orders: list[OrderRow]) -> list[ServerShiftTip]:
    """
    Groups orders by (date, shift, server) and calculates:
        Sub        = Dine-In sales (non-voided, non-FOH, non-zero-amount)
        Card Tip   = sum tips
        Gratuity   = sum gratuity
        VAL        = Sub × 6%
        Tip        = Card Tip + Gratuity
        Total      = Tip − VAL   (server net)

    FOH row:   card tips for takeout/pickup orders aggregated per (date, shift)
               VAL_foh = FOH card tips × 1/3
               cashier gets FOH card tips × 2/3  (if cashier present that shift)

    Shift label: order open time before 15:00 → Lunch, else → Dinner
    """
    sub_acc      = defaultdict(float)   # (date, shift, name) → sales
    tip_acc      = defaultdict(float)
    grat_acc     = defaultdict(float)
    foh_tip_acc  = defaultdict(float)   # (date, shift) → FOH card tips
    cashier_map: dict[tuple, str] = {}  # (date, shift) → cashier name

    for o in orders:
        if o.voided:
            continue
        d     = o.opened.date()
        shift = "Lunch" if o.opened.hour < cfg.LUNCH_CUTOFF_HOUR else "Dinner"

        if _is_foh(o.server):
            foh_tip_acc[(d, shift)] += o.tip
            continue

        # Cashier detection: zero-amount order with tip only
        if o.amount == 0.0 and (o.tip > 0 or o.gratuity > 0):
            cashier_map[(d, shift)] = o.server
            continue

        key = (d, shift, o.server)
        sub_acc[key]  += o.amount
        tip_acc[key]  += o.tip
        grat_acc[key] += o.gratuity

    records: list[ServerShiftTip] = []

    # Server / Bartender records
    for (d, shift, name), sub in sub_acc.items():
        ct    = _r(tip_acc[(d, shift, name)])
        grat  = _r(grat_acc[(d, shift, name)])
        val   = _r(sub * cfg.SERVER_VAL_PCT)
        tip   = _r(ct + grat)
        total = _r(tip - val)
        records.append(ServerShiftTip(
            work_date=d, shift=shift, job="Server",
            name=name, sub=_r(sub),
            card_tip=ct, gratuity=grat,
            val=val, tip=tip, total=total,
        ))

    # FOH (blue) rows – one per (date, shift)
    for (d, shift), foh_tip in foh_tip_acc.items():
        foh_val      = _r(foh_tip * cfg.FOH_VAL_PCT)
        cashier_amt  = _r(foh_tip * cfg.CASHIER_FOH_PCT)
        cashier_name = cashier_map.get((d, shift), "")

        records.append(ServerShiftTip(
            work_date=d, shift=shift, job="FOH",
            name="zMaster Code",
            sub=0.0, card_tip=_r(foh_tip), gratuity=0.0,
            val=foh_val, tip=cashier_amt, total=_r(cashier_amt - foh_val),
            cashier_tip=cashier_amt,
        ))

        if cashier_name:
            records.append(ServerShiftTip(
                work_date=d, shift=shift, job="Cashier",
                name=cashier_name,
                sub=0.0, card_tip=0.0, gratuity=0.0,
                val=0.0, tip=cashier_amt, total=cashier_amt,
                cashier_tip=cashier_amt,
            ))

    records.sort(key=lambda r: (r.work_date, r.shift, r.name))
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 4 – Aggregate server tips per employee (period totals)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_server_tips(records: list[ServerShiftTip]) -> dict[str, dict]:
    agg: dict[str, dict] = defaultdict(lambda: {
        "sub": 0.0, "card_tip": 0.0, "gratuity": 0.0,
        "val": 0.0, "net_tip": 0.0,
    })
    for r in records:
        if r.job in ("Server", "Bartender"):
            a = agg[r.name]
            a["sub"]      += r.sub
            a["card_tip"] += r.card_tip
            a["gratuity"] += r.gratuity
            a["val"]      += r.val
            a["net_tip"]  += r.total
    return {k: {f: _r(v) for f, v in d.items()} for k, d in agg.items()}


# ─────────────────────────────────────────────────────────────────────────────
# 5 – Kitchen pool & distribution
#
# E3   = $F$77 = SUM(F55:F76) = total_server_val (sum of server VAL from tip records)
# T30  = FOH_CardTip × 2/3 − total_cashier_paid
# E89  = E3 × KITCHEN_SERVER_VAL_FRACTION (M22) + T30
# Each kitchen employee tip = (their_hours / total_kitchen_hours) × E89
# ─────────────────────────────────────────────────────────────────────────────

def compute_kitchen_tips(
    shifts: list[Shift],
    records: list[ServerShiftTip],
) -> dict[str, float]:
    """Returns {employee_name: kitchen_tip_amount}."""

    # T30 = FOH × 2/3 − cashier_paid
    foh_card_tips    = _r(sum(r.card_tip    for r in records if r.job == "FOH"))
    cashier_paid     = _r(sum(r.cashier_tip for r in records if r.job == "Cashier"))
    T30              = _r(foh_card_tips * cfg.CASHIER_FOH_PCT - cashier_paid)

    # E3 = SUM(F55:F76) = total server VAL from tip records
    total_server_val = _r(sum(r.val for r in records if r.job == "Server"))

    # E89 = kitchen pool
    E89 = _r(total_server_val * cfg.KITCHEN_SERVER_VAL_FRACTION + T30)

    kitchen_hours: dict[str, float] = defaultdict(float)
    for s in shifts:
        if _role_cat(s.role) == "Kitchen":
            kitchen_hours[s.name] += s.total_hours

    total_k_hours = sum(kitchen_hours.values()) or 1.0
    return {
        name: _r(hours / total_k_hours * E89)
        for name, hours in kitchen_hours.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6 – Sushi pool & distribution
#
# F3 = E3 × SUSHI_VAL_FRACTION (M24)
#       + SUSHI_D123  (D123, pending confirmation)
#       + IFNA(VLOOKUP("Sushi Chef", A55:I76, 9), 0)
#            → col 9 = sum of (card_tip + gratuity) for sushi employees' orders
#
# Per-employee: Tip = G_i × F3 / SUM(G)   where G = hours × multiplier (H)
# ─────────────────────────────────────────────────────────────────────────────

def compute_sushi_tips(
    shifts: list[Shift],
    records: list[ServerShiftTip],
) -> dict[str, float]:
    """Returns {employee_name: sushi_tip_amount}."""

    # Identify sushi employees from the timesheet
    sushi_names = {s.name for s in shifts if _role_cat(s.role) == "Sushi"}

    # IFNA(VLOOKUP("Sushi Chef", A55:I76, 9), 0)
    # = card_tip + gratuity for POS orders attributed to sushi staff
    sushi_direct = _r(sum(
        r.card_tip + r.gratuity
        for r in records
        if r.job == "Server" and r.name in sushi_names
    ))

    # E3 = total server VAL (same as kitchen)
    total_server_val = _r(sum(r.val for r in records if r.job == "Server"))

    # F3 = sushi pool
    sushi_pool = _r(
        total_server_val * cfg.SUSHI_VAL_FRACTION
        + cfg.SUSHI_D123
        + sushi_direct
    )

    # G = hours × multiplier H  (weighted allocation)
    weighted: dict[str, float] = defaultdict(float)
    for s in shifts:
        if _role_cat(s.role) == "Sushi":
            mult = cfg.SUSHI_MULTIPLIERS.get(s.role.strip().lower(), 1.0)
            weighted[s.name] += s.total_hours * mult

    total_weight = sum(weighted.values()) or 1.0
    return {
        name: _r(w / total_weight * sushi_pool)
        for name, w in weighted.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7 – Build Super Sheet
# ─────────────────────────────────────────────────────────────────────────────

def build_super_sheet(
    ts_totals: dict[str, EmployeeTotals],
    server_tips: dict[str, dict],
    kitchen_tips: dict[str, float],
    sushi_tips: dict[str, float],
) -> list[EmployeePaySummary]:
    all_names = (
        set(ts_totals) | set(server_tips) | set(kitchen_tips) | set(sushi_tips)
    )
    rows: list[EmployeePaySummary] = []
    for name in sorted(all_names):
        ts   = ts_totals.get(name)
        tips = server_tips.get(name, {})
        kt   = kitchen_tips.get(name, 0.0)
        st   = sushi_tips.get(name, 0.0)

        net_tip    = tips.get("net_tip", 0.0)
        grand      = _r(net_tip + kt + st)

        rows.append(EmployeePaySummary(
            search_name=name, other_name="", display_name=name,
            total_hours=ts.total_hours   if ts else 0.0,
            ot_hours=ts.ot_hours         if ts else 0.0,
            regular_hours=ts.regular_hours if ts else 0.0,
            tip=net_tip, sushi_tip=st, kitchen_tip=kt,
            grand_total=grand,
        ))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 8 – CSV output generators
# ─────────────────────────────────────────────────────────────────────────────

def gen_current_sheet_csv(
    period_start: date,
    period_end: date,
    shifts: list[Shift],
    ts_totals: dict[str, EmployeeTotals],
    super_sheet: list[EmployeePaySummary],
) -> str:
    """Current payroll sheet: timesheet rows + Super Sheet table."""
    buf = io.StringIO()
    w   = csv.writer(buf)

    period_label = (f"{period_start.strftime('%m/%d/%Y')} "
                    f"To {period_end.strftime('%m/%d/%Y')}")
    w.writerow(["Raw Sushi Bistro"])
    w.writerow(["Payroll Period", period_label])
    w.writerow([])

    # ── Timesheet rows ────────────────────────────────────────────────────────
    HDR = ["Name", "Clock in date", "Clock in time",
           "Role", "Wage rate", "Total paid hours",
           "Regular hours", "OT hours", "Estimated wages"]
    prev = None
    for s in sorted(shifts, key=lambda x: (x.name, x.work_date)):
        if s.name != prev:
            w.writerow([])
            w.writerow(HDR)
            prev = s.name
        w.writerow([
            s.name,
            f"{s.work_date.strftime('%b')} {s.work_date.day} {s.work_date.year}",
            s.clock_in_time.strftime("%I:%M %p").lstrip("0") if s.clock_in_time else "",
            s.role,
            f"${s.wage_rate:.2f}",
            f"{s.total_hours:.2f}",
            f"{s.regular_hours:.2f}",
            f"{s.ot_hours:.2f}" if s.ot_hours else "0.00",
            f"${s.estimated_wages:.2f}",
        ])

    # Totals rows
    w.writerow([])
    for name, t in sorted(ts_totals.items()):
        w.writerow([
            f"Totals for {name}", "", "",
            "", "", f"{t.total_hours:.2f}",
            f"{t.regular_hours:.2f}", f"{t.ot_hours:.2f}",
            f"${t.estimated_wages:.2f}",
        ])

    # ── Super Sheet ───────────────────────────────────────────────────────────
    w.writerow([])
    w.writerow([
        "Search Name", "Other name", "Name",
        "Total", "Over", "Regular",
        "Tip", "Busser/Cashier/Hostess", "Sushi chef", "Kitchen", "Bartender",
        "Total",
    ])
    for row in super_sheet:
        w.writerow([
            row.search_name, row.other_name, row.display_name,
            f"{row.total_hours:.2f}" if row.total_hours else "",
            f"{row.ot_hours:.2f}"    if row.ot_hours    else "",
            f"{row.regular_hours:.2f}" if row.regular_hours else "0.00",
            _fmt_dollar(row.tip),
            _fmt_dollar(row.busser_cashier),
            _fmt_dollar(row.sushi_tip),
            _fmt_dollar(row.kitchen_tip),
            _fmt_dollar(row.bartender_tip),
            _fmt_dollar(row.grand_total),
        ])
    return buf.getvalue()


def gen_tip_records_csv(records: list[ServerShiftTip]) -> str:
    """Per-shift tip detail table (for the admin / formula file)."""
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([
        "Date (m/d/yyyy)", "Shift", "Job", "Name",
        "Total", "Subtotal", "Card Tip", "Gratuity",
        "Sum Tip_Gratuity", "Val", "Tip",
    ])
    for r in records:
        sum_tg = _r(r.card_tip + r.gratuity)
        w.writerow([
            f"{r.work_date.month}/{r.work_date.day}/{r.work_date.year}",
            r.shift, r.job, r.name,
            _fmt_dollar(r.total),
            f"{r.sub:.2f}"     if r.sub     else "",
            f"{r.card_tip:.2f}" if r.card_tip else "",
            f"{r.gratuity:.2f}" if r.gratuity else "",
            f"{sum_tg:.2f}"    if sum_tg    else "",
            f"{r.val:.2f}"     if r.val     else "",
            f"{r.tip:.2f}"     if r.tip     else "",
        ])
    return buf.getvalue()


def gen_val_summary_csv(
    server_tips: dict[str, dict],
    foh_card_tips: float,
    foh_val: float,
) -> str:
    """SERVER / BAR / CASHIER VAL summary (matches Formular f Payroll screenshot)."""
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([
        "Name", "Subtotal (Dine In Sale)", "Card Tip", "Gratuity",
        "VAL (= Sub × 6%)", "Server/Bartender card tip (= Card Tip + Gratuity)",
    ])
    for name, a in sorted(server_tips.items()):
        w.writerow([
            name,
            f"{a['sub']:.2f}",
            f"{a['card_tip']:.2f}",
            f"{a['gratuity']:.2f}",
            f"{a['val']:.2f}",
            f"{a['card_tip'] + a['gratuity']:.2f}",
        ])
    # FOH blue row
    w.writerow([
        "FOH / zMaster Code", "",
        f"{foh_card_tips:.2f}", "",
        f"{foh_val:.2f}", "",
    ])
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 9 – Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run(ts_text: str, ord_text: str, period_end: date) -> dict:
    shifts, ts_totals = parse_timesheet(ts_text)
    orders            = parse_orders(ord_text)
    tip_records       = compute_tips(orders)
    server_tips       = aggregate_server_tips(tip_records)
    kitchen_tips      = compute_kitchen_tips(shifts, tip_records)
    sushi_tips        = compute_sushi_tips(shifts, tip_records)
    super_sheet       = build_super_sheet(ts_totals, server_tips, kitchen_tips, sushi_tips)

    all_dates    = [s.work_date for s in shifts if s.work_date]
    period_start = min(all_dates) if all_dates else period_end

    foh_ct  = _r(sum(r.card_tip for r in tip_records if r.job == "FOH"))
    foh_val = _r(foh_ct * cfg.FOH_VAL_PCT)

    return {
        "period_start":    period_start,
        "period_end":      period_end,
        "current_csv":     gen_current_sheet_csv(period_start, period_end, shifts, ts_totals, super_sheet),
        "tip_records_csv": gen_tip_records_csv(tip_records),
        "val_summary_csv": gen_val_summary_csv(server_tips, foh_ct, foh_val),
        "super_sheet":     super_sheet,
        "tip_records":     tip_records,
        "server_tips":     server_tips,
        "kitchen_tips":    kitchen_tips,
        "sushi_tips":      sushi_tips,
        "foh_card_tips":   foh_ct,
        "foh_val":         foh_val,
        "T30":             _r(foh_ct * cfg.CASHIER_FOH_PCT
                               - sum(r.cashier_tip for r in tip_records if r.job == "Cashier")),
        "sushi_pool":      _r(
                               _r(sum(r.val for r in tip_records if r.job == "Server"))
                               * cfg.SUSHI_VAL_FRACTION
                               + cfg.SUSHI_D123
                               + _r(sum(
                                   r.card_tip + r.gratuity
                                   for r in tip_records
                                   if r.job == "Server"
                                   and r.name in {s.name for s in shifts if _role_cat(s.role) == "Sushi"}
                               ))
                           ),
    }


def print_summary(result: dict) -> None:
    print(f"\n{'='*65}")
    print(f"  Payroll  {result['period_start']}  →  {result['period_end']}")
    print(f"{'='*65}")
    print(f"\n  FOH Card Tips  : ${result['foh_card_tips']:>8,.2f}")
    print(f"  FOH VAL (1/3)  : ${result['foh_val']:>8,.2f}")
    print(f"  T30 (kitchen)  : ${result['T30']:>8,.2f}")
    print(f"  Sushi pool (F3): ${result['sushi_pool']:>8,.2f}")
    print()
    print(f"  {'Name':<28} {'Hours':>7} {'OT':>6} {'Net Tip':>10} {'Total':>10}")
    print(f"  {'-'*63}")
    for row in result["super_sheet"]:
        if row.total_hours or row.grand_total:
            print(f"  {row.display_name:<28} {row.total_hours:>7.2f} "
                  f"{row.ot_hours:>6.2f} {row.tip:>10.2f} {row.grand_total:>10.2f}")
    total_pool = sum(r.val for r in result["tip_records"] if r.job in ("Server", "FOH"))
    print(f"\n  Total VAL pool (server 6% + FOH 1/3) = ${total_pool:,.2f}")
    print(f"\n  Output: current_sheet.csv  tip_records.csv  val_summary.csv\n")


def main():
    ap = argparse.ArgumentParser(description="Raw Sushi Bistro Payroll Processor")
    ap.add_argument("--timesheet",  help="Toast timesheet CSV path")
    ap.add_argument("--orders",     help="Order Details CSV path")
    ap.add_argument("--period-end", help="Period end date YYYY-MM-DD (auto-detected if omitted)")
    ap.add_argument("--out-dir",    default="output", help="Output directory")
    args = ap.parse_args()

    # ── Find input files ──────────────────────────────────────────────────────
    if args.timesheet and args.orders:
        ts_text  = Path(args.timesheet).read_text()
        ord_text = Path(args.orders).read_text()
        ts_path  = Path(args.timesheet)
        ord_path = Path(args.orders)
    else:
        ts_path = ord_path = None
        for f in sorted(Path(".").glob("*.csv"), reverse=True):
            fl = f.name.lower().replace("_", "").replace(" ", "")
            if "timesheet" in fl and ts_path is None:
                ts_path = f
            elif "orderdetail" in fl and ord_path is None:
                ord_path = f
        if not ts_path or not ord_path:
            print("ERROR: Cannot find timesheet and/or order-detail CSV files.\n"
                  "  Run:  python3 payroll_processor.py --timesheet FILE --orders FILE")
            sys.exit(1)
        print(f"Using:  {ts_path.name}  +  {ord_path.name}")
        ts_text  = ts_path.read_text()
        ord_text = ord_path.read_text()

    # ── Auto-detect period end ────────────────────────────────────────────────
    if args.period_end:
        period_end = date.fromisoformat(args.period_end)
    else:
        fn = ord_path.name if ord_path else ""
        m  = re.search(r"(\d{4})[_\-](\d{2})[_\-](\d{2})[^_\-\d]*(\d{4})[_\-](\d{2})[_\-](\d{2})", fn)
        if m:
            period_end = date(int(m[4]), int(m[5]), int(m[6]))
        else:
            tmp_shifts, _ = parse_timesheet(ts_text)
            dates = [s.work_date for s in tmp_shifts if s.work_date]
            period_end = max(dates) if dates else date.today()

    # ── Run & write ───────────────────────────────────────────────────────────
    result = run(ts_text, ord_text, period_end)
    print_summary(result)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = period_end.strftime("%m-%d")

    (out / f"current_sheet_{tag}.csv").write_text(result["current_csv"])
    (out / f"tip_records_{tag}.csv").write_text(result["tip_records_csv"])
    (out / f"val_summary_{tag}.csv").write_text(result["val_summary_csv"])
    print(f"  Files written → {out.resolve()}\n")


if __name__ == "__main__":
    main()
