# Sabi Boy V2 — Dell Security and Secrets Acceptance

**Review date:** 2026-08-26  
**Scope:** Sabi Boy V2 branch, Dell runtime, read-only dashboard, OpenClaw integration, private environment files and recovery backups.  
**Reviewed candidate:** V2 acceptance line beginning at `b3e666e4f55d6dff3fc28a832e760ca1dc8f803d`; final release evidence must record the later exact tested commit.

## Executive summary

No critical or high-severity issue remains in the reviewed V2 boundary. Two medium dashboard-hardening gaps and one low runtime-permission gap were found and corrected. The installed Python environment reported no known published dependency vulnerabilities. V2 remains a deliberately public, GET-only dashboard; all research, ticket, settlement and Blog writes remain behind the OpenClaw tool boundary rather than the browser API.

## Fixed findings

### SBSEC-001 — Public OpenAPI schema was reachable

- **Rule:** FASTAPI-OPENAPI-001
- **Severity:** Medium
- **Location:** `dashboard/v2_app.py:20` (FastAPI construction) and `dashboard/v2_app.py:106` (UI catch-all).
- **Evidence:** Interactive docs were disabled, but `openapi_url` still used FastAPI's default and the UI catch-all returned the dashboard shell for documentation paths.
- **Impact:** A public caller could enumerate the read-model API surface more easily.
- **Fix:** Set `openapi_url=None` and return 404 for `/docs`, `/redoc` and `/openapi.json` before the SPA shell fallback. Added regression coverage in `tests/test_dashboard_v2_security.py:9`.
- **Status:** Fixed in `b3e666e4f55d6dff3fc28a832e760ca1dc8f803d`.

### SBSEC-002 — Dashboard lacked host validation and browser security headers

- **Rules:** FASTAPI-HOST-001, FASTAPI-HEADERS-001, JS-CSP-001
- **Severity:** Medium
- **Location:** `dashboard/v2_app.py:27` (trusted hosts) and `dashboard/v2_app.py:39` (security-header middleware).
- **Evidence:** Runtime responses had no CSP, clickjacking, MIME-sniffing, referrer or permissions headers, and arbitrary Host values were accepted.
- **Impact:** Defense in depth against host-header abuse, clickjacking and a future browser-injection defect was weaker than required for the public dashboard.
- **Fix:** Added an environment-configurable trusted-host allowlist; CSP with same-origin scripts and no objects/forms/frames; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`; and `no-store` on health/read-model API responses. Added regression coverage in `tests/test_dashboard_v2_security.py:15` and `tests/test_dashboard_v2_security.py:27`.
- **Status:** Fixed in `b3e666e4f55d6dff3fc28a832e760ca1dc8f803d`.

### SBSEC-003 — Private parent directories allowed group/world traversal

- **Rule:** Secrets and backup least-privilege storage.
- **Severity:** Low
- **Location:** Dell runtime directories `~/.config/sabi-boy`, `~/.openclaw/env`, and `~/sabi-boy-migration-archives`.
- **Evidence:** Secret and archive files were already mode 600, but their parent directories were mode 775/755.
- **Impact:** Other local accounts could list or traverse private directory names even though they could not read the protected files.
- **Fix:** Changed the three exact parent directories to mode 700. Verified runtime environment files and archive files remain mode 600; verified V2 backup directories/files remain 700/600.
- **Status:** Fixed on the Dell runtime.

## Verified controls

- The `/api/v2` browser router exposes only GET/HEAD methods; no POST, PUT, PATCH or DELETE route is present.
- The V2 dashboard has no PIN, browser write key or localStorage credential design. Those matches exist only in the legacy V1 dashboard slated for removal.
- API-derived strings passed through V2's HTML templates are escaped; no unescaped user-controlled script URL, navigation, `postMessage`, eval or browser-secret storage path was found.
- Static asset lookup strips path components and serves only existing files from the fixed V2 asset directory.
- SQLite access in the reviewed V2 paths is parameterized. The two dynamic table-name queries use internal fixed table allowlists, not request-controlled identifiers.
- Bookmaker subprocess execution uses argument arrays without `shell=True` and has timeout handling.
- Source adapters call fixed provider base URLs with explicit timeouts. Learned source URLs are persisted as evidence for OpenClaw Browser/Search and are not fetched by the V2 HTTP client.
- Paid sources are disabled in the Dell runtime.
- Secret-pattern review found no committed credential. Candidate matches were shell/code references, test placeholders, or the substring `sk-` inside historical `risk-review` filenames.
- The live Sabi Boy env file and OpenClaw gateway env file are mode 600 inside mode 700 directories. No secret value was printed into acceptance evidence.
- Verified database backups use mode 700 directories and mode 600 manifests/database files. Recovery archives are mode 600 inside mode 700 directories.
- `pip-audit` against the installed V2 site-packages reported: `No known vulnerabilities found`. Reviewed runtime versions were FastAPI 0.141.1, Starlette 1.6.0 and Uvicorn 0.52.4.
- Stake's Cloudflare verification page was not bypassed. No CAPTCHA, authentication or regional control was bypassed during bookmaker testing.

## Boundary notes

- The dashboard is intentionally public and read-only. It displays Sabi Boy's recorded betting history and bankroll figures; this visibility is a product decision, not an authentication control.
- CSP permits inline styles because the dashboard generates numeric chart widths as style attributes. Script execution remains restricted to same-origin external scripts; `unsafe-eval` and inline scripts are not allowed.
- Cloudflare routing and TLS termination are external controls. They were inspected for target continuity but were not edited during this review.
- OpenClaw reports a redundant bundled-plugin-path warning. It is configuration noise, not a demonstrated vulnerability, and was not changed because it is outside the Sabi Boy replacement scope.
