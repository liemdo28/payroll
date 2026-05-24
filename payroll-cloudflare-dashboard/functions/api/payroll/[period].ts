/**
 * GET /api/payroll/:period   e.g. /api/payroll/05-10
 *
 * Returns full payroll data for a given period tab.
 * Falls back to built-in mock data when env vars are not configured.
 */
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  PAYROLL_FILE_ID?: string;
  ADMIN_FILE_ID?: string;
  GOOGLE_SA_JSON?: string;
}

export const onRequestGet: PagesFunction<Env> = async ({ params, env }) => {
  const period = Array.isArray(params.period) ? params.period[0] : params.period;
  const headers = {
    "Content-Type": "application/json",
    "Cache-Control": "public, max-age=60",
  };

  if (!env.PAYROLL_FILE_ID || !env.GOOGLE_SA_JSON) {
    const mock = getMockData(period);
    if (!mock) {
      return new Response(JSON.stringify({ error: "Period not found in mock data" }), {
        status: 404,
        headers,
      });
    }
    return new Response(JSON.stringify(mock), { headers });
  }

  try {
    const token = await getServiceAccountToken(env.GOOGLE_SA_JSON);
    const data = await fetchPeriodFromSheets(env.PAYROLL_FILE_ID, period, token);
    return new Response(JSON.stringify(data), { headers });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return new Response(JSON.stringify({ error: msg }), { status: 500, headers });
  }
};

// ── Mock data for the 04/27 – 05/10/2026 period ──────────────────────────────

function getMockData(period: string) {
  if (period !== "05-10") return null;
  return {
    period_start: "04/27/2026",
    period_end: "05/10/2026",
    tab_name: "05-10",
    pool: {
      foh_card_tips: 606.01,
      foh_val: 202.0,
      t30: 404.01,
      total_val_pool: 2814.44,
      kitchen_pool: 404.01,
    },
    employees: [
      { search_name: "Aidan Stone",    other_name: "", display_name: "Aidan Stone",    total_hours: 35.95, ot_hours: 1.28, regular_hours: 34.67, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 15.85, bartender_tip: 0, grand_total: 15.85 },
      { search_name: "Ali Arevalo",    other_name: "", display_name: "Ali Arevalo",    total_hours: 45.31, ot_hours: 0,    regular_hours: 45.31, tip: 575.52, busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 575.52 },
      { search_name: "Angus Lo",       other_name: "", display_name: "Angus Lo",       total_hours: 14.67, ot_hours: 0,    regular_hours: 14.67, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 0 },
      { search_name: "Christian Rauda",other_name: "", display_name: "Christian Rauda",total_hours: 55.82, ot_hours: 3.14, regular_hours: 52.68, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 76.71, bartender_tip: 0, grand_total: 76.71 },
      { search_name: "Huy Nguyen",     other_name: "", display_name: "Huy Nguyen",     total_hours: 74.86, ot_hours: 1.15, regular_hours: 73.71, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 0 },
      { search_name: "Ian Paige",      other_name: "", display_name: "Ian Paige",      total_hours: 8.23,  ot_hours: 0,    regular_hours: 8.23,  tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 11.31, bartender_tip: 0, grand_total: 11.31 },
      { search_name: "Jay Perez",      other_name: "", display_name: "Jay Perez",      total_hours: 37.10, ot_hours: 0,    regular_hours: 37.10, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 0 },
      { search_name: "Jaydyn Perez",   other_name: "", display_name: "Jaydyn Perez",   total_hours: 0,     ot_hours: 0,    regular_hours: 0,     tip: 557.02, busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 557.02 },
      { search_name: "Joeleen Mey",    other_name: "", display_name: "Joeleen Mey",    total_hours: 10.88, ot_hours: 0,    regular_hours: 10.88, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 16.05, bartender_tip: 0, grand_total: 16.05 },
      { search_name: "Khiem Tran",     other_name: "", display_name: "Khiem Tran",     total_hours: 19.30, ot_hours: 0,    regular_hours: 19.30, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 26.52, bartender_tip: 0, grand_total: 26.52 },
      { search_name: "Kiko Yago",      other_name: "", display_name: "Kiko Yago",      total_hours: 57.40, ot_hours: 0.15, regular_hours: 57.25, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 0 },
      { search_name: "Stacy Vallar",   other_name: "", display_name: "Stacy Vallar",   total_hours: 53.12, ot_hours: 0,    regular_hours: 53.12, tip: 352.98, busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 352.98 },
      { search_name: "Steve",          other_name: "", display_name: "Steve",          total_hours: 88.96, ot_hours: 9.29, regular_hours: 79.67, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 6.83,  bartender_tip: 0, grand_total: 6.83 },
      { search_name: "Steve Nguyen",   other_name: "", display_name: "Steve Nguyen",   total_hours: 0,     ot_hours: 0,    regular_hours: 0,     tip: 229.48, busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 229.48 },
      { search_name: "Tita Romero",    other_name: "", display_name: "Tita Romero",    total_hours: 0,     ot_hours: 0,    regular_hours: 0,     tip: 745.50, busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 745.50 },
      { search_name: "Tita Server",    other_name: "", display_name: "Tita Server",    total_hours: 66.27, ot_hours: 0.85, regular_hours: 65.42, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 0 },
      { search_name: "Wendy Canton",   other_name: "", display_name: "Wendy Canton",   total_hours: 0,     ot_hours: 0,    regular_hours: 0,     tip: 355.51, busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 355.51 },
      { search_name: "Wendy Flores",   other_name: "", display_name: "Wendy Flores",   total_hours: 67.30, ot_hours: 4.35, regular_hours: 62.95, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 39.73, bartender_tip: 0, grand_total: 39.73 },
      { search_name: "Wesley Wong",    other_name: "", display_name: "Wesley Wong",    total_hours: 54.41, ot_hours: 1.30, regular_hours: 53.11, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 74.78, bartender_tip: 0, grand_total: 74.78 },
      { search_name: "Yami Canton",    other_name: "", display_name: "Yami Canton",    total_hours: 0,     ot_hours: 0,    regular_hours: 0,     tip: 94.95,  busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 94.95 },
      { search_name: "Yami Yamileth",  other_name: "", display_name: "Yami Yamileth",  total_hours: 33.21, ot_hours: 0,    regular_hours: 33.21, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 37.38, bartender_tip: 0, grand_total: 37.38 },
      { search_name: "Yiwen Guan",     other_name: "", display_name: "Yiwen Guan",     total_hours: 34.32, ot_hours: 0.55, regular_hours: 33.77, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,     bartender_tip: 0, grand_total: 0 },
      { search_name: "reyna Canton",   other_name: "", display_name: "reyna Canton",   total_hours: 74.97, ot_hours: 12.44,regular_hours: 62.53, tip: 0,      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 103.03,bartender_tip: 0, grand_total: 103.03 },
    ],
    tip_records: [
      { date: "4/27/2026", shift: "Dinner", job: "Server",    name: "Ali Arevalo",    total: 22.35,  subtotal: 390.33, card_tip: 45.70,  gratuity: 0,    sum_tip_gratuity: 45.70,  val: 23.42, tip: 22.28 },
      { date: "4/27/2026", shift: "Dinner", job: "Server",    name: "Jaydyn Perez",   total: 18.90,  subtotal: 340.20, card_tip: 38.10,  gratuity: 0,    sum_tip_gratuity: 38.10,  val: 20.41, tip: 17.69 },
      { date: "4/27/2026", shift: "Dinner", job: "FOH",       name: "zMaster Code",   total: 25.40,  subtotal: 0,      card_tip: 48.23,  gratuity: 0,    sum_tip_gratuity: 48.23,  val: 16.08, tip: 32.15 },
      { date: "4/28/2026", shift: "Lunch",  job: "Server",    name: "Stacy Vallar",   total: 31.60,  subtotal: 548.90, card_tip: 64.80,  gratuity: 0,    sum_tip_gratuity: 64.80,  val: 32.93, tip: 31.87 },
      { date: "4/28/2026", shift: "Dinner", job: "Server",    name: "Tita Romero",    total: 89.14,  subtotal: 1540.0, card_tip: 181.54, gratuity: 0,    sum_tip_gratuity: 181.54, val: 92.40, tip: 89.14 },
      { date: "4/28/2026", shift: "Dinner", job: "FOH",       name: "zMaster Code",   total: 30.10,  subtotal: 0,      card_tip: 57.20,  gratuity: 0,    sum_tip_gratuity: 57.20,  val: 19.07, tip: 38.13 },
    ],
  };
}

