# Raw Sushi Bistro – Payroll Pipeline

Automated payroll processing from Toast POS exports (timesheet + order details)
to Google Sheets, with comparison against the Sheet Supper reference.

## Setup

### 1. Install dependencies

```bash
pip install python-dotenv rsa
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real values
```

Key variables:

| Variable | Description |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to service-account JSON key (keep outside repo) |
| `SOURCE_FILE_1_ID` | Drive file ID for timesheet CSV (blank = auto-discover) |
| `SOURCE_FILE_2_ID` | Drive file ID for orders CSV (blank = auto-discover) |
| `OUTPUT_SHEET_ID` | Google Sheet to write payroll output into |
| `SUPPER_SHEET_ID` | Sheet containing "Sheet Supper" reference tab |
| `RAW_FOLDER_ID` | Drive folder for auto-discovery of latest CSV pair |

### 3. Service account permissions

The service account needs:
- **Google Drive**: Reader access to `RAW_FOLDER_ID` (or the specific source files)
- **Google Sheets**: Editor access to `OUTPUT_SHEET_ID` and `SUPPER_SHEET_ID`

## Running

### Auto-discover latest CSVs from Drive

```bash
python3 run_payroll.py
```

### Use specific Drive file IDs

```bash
python3 run_payroll.py \
    --source-file-1 <TIMESHEET_FILE_ID> \
    --source-file-2 <ORDERS_FILE_ID>
```

### Local CSV files (no Google Drive needed)

```bash
python3 run_payroll.py \
    --timesheet path/to/timesheet.csv \
    --orders    path/to/orders.csv \
    --no-upload
```

### Dry run (compute + compare, no Sheets write)

```bash
python3 run_payroll.py --dry-run
```

## Output

The pipeline writes 6 tabs to `OUTPUT_SHEET_ID`:

| Tab | Contents |
|---|---|
| Payroll Output | One row per employee: hours, tips, total pay |
| Compare With Supper | Field-by-field diff vs Sheet Supper (MATCH/DIFF/MISSING) |
| Raw Source 1 | Original timesheet CSV |
| Raw Source 2 | Original orders CSV |
| Errors | Validation warnings and errors |
| Run Metadata | Period dates, pool totals, run timestamp |

Local CSV output is also written to `output/` for every run.

## Tests

```bash
pytest tests/
```

End-to-end tests require CSV files at `/tmp/timesheet.csv` and `/tmp/orders.csv` —
they are skipped automatically when those files are absent.

## Payroll formulas

| Pool | Formula |
|---|---|
| Server VAL | `sub × 6%` per shift (Dine-In only) |
| FOH pool | FOH card tips × 1/3 |
| T30 (kitchen base) | FOH card tips × 2/3 − cashier_paid |
| Kitchen E89 | `total_server_val × M22 + T30` |
| Sushi F3 | `total_server_val × M24 + D123 + sushi_direct_tips` |
| Sushi distribution | `(hours × multiplier) / SUM(weighted) × F3` |

M22, M24, D123 are configured via `.env` (`KITCHEN_SERVER_VAL_FRACTION`,
`SUSHI_VAL_FRACTION`, `SUSHI_D123`).

## Security

- Never commit `.env`, `*.json` (service account), or any secret file.
- `.gitignore` excludes `*.json`, `output/`, `__pycache__/`.
- Sheet IDs in `.env.example` are non-sensitive public identifiers.
