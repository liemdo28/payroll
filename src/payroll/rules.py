"""
Payroll calculation rules — pure functions, no side-effects, fully testable.

All money values are Python float rounded to 2 decimal places.
Rounding uses round(x, 2) throughout (banker's rounding via Python's built-in).

Formula sources (confirmed by owner):
  VAL         = Dine-In sub × 6%
  FOH pool    = FOH card tips × 1/3  → tip pool
  FOH cashier = FOH card tips × 2/3  → cashier
  T30         = FOH card tips × 2/3 − cashier_paid
  Kitchen E89 = total_server_val × M22 + T30
  Sushi F3    = total_server_val × M24 + D123 + sushi_direct_tips
  Distribution = (hours [× multiplier]) / SUM × pool
  Net tip      = (card_tip + gratuity) − VAL
"""

from __future__ import annotations


def r(v: float) -> float:
    """Round to 2 decimal places."""
    return round(v, 2)


# ── Individual tip-out calculations ──────────────────────────────────────────

def server_val(sub: float, rate: float = 0.06) -> float:
    """VAL = Dine-In subtotal × rate (default 6%)."""
    return r(sub * rate)


def foh_split(foh_card_tip: float, cashier_pct: float = 2 / 3, val_pct: float = 1 / 3
              ) -> tuple[float, float]:
    """Return (cashier_amount, val_to_pool) for one FOH card-tip amount."""
    return r(foh_card_tip * cashier_pct), r(foh_card_tip * val_pct)


def t30(foh_card_tip: float, cashier_paid: float,
        cashier_foh_pct: float = 2 / 3) -> float:
    """T30 = FOH × 2/3 − total_cashier_paid  (kitchen pool base)."""
    return r(foh_card_tip * cashier_foh_pct - cashier_paid)


def kitchen_pool(total_server_val: float, t30_val: float,
                 m22: float = 0.0) -> float:
    """E89 = total_server_val × M22 + T30."""
    return r(total_server_val * m22 + t30_val)


def sushi_pool(total_server_val: float, m24: float, d123: float,
               sushi_direct: float) -> float:
    """F3 = E3 × M24 + D123 + IFNA(sushi_direct, 0)."""
    return r(total_server_val * m24 + d123 + sushi_direct)


def server_net_tip(card_tip: float, gratuity: float, val: float) -> float:
    """Net tip kept by server = (card_tip + gratuity) − VAL."""
    return r(card_tip + gratuity - val)


# ── Pool distribution ─────────────────────────────────────────────────────────

def distribute_by_hours(pool: float, hours: dict[str, float]) -> dict[str, float]:
    """
    Distribute pool proportional to hours.
    Kitchen formula: each employee = (hours / total_hours) × E89
    """
    total = sum(hours.values()) or 1.0
    return {name: r(h / total * pool) for name, h in hours.items()}


def distribute_weighted(pool: float, weighted_hours: dict[str, float]) -> dict[str, float]:
    """
    Distribute pool proportional to (hours × multiplier).
    Sushi formula: each employee = G_i / SUM(G) × F3
                   where G = hours × multiplier H
    """
    total = sum(weighted_hours.values()) or 1.0
    return {name: r(w / total * pool) for name, w in weighted_hours.items()}


# ── Pay components ────────────────────────────────────────────────────────────

def base_pay(hours: float, wage_rate: float) -> float:
    """Regular hours × wage rate."""
    return r(hours * wage_rate)


def overtime_pay(ot_hours: float, wage_rate: float, ot_multiplier: float = 1.5) -> float:
    """OT hours × wage rate × 1.5 (standard US overtime)."""
    return r(ot_hours * wage_rate * ot_multiplier)


def total_pay(
    base: float,
    ot: float = 0.0,
    tip: float = 0.0,
    busser_cashier: float = 0.0,
    sushi: float = 0.0,
    kitchen: float = 0.0,
    bartender: float = 0.0,
    bonus: float = 0.0,
    deduction: float = 0.0,
) -> float:
    """
    Grand total = base + OT + all tip-pool receipts + bonus − deduction.
    Note: the current payroll is tip-focused; base/OT wages are tracked
    separately (not combined in the tip distribution sheet).
    """
    return r(base + ot + tip + busser_cashier + sushi + kitchen + bartender
             + bonus - deduction)


# ── Rounding helpers ──────────────────────────────────────────────────────────

def parse_dollar(val: str) -> float:
    """Parse a dollar string like '$1,234.56' or '1234.56' → float."""
    if not val or str(val).strip() in ("", "-", "—"):
        return 0.0
    import re
    cleaned = re.sub(r"[$,\s]", "", str(val).strip())
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_hours(val: str) -> float:
    """Parse an hours string like '40.50' → float."""
    try:
        return float(str(val).strip())
    except ValueError:
        return 0.0
