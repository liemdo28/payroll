/**
 * GET /api/payroll/periods
 *
 * Returns the list of available payroll period tabs from Google Sheets.
 * Falls back to mock data when env vars are not configured.
 */
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  PAYROLL_FILE_ID?: string;
  GOOGLE_SA_JSON?: string;
}

const MOCK_PERIODS = {
  periods: [
    { tab_name: "05-10", period_start: "04/27/2026", period_end: "05/10/2026" },
    { tab_name: "04-26", period_start: "04/13/2026", period_end: "04/26/2026" },
  ],
};

export const onRequestGet: PagesFunction<Env> = async ({ env }) => {
  const headers = {
    "Content-Type": "application/json",
    "Cache-Control": "public, max-age=300",
  };

  if (!env.PAYROLL_FILE_ID || !env.GOOGLE_SA_JSON) {
    return new Response(JSON.stringify(MOCK_PERIODS), { headers });
  }

  try {
    const token = await getServiceAccountToken(env.GOOGLE_SA_JSON);
    const sheets = await listSheetTabs(env.PAYROLL_FILE_ID, token);
    const periods = sheets
      .filter((s) => /^\d{2}-\d{2}$/.test(s.title))
      .map((s) => ({
        tab_name: s.title,
        period_start: "",
        period_end: s.title,
      }));
    return new Response(JSON.stringify({ periods }), { headers });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return new Response(JSON.stringify({ error: msg }), { status: 500, headers });
  }
};

// ── Minimal Google Sheets helpers (no external deps in Workers) ──────────────

async function getServiceAccountToken(saJson: string): Promise<string> {
  const sa = JSON.parse(saJson) as {
    client_email: string;
    private_key: string;
  };

  const now = Math.floor(Date.now() / 1000);
  const payload = { iss: sa.client_email, scope: SHEETS_SCOPE, aud: TOKEN_URL, iat: now, exp: now + 3600 };

  const jwt = await signJwt(sa.private_key, payload);
  const body = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: jwt,
  });
  const resp = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  const data = (await resp.json()) as { access_token: string };
  return data.access_token;
}

async function listSheetTabs(
  spreadsheetId: string,
  token: string
): Promise<{ title: string }[]> {
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?fields=sheets.properties`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  const data = (await resp.json()) as { sheets: { properties: { title: string } }[] };
  return data.sheets.map((s) => ({ title: s.properties.title }));
}

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";

function b64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let str = "";
  for (const b of bytes) str += String.fromCharCode(b);
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

async function signJwt(pemKey: string, payload: object): Promise<string> {
  const header = { alg: "RS256", typ: "JWT" };
  const enc = new TextEncoder();
  const headerB64 = b64url(enc.encode(JSON.stringify(header)));
  const payloadB64 = b64url(enc.encode(JSON.stringify(payload)));
  const signingInput = `${headerB64}.${payloadB64}`;

  const keyDer = pemToDer(pemKey);
  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8",
    keyDer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", cryptoKey, enc.encode(signingInput));
  return `${signingInput}.${b64url(sig)}`;
}

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s/g, "");
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}
