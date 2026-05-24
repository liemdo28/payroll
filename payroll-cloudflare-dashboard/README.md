# Payroll Dashboard — Raw Sushi Bistro

A Cloudflare Pages + Workers dashboard for viewing payroll data processed by the Python backend.

## Local development

```bash
# Install dependencies
npm install

# Start Vite dev server (UI only, API uses mock data)
npm run dev

# Start full stack with Cloudflare Pages local emulator (real API functions)
npx wrangler pages dev dist --compatibility-date 2025-01-01
```

## Build

```bash
npm run build          # TypeScript check + Vite bundle → dist/
npm run typecheck      # Type check only
```

## Deploy to Cloudflare Pages

### First-time setup

```bash
# Authenticate wrangler
npx wrangler login

# Create the Pages project (once)
npx wrangler pages project create payroll-dashboard

# Deploy
npm run build
npx wrangler pages deploy dist --project-name payroll-dashboard
```

### CI / subsequent deploys

```bash
npm run build && npx wrangler pages deploy dist --project-name payroll-dashboard
```

## Environment variables

Set these in **Cloudflare Dashboard → Pages → payroll-dashboard → Settings → Environment Variables**:

| Variable | Type | Description |
|----------|------|-------------|
| `PAYROLL_FILE_ID` | Plain text | Google Sheets payroll workbook ID |
| `ADMIN_FILE_ID` | Plain text | Google Sheets admin workbook ID |
| `GOOGLE_SA_JSON` | **Secret** | Full service-account JSON (single line) |

Without these variables the dashboard uses built-in mock data and is fully functional for review.

## API routes

| Route | Description |
|-------|-------------|
| `GET /api/payroll/periods` | List available payroll periods |
| `GET /api/payroll/:period` | Full data for one period (e.g. `/api/payroll/05-10`) |

When `GOOGLE_SA_JSON` is not set, both routes return sample data from the **04/27 – 05/10/2026** period.

## How to connect real data

1. Create a Google Cloud project and enable the Sheets API.
2. Create a service account; download the JSON key.
3. Share the payroll and admin Sheets with the service account email.
4. In Cloudflare Pages, add `PAYROLL_FILE_ID`, `ADMIN_FILE_ID`, and `GOOGLE_SA_JSON` (as secret).
5. Redeploy — the dashboard will read live data from Sheets.

## Security notes

- Never commit `service_account.json` or any file containing credentials.
- `GOOGLE_SA_JSON` must be configured as a **Secret** in Cloudflare Pages (not a plain env var).
- The `.gitignore` in this repo excludes `*.json` files to prevent accidental key commits.
