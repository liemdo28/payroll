"""
Consolidated Google API client.

Handles JWT-based service-account auth (uses `rsa` package — works without
the broken system `cryptography` Rust extension).

Supports combined Drive + Sheets scopes and provides a single shared token
for the lifetime of one run.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import rsa

# ── OAuth2 scopes ─────────────────────────────────────────────────────────────
SCOPE_DRIVE_RO  = "https://www.googleapis.com/auth/drive.readonly"
SCOPE_SHEETS_RW = "https://www.googleapis.com/auth/spreadsheets"
_TOKEN_URL      = "https://oauth2.googleapis.com/token"

DEFAULT_SCOPES = [SCOPE_DRIVE_RO, SCOPE_SHEETS_RW]


# ── JWT signing ───────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_jwt(sa: dict, scopes: list[str]) -> str:
    now = int(time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss":   sa["client_email"],
        "scope": " ".join(scopes),
        "aud":   _TOKEN_URL,
        "iat":   now,
        "exp":   now + 3600,
    }).encode())
    signing_input = f"{header}.{payload}".encode()
    try:
        private_key = rsa.PrivateKey.load_pkcs1_openssl_pem(sa["private_key"].encode())
    except Exception as exc:
        raise RuntimeError(f"Cannot parse service-account private key: {exc}") from exc
    sig = rsa.sign(signing_input, private_key, "SHA-256")
    return f"{header}.{payload}.{_b64url(sig)}"


# ── Token exchange ────────────────────────────────────────────────────────────

def get_access_token(key_file: str | Path, scopes: list[str] | None = None) -> str:
    """Load a service-account JSON key and return a short-lived OAuth2 token."""
    key_path = Path(key_file)
    if not key_path.exists():
        raise FileNotFoundError(f"Service-account key not found: {key_path}")
    try:
        sa = json.loads(key_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {key_path}: {exc}") from exc

    jwt_token = _make_jwt(sa, scopes or DEFAULT_SCOPES)
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt_token,
    }).encode()
    req = urllib.request.Request(
        _TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Token exchange failed ({exc.code}): {exc.read().decode()}"
        ) from exc


# ── Shared HTTP helper with retry ─────────────────────────────────────────────

def api_request(
    method: str,
    url: str,
    token: str,
    body: Any = None,
    timeout: int = 30,
    max_retries: int = 4,
) -> Any:
    """
    Call a Google API endpoint; returns parsed JSON.
    Retries on 429 / 5xx with exponential back-off.
    """
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    last_exc: Exception = RuntimeError("no attempts")
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                last_exc = exc
                continue
            raise RuntimeError(
                f"API {method} {url} → {exc.code}: {exc.read().decode()}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                last_exc = exc
                continue
            raise
    raise last_exc