// ── Google Sheets data fetcher (production path) ──────────────────────────────

async function fetchPeriodFromSheets(
  spreadsheetId: string,
  period: string,
  token: string
) {
  const range = encodeURIComponent(`'${period}'!A1:Z300`);
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${range}`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!resp.ok) throw new Error(`Sheets API ${resp.status}: ${await resp.text()}`);
  const data = (await resp.json()) as { values?: string[][] };
  return parseSheetValues(period, data.values ?? []);
}

function parseSheetValues(period: string, rows: string[][]) {
  // Minimal parser: find "Search Name" header row, then read Super Sheet block
  const superStart = rows.findIndex((r) => r[0] === "Search Name");
  const employees = [];
  if (superStart !== -1) {
    for (let i = superStart + 1; i < rows.length; i++) {
      const r = rows[i];
      if (!r[0]) break;
      const n = (s: string | undefined) => parseFloat((s ?? "").replace(/[$,]/g, "")) || 0;
      employees.push({
        search_name: r[0] ?? "",
        other_name: r[1] ?? "",
        display_name: r[2] ?? "",
        total_hours: n(r[3]),
        ot_hours: n(r[4]),
        regular_hours: n(r[5]),
        tip: n(r[6]),
        busser_cashier: n(r[7]),
        sushi_tip: n(r[8]),
        kitchen_tip: n(r[9]),
        bartender_tip: n(r[10]),
        grand_total: n(r[11]),
      });
    }
  }

  return {
    period_start: "",
    period_end: period,
    tab_name: period,
    pool: { foh_card_tips: 0, foh_val: 0, t30: 0, total_val_pool: 0, kitchen_pool: 0 },
    employees,
    tip_records: [],
  };
}

// ── JWT / Auth helpers (Web Crypto API – runs natively in Workers) ────────────

async function getServiceAccountToken(saJson: string): Promise<string> {
  const sa = JSON.parse(saJson) as { client_email: string; private_key: string };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/spreadsheets.readonly",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  };
  const jwt = await signJwt(sa.private_key, payload);
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: jwt,
  });
  const resp = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  const d = (await resp.json()) as { access_token: string };
  return d.access_token;
}

function b64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

async function signJwt(pem: string, payload: object): Promise<string> {
  const enc = new TextEncoder();
  const headerB64 = b64url(enc.encode(JSON.stringify({ alg: "RS256", typ: "JWT" })));
  const payloadB64 = b64url(enc.encode(JSON.stringify(payload)));
  const input = `${headerB64}.${payloadB64}`;
  const der = pemToDer(pem);
  const key = await crypto.subtle.importKey(
    "pkcs8", der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false, ["sign"]
  );
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, enc.encode(input));
  return `${input}.${b64url(sig)}`;
}

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}
