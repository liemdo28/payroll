"""
Business rule configuration for Raw Sushi Bistro payroll processing.

Runtime overrides via environment variables (recommended for production):
    RAW_FOLDER_ID              – Google Drive folder for raw CSV uploads
    PAYROLL_FILE_ID            – Google Sheets payroll workbook (one tab per period)
    ADMIN_FILE_ID              – Google Sheets admin workbook (Super Sheet / Tip Records)
    SERVICE_ACCOUNT_KEY        – path to service-account JSON key (default: service_account.json)
    KITCHEN_SERVER_VAL_FRACTION – M22 in kitchen formula (pending owner confirmation)
    SUSHI_VAL_FRACTION         – M24 in sushi formula (pending owner confirmation)
    SUSHI_D123                 – D123 additional pool component (pending owner confirmation)
"""

import os

# ── Tip-out rates ─────────────────────────────────────────────────────────────
SERVER_VAL_PCT  = 0.06      # 6 % of each server/bartender's Dine-In sales → pool
FOH_VAL_PCT     = 1 / 3     # 1/3 of FOH (takeout/pickup) card tips → pool (VAL)
CASHIER_FOH_PCT = 2 / 3     # 2/3 of FOH card tips → cashier on that shift

# ── Kitchen pool formula ──────────────────────────────────────────────────────
#   E3   = $F$77 = SUM(F55:F76) = sum of all server VAL from the tip-records table
#          (computed automatically as total_server_val)
#   T30  = FOH_CardTip × 2/3  −  total_cashier_paid   (computed automatically)
#   E89  = E3 × M22 + T30     (kitchen pool)
#   Each kitchen employee tip = (their_hours / total_kitchen_hours) × E89
#
#   KITCHEN_SERVER_VAL_FRACTION = M22 (the multiplier applied to total server VAL)
#   Set to 0 to use only T30; update once owner confirms M22.
KITCHEN_SERVER_VAL_FRACTION = float(os.getenv("KITCHEN_SERVER_VAL_FRACTION", "0.0"))

# ── Sushi pool formula ────────────────────────────────────────────────────────
#   F3 = E3 × M24 + D123 + IFNA(VLOOKUP("Sushi Chef", A55:I76, 9), 0)
#     E3   = total server VAL (same as kitchen)
#     M24  = SUSHI_VAL_FRACTION (fraction of total VAL; pending confirmation)
#     D123 = additional pool component (pending confirmation; currently 0)
#     VLOOKUP("Sushi Chef",...,9) = sum of (card_tip + gratuity) for sushi
#            chefs' direct orders in the POS (auto-detected from timesheet roles)
#
#   Per-employee = (hours × multiplier) / SUM(hours × multiplier) × F3
#     G = C × H  where C = hours, H = SUSHI_MULTIPLIER for that role
#     Tip (col D) = G3 × F3 / SUM(G3:G17)
SUSHI_VAL_FRACTION = float(os.getenv("SUSHI_VAL_FRACTION", "0.0"))  # M24, pending confirmation
SUSHI_D123         = float(os.getenv("SUSHI_D123", "0.0"))           # D123, pending confirmation

# Multiplier H per sushi role (G = hours × H).  Default 1.0 until owner confirms values.
SUSHI_MULTIPLIERS: dict[str, float] = {
    "sushi":   float(os.getenv("SUSHI_MULT_SUSHI",   "1.0")),
    "sushi ":  float(os.getenv("SUSHI_MULT_SUSHI",   "1.0")),
}

# ── Shift boundary (from timesheet clock-in time) ────────────────────────────
#   Morning / Lunch shift : clock-in before this hour (10 am – 3 pm)
#   Evening / Dinner shift: clock-in at or after this hour
LUNCH_CUTOFF_HOUR = 15      # 3:00 PM

# ── Role classification ───────────────────────────────────────────────────────
SERVER_ROLES    = {"server", "server "}
BARTENDER_ROLES = {"bartender", "bartender.z"}
CASHIER_ROLES   = {"cashier"}
BUSSER_ROLES    = {"busser", "hostess", "host"}
KITCHEN_ROLES   = {"line cook", "prep", "floater", "fryer", "dishwasher"}
SUSHI_ROLES     = {"sushi", "sushi "}

# FOH pseudo-server names in Order Details (handled separately, not real servers)
FOH_SERVER_NAMES = {"foh foh", "foh", "master code", "zmaster code"}

# ── Google Drive / Sheets file IDs ────────────────────────────────────────────
# Override via environment variables; fall back to defaults for local dev.
RAW_FOLDER_ID   = os.getenv("RAW_FOLDER_ID",   "1_g5jBpoY54rX22TlLMlubZ4r15tfWhBO")
PAYROLL_FILE_ID = os.getenv("PAYROLL_FILE_ID",  "1WSiRuSmhwklWwZ7hAGdtqbFCuaiU6BMbLFrpzy3Df7o")
ADMIN_FILE_ID   = os.getenv("ADMIN_FILE_ID",    "1K1ycBuw2mdqZjWfHGw_DG-T5sYXF8LbWEOAs63lssPk")

# ── Service-account key path (local runs only; use Cloudflare secrets in prod) ─
SERVICE_ACCOUNT_KEY = os.getenv("SERVICE_ACCOUNT_KEY", "service_account.json")
