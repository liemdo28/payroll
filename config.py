"""
Business rule configuration for Raw Sushi Bistro payroll processing.

Runtime overrides via environment variables (recommended for production):
    RAW_FOLDER_ID    – Google Drive folder for raw CSV uploads
    PAYROLL_FILE_ID  – Google Sheets payroll workbook (one tab per period)
    ADMIN_FILE_ID    – Google Sheets admin workbook (Super Sheet / Tip Records)
    SERVICE_ACCOUNT_KEY – path to service-account JSON key (default: service_account.json)
"""

import os

# ── Tip-out rates ─────────────────────────────────────────────────────────────
SERVER_VAL_PCT  = 0.06      # 6 % of each server/bartender's Dine-In sales → pool
FOH_VAL_PCT     = 1 / 3     # 1/3 of FOH (takeout/pickup) card tips → pool (VAL)
CASHIER_FOH_PCT = 2 / 3     # 2/3 of FOH card tips → cashier on that shift

# ── Kitchen pool formula:  E89 = M22 * E3 + T30 ─────────────────────────────
#   T30 = FOH_CardTip × 2/3  −  total_cashier_paid   (computed automatically)
#   M22 = total server VAL from Dine-In   (computed automatically)
#   E3  = fraction of server VAL that flows into the kitchen pool
#         Set to 0 to use only T30; set to the actual fraction once confirmed.
KITCHEN_SERVER_VAL_FRACTION = float(os.getenv("KITCHEN_SERVER_VAL_FRACTION", "0.0"))
# TODO: confirm E3 value with owner, then set KITCHEN_SERVER_VAL_FRACTION env var

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
