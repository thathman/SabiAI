# Sabi Boy V2.4 — Security Review

**Review date:** 2026-08-29  
**Reviewed release:** `v2` at the controlled Dell candidate (the post-review commit is recorded in Phase 16)  
**Scope:** dashboard/API, PWA push surface, runtime configuration, source and bookmaker integrations, and the installed Dell service boundary.

## Result

No critical or high-severity application findings were found in the acceptance review. The service is loopback-bound behind the existing HTTPS edge, API documentation is disabled, state-changing requests are bounded and validated, and the PWA push surface is restricted to same-origin requests and approved Web Push hosts.

This is an application review, not a claim that every host, edge or third-party provider is secure. External routing was not changed during this acceptance.

## Controls verified

- FastAPI Swagger, ReDoc and OpenAPI routes are disabled.
- `TrustedHostMiddleware` restricts accepted host names.
- State-changing request bodies are capped at 16 KiB before parsing.
- Responses set `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS, cross-origin isolation/resource policies, and a restrictive Content Security Policy.
- Push subscription and removal require an allowed dashboard `Origin`, reject cross-site fetches, rate-limit mutations, validate P-256/auth key shapes, and accept only HTTPS endpoints for FCM, Mozilla, Apple or Microsoft push hosts.
- Read-only API and service-worker responses are marked `no-store`; HTML/assets use controlled cache policies.
- Dashboard API-derived values are escaped before insertion into markup. A source scan found no `eval`, `new Function`, `document.write` or equivalent dynamic-code execution in the active dashboard shell.
- No live secret values are tracked in the repository. Runtime environment/key files remain outside Git and are permission-restricted; only placeholder names occur in examples/legacy documentation.
- Removed bookmaker targets (Stake and 1xBet) are absent from the active registry and are rejected by the gateway.

## Documented limitations and follow-up

**SEC-001 — Public read-only data (medium):** the dashboard and read APIs do not require application login. This is intentional for the current read-only deployment, but anyone who can reach the approved URL can view bankroll, picks, source health and related history. If those records must be private, add an authenticated edge/access policy in a separately authorised change window; do not add an unreviewed in-app bypass or change Cloudflare routing during this release.

**SEC-002 — Inline style allowance (low):** the CSP currently permits `style-src 'unsafe-inline'` because the chart renderer emits a small number of inline width styles. Move those values to nonce/hash-backed styles or generated classes in a future hardening change.

**SEC-003 — Edge analytics script (informational):** the current CSP blocks an injected Cloudflare Insights script. This is a safe default; confirm the edge injection is intentional before relaxing CSP.

**SEC-004 — Host process arguments (operational):** the Sabi Boy service and its root-owned Cloudflare credentials were checked for token exposure. Unrelated host tunnel services may still expose their own tokens in process arguments; remediation is outside this release and needs an authorised host-maintenance window.

## Acceptance disposition

The application security gates pass for this candidate. SEC-001 remains the principal product-level limitation and is carried into the release report; no external production cutover is implied by this review.
