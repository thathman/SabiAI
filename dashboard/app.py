#!/usr/bin/env python3
"""SabiAI — betting analyst dashboard. PWA-ready, mobile-first.

Design: impeccable craft pass — OKLCH warm-amber palette, Fraunces + Hanken Grotesk,
section-based layout (not card soup), tabular-nums throughout, bottom nav for mobile.
4 bet channels: Kelly · Compound chain · Long shot · Live alerts.
All to WhatsApp. Decimal odds, % confidence, plain language.
"""
import os, sys, json as _json, hmac
from fastapi import FastAPI, Response, HTTPException, Header
from fastapi.responses import HTMLResponse, PlainTextResponse

WS = os.path.expanduser("~/.openclaw/workspace")
sys.path.insert(0, f"{WS}/scripts")
import sabiai_data as D

app = FastAPI(title="SabiAI")

# ── Write auth: shared secret for mutating endpoints ──────────────────────────
# Token lives in data/.dashboard_token (created on first boot). The frontend
# stores it in localStorage after PIN unlock and sends it as X-SabiAI-Key.
_TOKEN_FILE = f"{WS}/data/.dashboard_token"
def _write_token() -> str:
    try:
        with open(_TOKEN_FILE) as fh:
            return fh.read().strip()
    except FileNotFoundError:
        import secrets
        tok = secrets.token_hex(16)
        with open(_TOKEN_FILE, "w") as fh:
            fh.write(tok)
        os.chmod(_TOKEN_FILE, 0o600)
        return tok

def _require_key(x_sabiai_key: str):
    if not x_sabiai_key or not hmac.compare_digest(x_sabiai_key, _write_token()):
        raise HTTPException(401, "missing or invalid X-SabiAI-Key")

# ── PWA endpoints ─────────────────────────────────────────────────────────────
@app.get("/manifest.json")
def manifest():
    data = {
        "name": "SabiAI",
        "short_name": "SabiAI",
        "description": "Your AI betting analyst — picks, chain, long shot",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#0c0a07",
        "theme_color": "#e6b252",
        "categories": ["sports", "finance"],
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
        "shortcuts": [
            {"name": "Bet Chain", "url": "/betchain",   "description": "30-day compound chain"},
            {"name": "Long Shot", "url": "/longshot",   "description": "Weekly 1000× slip"},
            {"name": "History",  "url": "/history",    "description": "Settled bets"},
            {"name": "Finance",  "url": "/finance",    "description": "Bankroll & money"},
        ],
    }
    return Response(_json.dumps(data), media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    sw = r"""
const CACHE = 'sabiai-v4';
const SHELL = ['/', '/betchain', '/longshot', '/history', '/diary', '/strategies', '/live', '/finance'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  // Wipe ALL old caches on activate so stale API data never survives a deploy
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // API: network-first — always fetch fresh, no stale cache served first
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request).catch(() => new Response('{}', {headers:{'Content-Type':'application/json'}})));
    return;
  }
  // Shell: network-first with cache fallback
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
"""
    from starlette.responses import Response as SR
    return SR(content=sw.strip(), media_type="text/javascript; charset=utf-8")

@app.get("/favicon.ico")
def favicon():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
<rect width='32' height='32' rx='6' fill='#0c0a07'/>
<text x='16' y='24' font-family='Georgia,serif' font-size='22' font-weight='900'
  fill='#e6b252' text-anchor='middle'>S</text></svg>"""
    return Response(svg.encode(), media_type="image/svg+xml")

@app.get("/icon.svg")
def icon_svg():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'>
<rect width='192' height='192' rx='32' fill='#0c0a07'/>
<text x='96' y='130' font-family='Georgia,serif' font-size='110' font-weight='900'
  fill='#e6b252' text-anchor='middle'>S</text></svg>"""
    return Response(svg.encode(), media_type="image/svg+xml")

def _make_icon_png(size: int) -> bytes:
    """Generate a minimal valid PNG with a dark background + gold 'S' via pixel data."""
    import struct, zlib
    # Simple solid dark-navy square — enough for PWA to show a non-blank icon
    # For a proper "S" letter we'd need a font renderer; this gives a solid branded colour
    bg_r, bg_g, bg_b = 12, 10, 7       # #0c0a07 dark
    ac_r, ac_g, ac_b = 230, 178, 82    # #e6b252 gold
    w = h = size
    # Draw a simple "S" shape as pixel blocks (5×7 grid scaled up)
    S = [
        "011110",
        "100001",
        "100000",
        "011110",
        "000001",
        "100001",
        "011110",
    ]
    cell = max(1, size // 8)
    rows = []
    for y in range(h):
        row = []
        gy = (y - (h - 7*cell)//2) // cell
        for x in range(w):
            gx = (x - (w - 6*cell)//2) // cell
            if 0 <= gy < 7 and 0 <= gx < 6 and S[gy][gx] == '1':
                row += [ac_r, ac_g, ac_b]
            else:
                row += [bg_r, bg_g, bg_b]
        rows.append(b'\x00' + bytes(row))
    raw = b''.join(rows)
    comp = zlib.compress(raw, 9)
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', comp)
           + chunk(b'IEND', b''))
    return png

@app.get("/icon-192.png")
def icon_192():
    return Response(_make_icon_png(192), media_type="image/png")

@app.get("/icon-512.png")
def icon_512():
    return Response(_make_icon_png(512), media_type="image/png")

# ── API ───────────────────────────────────────────────────────────────────────
@app.get("/api/overview")
def api_overview(): return D.overview()

@app.get("/api/by-sport")
def api_by_sport(): return D.by_sport()

@app.get("/api/over-time")
def api_over_time(): return D.over_time()

@app.get("/api/breakdown")
def api_breakdown(): return D.breakdown()

@app.get("/api/markets")
def api_markets(): return D.markets_covered()

@app.get("/api/history")
def api_history(page: int = 1, page_size: int = 25, sport: str = "",
                outcome: str = "", bookmaker: str = "", q: str = ""):
    return D.history_page(page=page, page_size=page_size,
                          sport=sport or None, outcome=outcome or None,
                          bookmaker=bookmaker or None, q=q or None)

@app.get("/api/today")
def api_today(): return D.today()

@app.get("/api/today-settled")
def api_today_settled(): return D.today_settled()

@app.get("/api/diary")
def api_diary(): return D.diary()

@app.get("/api/live-bets")
def api_live(): return D.live_bets()

@app.get("/api/live-history")
def api_live_history(): return D.live_history()

@app.get("/api/insights")
def api_insights(): return D.recent_insights()

@app.get("/api/continuous-bet")
def api_cb(): return D.continuous_bet_streak() or {"streak_status":"idle","streak_day":0}

@app.get("/api/long-shot")
def api_ls(): return D.weekly_long_shot_recent()

@app.get("/api/long-shot/latest")
def api_ls_latest(): return D.weekly_long_shot_latest()

@app.get("/api/long-shot/legs/{ls_id}")
def api_ls_legs(ls_id: int): return D.longshot_legs(ls_id)

@app.get("/api/long-shot/monitor")
def api_ls_monitor():
    import sys as _sys
    _sys.path.insert(0, "/home/hendrix/.openclaw/workspace/scripts")
    try:
        import weekly_long_shot as WLS
        result = WLS.monitor_current()
        return result or {"status": "no_active_slip"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/betchain/history")
def api_chain(): return D.betchain_history()

@app.get("/api/betchain/today")
def api_chain_today(): return D.betchain_today()

@app.post("/api/bets/{bet_id}/select")
def api_select_bet(bet_id: int, x_sabiai_key: str = Header(default="")):
    _require_key(x_sabiai_key)
    result = D.toggle_selected(bet_id, True)
    if not result: raise HTTPException(404, "bet not found")
    return result

@app.post("/api/bets/{bet_id}/deselect")
def api_deselect_bet(bet_id: int, x_sabiai_key: str = Header(default="")):
    _require_key(x_sabiai_key)
    result = D.toggle_selected(bet_id, False)
    if not result: raise HTTPException(404, "bet not found")
    return result

@app.get("/api/write-key")
def api_write_key(pin: str = ""):
    """Exchange the finance PIN for the write token (frontend stores it)."""
    expected_pin = os.environ.get("SABIAI_PIN", "1234")
    if not hmac.compare_digest(pin, expected_pin):
        raise HTTPException(401, "wrong pin")
    return {"key": _write_token()}

@app.get("/api/clv")
def api_clv(): return D.clv_stats()

@app.get("/api/calibration")
def api_calibration(): return D.calibration_curve()

@app.get("/api/bookmaker-pl")
def api_bookmaker_pl(): return D.bookmaker_pl()

@app.get("/health")
def health(): return {"ok": True}

# ── Design tokens & shared CSS ─────────────────────────────────────────────────
TOKENS = """
:root {
  /* Hex fallbacks (for browsers without OKLCH support) */
  --bg:        #0c0a07;
  --bg-raised: #110f09;
  --surface:   #16130c;
  --surface-2: #1c1810;
  --border:    #221e13;
  --border-2:  #2e2919;

  --ink:       #f0ece8;
  --ink-2:     #b8b0a6;
  --ink-3:     #847c72;

  --gold:      #d4a840;
  --gold-dim:  #b38c2e;

  --kelly:     #22a268;
  --compound:  #c97930;
  --longshot:  #8855d4;
  --live:      #d44040;

  --win:       #30b870;
  --loss:      #d44040;
}

/* OKLCH overrides for supporting browsers */
@supports (color: oklch(0% 0 0)) {
:root {
  --bg:        oklch(10% .018 68);
  --bg-raised: oklch(13% .020 68);
  --surface:   oklch(16% .022 68);
  --surface-2: oklch(19% .024 68);
  --border:    oklch(24% .020 68);
  --border-2:  oklch(30% .022 68);

  --ink:       oklch(94% .012 80);
  --ink-2:     oklch(72% .018 75);
  --ink-3:     oklch(52% .018 72);

  --gold:      oklch(78% .145 75);
  --gold-dim:  oklch(65% .110 75);

  --kelly:     oklch(62% .14 155);
  --compound:  oklch(70% .16 65);
  --longshot:  oklch(62% .18 295);
  --live:      oklch(62% .18 22);

  --win:       oklch(68% .15 155);
  --loss:      oklch(62% .18 22);
}}

:root {

  /* Type scale — fixed rem, 1.25 ratio */
  --t-xs:   .75rem;
  --t-sm:   .875rem;
  --t-base: 1rem;
  --t-md:   1.125rem;
  --t-lg:   1.375rem;
  --t-xl:   1.75rem;
  --t-2xl:  2.25rem;
  --t-3xl:  3rem;

  /* Space scale — 4px base */
  --sp-1: .25rem; --sp-2: .5rem; --sp-3: .75rem; --sp-4: 1rem;
  --sp-5: 1.25rem; --sp-6: 1.5rem; --sp-8: 2rem; --sp-10: 2.5rem;
  --sp-12: 3rem; --sp-16: 4rem;
}
"""

BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; -webkit-tap-highlight-color: transparent; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
  font-size: var(--t-base);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  min-height: 100dvh;
}
a { color: inherit; text-decoration: none; }
button { font: inherit; cursor: pointer; border: none; background: none; }
img { display: block; max-width: 100%; }

/* Typography */
.display {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  line-height: 1;
  letter-spacing: -.03em;
  font-optical-sizing: auto;
}
.label {
  font-size: var(--t-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .09em;
  color: var(--ink-3);
}
.num { font-variant-numeric: tabular-nums; }

/* Layout */
.page-wrap {
  max-width: 1120px;
  margin: 0 auto;
  padding: var(--sp-4) var(--sp-4) 96px;
}
@media (min-width: 640px) {
  .page-wrap { padding: var(--sp-6) var(--sp-8) var(--sp-16); }
}
.section { margin-top: var(--sp-10); }
.section-head {
  display: flex;
  align-items: baseline;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}
.section-head h2 {
  font-family: 'Fraunces', Georgia, serif;
  font-size: var(--t-xl);
  font-weight: 600;
  white-space: nowrap;
}
.section-rule {
  flex: 1;
  height: 1px;
  background: var(--border);
}
.grid-2 { display: grid; gap: var(--sp-4); grid-template-columns: repeat(2,1fr); }
.grid-3 { display: grid; gap: var(--sp-4); grid-template-columns: repeat(3,1fr); }
.grid-4 { display: grid; gap: var(--sp-4); grid-template-columns: repeat(4,1fr); }
@media (max-width: 860px) {
  .grid-4 { grid-template-columns: repeat(2,1fr); }
  .grid-3 { grid-template-columns: repeat(2,1fr); }
}
@media (max-width: 540px) {
  .grid-4, .grid-3, .grid-2 { grid-template-columns: 1fr; }
}

/* Surface */
.surface {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: var(--sp-5);
}
.surface-2 {
  background: var(--surface-2);
  border: 1px solid var(--border-2);
  border-radius: 10px;
  padding: var(--sp-4);
}

/* KPI block */
.kpi-block { display: flex; flex-direction: column; gap: var(--sp-2); }
.kpi-value {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  font-size: var(--t-2xl);
  letter-spacing: -.04em;
  font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: var(--t-sm); color: var(--ink-3); font-variant-numeric: tabular-nums; }

/* Channel cards */
.channel-row {
  display: grid;
  gap: var(--sp-3);
  grid-template-columns: repeat(4,1fr);
}
@media (max-width: 860px) { .channel-row { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 480px) {
  .channel-row {
    grid-template-columns: repeat(2,1fr);
    gap: var(--sp-2);
  }
}
.channel {
  border-radius: 16px;
  padding: var(--sp-4) var(--sp-4) var(--sp-5);
  border: 1px solid;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-height: 130px;
  position: relative;
  overflow: hidden;
}
.channel::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: .06;
  pointer-events: none;
}
.ch-kelly   { border-color: oklch(62% .14 155 / .4); background: oklch(13% .025 155); }
.ch-kelly::before { background: var(--kelly); }
.ch-compound{ border-color: oklch(70% .16 65 / .4);  background: oklch(13% .030 65); }
.ch-compound::before { background: var(--compound); }
.ch-longshot{ border-color: oklch(62% .18 295 / .4); background: oklch(13% .025 295); }
.ch-longshot::before { background: var(--longshot); }
.ch-live    { border-color: oklch(62% .18 22 / .4);  background: oklch(13% .025 22); }
.ch-live::before { background: var(--live); }
.channel .ch-label { font-size: var(--t-xs); font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.ch-kelly .ch-label   { color: var(--kelly); }
.ch-compound .ch-label{ color: var(--compound); }
.ch-longshot .ch-label{ color: var(--longshot); }
.ch-live .ch-label    { color: var(--live); }
.channel .ch-big {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  font-size: var(--t-2xl);
  letter-spacing: -.04em;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.channel .ch-sub { font-size: var(--t-sm); color: var(--ink-2); line-height: 1.4; }

/* Pick card */
.pick-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: var(--sp-4);
  background: var(--surface);
  transition: border-color .15s, transform .15s;
}
.pick-card:hover { border-color: var(--border-2); transform: translateY(-1px); }
.pick-card .pick-match { font-weight: 700; font-size: var(--t-md); }
.pick-card .pick-line {
  margin-top: var(--sp-2);
  font-size: var(--t-base);
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--sp-2);
}
.pick-card .pick-odds {
  font-family: 'Fraunces', Georgia, serif;
  font-size: var(--t-xl);
  font-weight: 900;
  color: var(--gold);
  font-variant-numeric: tabular-nums;
}
.pick-card .pick-why {
  margin-top: var(--sp-2);
  font-size: var(--t-sm);
  color: var(--ink-2);
  line-height: 1.55;
}

/* Badges & pills */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: var(--t-xs);
  font-weight: 700;
  letter-spacing: .04em;
  border: 1px solid;
}
.badge-gold    { background: oklch(78% .145 75 / .12); color: var(--gold);    border-color: oklch(78% .145 75 / .3); }
.badge-win     { background: oklch(68% .15 155 / .14); color: var(--win);     border-color: oklch(68% .15 155 / .35); }
.badge-loss    { background: oklch(62% .18 22 / .14);  color: var(--loss);    border-color: oklch(62% .18 22 / .35); }
.badge-pending { background: oklch(52% .018 72 / .1);  color: var(--ink-2);   border-color: oklch(52% .018 72 / .2); }
.badge-model   { background: oklch(62% .14 155 / .1);  color: var(--kelly);   border-color: oklch(62% .14 155 / .3); }
.badge-live    { background: oklch(62% .18 22 / .14);  color: var(--live);    border-color: oklch(62% .18 22 / .35); animation: pulse 1.8s infinite; }

.conf-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.conf-pip {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--border-2);
  flex-shrink: 0;
}
.conf-pip.lit { background: var(--gold); }
.conf-pip.dim { background: var(--ink-3); }

/* Stat row */
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--border);
  font-size: var(--t-sm);
}
.stat-row:last-child { border-bottom: 0; }
.stat-row .sv {
  font-family: 'Fraunces', Georgia, serif;
  font-size: var(--t-lg);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* Bar chart */
.bar-list { display: flex; flex-direction: column; gap: var(--sp-2); }
.bar-item {
  display: grid;
  grid-template-columns: 120px 1fr 52px;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--t-sm);
}
.bar-track {
  height: 8px;
  background: oklch(24% .020 68);
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--gold-dim), var(--gold));
  border-radius: 4px;
  transition: width .4s ease;
}

/* Progress ring */
.ring-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ring-label {
  position: absolute;
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}

/* Day grid */
.day-grid {
  display: grid;
  grid-template-columns: repeat(10,1fr);
  gap: 4px;
  margin: var(--sp-4) 0;
}
.day-cell {
  aspect-ratio: 1;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.day-win    { background: oklch(68% .15 155 / .2);  color: var(--win);      border: 1px solid oklch(68% .15 155 / .4); }
.day-loss   { background: oklch(62% .18 22 / .2);   color: var(--loss);     border: 1px solid oklch(62% .18 22 / .4); }
.day-today  { background: oklch(70% .16 65 / .2);   color: var(--compound); border: 1px solid oklch(70% .16 65 / .5); animation: pulse 2s infinite; }
.day-future { background: transparent;              color: var(--ink-3);    border: 1px solid var(--border); }

/* Code block */
.booking-code {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  background: oklch(62% .18 295 / .1);
  border: 1px solid oklch(62% .18 295 / .4);
  color: oklch(75% .15 295);
  border-radius: 10px;
  padding: var(--sp-2) var(--sp-4);
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: var(--t-md);
  font-weight: 700;
  letter-spacing: .06em;
  cursor: pointer;
  transition: background .15s;
}
.booking-code:hover { background: oklch(62% .18 295 / .18); }

/* Leg item */
.leg-item {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: start;
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
  border-bottom: 1px solid var(--border);
}
.leg-item:last-child { border-bottom: 0; }
.leg-num {
  width: 28px; height: 28px; border-radius: 50%;
  background: oklch(62% .18 295 / .12);
  border: 1px solid oklch(62% .18 295 / .3);
  display: flex; align-items: center; justify-content: center;
  font-size: var(--t-xs); font-weight: 700; color: oklch(75% .15 295);
  flex-shrink: 0;
  margin-top: 2px;
}
.leg-odds-display {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  font-size: var(--t-xl);
  color: var(--gold);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* Table */
table { width: 100%; border-collapse: collapse; font-size: var(--t-sm); font-variant-numeric: tabular-nums; }
th {
  color: var(--ink-3);
  font-weight: 700;
  font-size: var(--t-xs);
  text-transform: uppercase;
  letter-spacing: .09em;
  text-align: left;
  padding: var(--sp-3) var(--sp-3);
  border-bottom: 1px solid var(--border);
}
td {
  padding: var(--sp-3);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
tr:last-child td { border-bottom: 0; }
tr:hover td { background: oklch(16% .022 68 / .5); }

/* Empty state */
.empty {
  text-align: center;
  padding: var(--sp-12) var(--sp-8);
  color: var(--ink-3);
}
.empty .empty-title {
  font-family: 'Fraunces', Georgia, serif;
  font-size: var(--t-xl);
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: var(--sp-2);
}

/* Diary */
.diary-entry {
  padding: var(--sp-5) 0;
  border-bottom: 1px solid var(--border);
}
.diary-entry:last-child { border-bottom: 0; }
.diary-date {
  font-size: var(--t-xs);
  font-weight: 700;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--gold-dim);
  margin-bottom: var(--sp-2);
}
.diary-title {
  font-family: 'Fraunces', Georgia, serif;
  font-size: var(--t-xl);
  font-weight: 600;
  margin-bottom: var(--sp-3);
}
.diary-body { color: var(--ink-2); line-height: 1.7; white-space: pre-wrap; }

/* Sparkline chart */
.chart-wrap { width: 100%; overflow: hidden; }
svg text { font-family: 'Hanken Grotesk', system-ui, sans-serif; }

/* Header */
.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: oklch(10% .018 68 / .88);
  backdrop-filter: blur(12px) saturate(1.5);
  -webkit-backdrop-filter: blur(12px) saturate(1.5);
  border-bottom: 1px solid var(--border);
  padding: 0 var(--sp-4);
}
.header-inner {
  max-width: 1120px;
  margin: 0 auto;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}
.brand-name {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  font-size: var(--t-xl);
  letter-spacing: -.03em;
}
.brand-name .ai { color: var(--gold); }
.brand-tag {
  font-size: var(--t-xs);
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-3);
}
/* Desktop nav */
.desk-nav { display: flex; gap: var(--sp-1); }
.desk-nav a {
  padding: var(--sp-2) var(--sp-4);
  border-radius: 999px;
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--ink-3);
  border: 1px solid transparent;
  transition: color .15s, background .15s;
  white-space: nowrap;
}
.desk-nav a:hover { color: var(--ink); }
.desk-nav a.active {
  color: var(--bg);
  background: var(--gold);
  border-color: var(--gold);
}
@media (max-width: 640px) { .desk-nav { display: none; } }

/* Bottom nav (mobile PWA) */
.bottom-nav {
  display: none;
  position: fixed;
  bottom: 0; left: 0; right: 0;
  z-index: 20;
  background: oklch(10% .018 68 / .92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-top: 1px solid var(--border);
  padding: var(--sp-1) 0;
  padding-bottom: env(safe-area-inset-bottom, 0);
}
.bottom-nav-inner {
  display: flex;
  justify-content: space-around;
}
.bottom-nav a {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: var(--sp-2) var(--sp-3);
  color: var(--ink-3);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  min-width: 48px;
  border-radius: 10px;
  transition: color .15s, background .15s;
}
.bottom-nav a:hover { color: var(--ink); background: oklch(16% .022 68); }
.bottom-nav a.active { color: var(--gold); }
.bottom-nav svg { width: 22px; height: 22px; stroke-width: 1.8; }
@media (max-width: 640px) { .bottom-nav { display: block; } }

/* Pulse animation */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.55} }
@keyframes rise { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
.rise { animation: rise .4s both; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 3px; }

/* Focus */
:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; border-radius: 4px; }

/* SVG charts */
.area-path { fill: url(#area-grad); }
.line-path  { fill: none; stroke: var(--gold); stroke-width: 2px; stroke-linecap: round; }

/* ──────────────────────────────────────────────────────────────────────────
   Dense ProphetAI-inspired layout classes
   ────────────────────────────────────────────────────────────────────────── */
.stats-strip {
  display: grid; grid-template-columns: repeat(5, 1fr);
  border: 1px solid var(--border); border-radius: 12px;
  overflow: hidden; margin: var(--sp-3) 0 var(--sp-6);
}
.stat-cell { padding: var(--sp-4); border-right: 1px solid var(--border); }
.stat-cell:last-child { border-right: 0; }
.sc-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .09em; color: var(--ink-3); margin-bottom: var(--sp-2); }
.sc-val { font-family: 'Fraunces',Georgia,serif; font-size: var(--t-xl); font-weight: 900; font-variant-numeric: tabular-nums; letter-spacing: -.02em; line-height: 1; margin-bottom: 4px; }
.sc-sub { font-size: 10px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
@media (max-width: 900px) {
  .stats-strip { grid-template-columns: repeat(3, 1fr); }
  .stat-cell:nth-child(3) { border-right: 0; }
  .stat-cell:nth-child(4), .stat-cell:nth-child(5) { border-top: 1px solid var(--border); }
  .stat-cell:nth-child(5) { border-right: 0; }
}
@media (max-width: 480px) {
  .stats-strip { grid-template-columns: repeat(2, 1fr); }
  .stat-cell { border-top: 1px solid var(--border); }
  .stat-cell:nth-child(odd) { border-right: 1px solid var(--border); }
  .stat-cell:nth-child(even) { border-right: 0; }
  .stat-cell:nth-child(1), .stat-cell:nth-child(2) { border-top: 0; }
}
.content-grid { display: grid; grid-template-columns: 1fr 300px; gap: var(--sp-8); align-items: start; }
@media (max-width: 960px) { .content-grid { grid-template-columns: 1fr 255px; gap: var(--sp-5); } }
@media (max-width: 700px) { .content-grid { grid-template-columns: 1fr; } .content-sidebar { order: -1; } }
.ch-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--sp-2); margin-bottom: var(--sp-6); }
.ch-strip-item { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; text-decoration: none; color: inherit; transition: border-color .15s; }
.ch-strip-item:hover { border-color: var(--border-2); }
.csi-lbl { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .09em; }
.csi-val { font-family: 'Fraunces',Georgia,serif; font-weight: 900; font-size: var(--t-lg); font-variant-numeric: tabular-nums; line-height: 1.1; letter-spacing: -.02em; }
.csi-sub { font-size: 10px; color: var(--ink-3); line-height: 1.4; }
@media (max-width: 480px) { .ch-strip { grid-template-columns: repeat(2, 1fr); } }
.sec-head { display: flex; align-items: center; justify-content: space-between; padding-bottom: var(--sp-3); border-bottom: 1px solid var(--border); }
.sec-lbl { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .09em; color: var(--ink-3); }
.sec-meta { font-size: 10px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.list-sec { margin-bottom: var(--sp-8); }
.pick-row { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--sp-3); padding: 12px 0; border-bottom: 1px solid var(--border); }
.pick-row:last-child { border-bottom: 0; }
.pr-left { min-width: 0; flex: 1; }
.pr-match { font-weight: 700; font-size: var(--t-sm); display: flex; align-items: baseline; gap: var(--sp-2); overflow: hidden; }
.pr-match-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pr-sport { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-3); flex-shrink: 0; }
.pr-pick { font-size: var(--t-sm); color: var(--ink-2); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pr-pick strong { color: var(--ink); }
.pr-meta { font-size: 10px; color: var(--ink-3); margin-top: 3px; display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
.pr-why { font-size: 10px; color: var(--ink-3); line-height: 1.5; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.pr-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.pr-odds { font-family: 'Fraunces',Georgia,serif; font-weight: 900; font-size: var(--t-lg); color: var(--gold); font-variant-numeric: tabular-nums; line-height: 1; }
.pr-conf { font-size: 10px; color: var(--ink-3); }
.result-row { display: flex; align-items: center; gap: var(--sp-3); padding: 9px 0; border-bottom: 1px solid var(--border); font-size: var(--t-sm); }
.result-row:last-child { border-bottom: 0; }
.res-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.rd-win { background: var(--win); }
.rd-loss { background: var(--loss); }
.res-match { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.res-pick { color: var(--ink-3); font-size: var(--t-xs); flex-shrink: 0; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.res-odds { color: var(--gold); font-variant-numeric: tabular-nums; flex-shrink: 0; font-family: 'Fraunces',serif; font-weight: 700; }
.res-out { font-size: var(--t-xs); font-weight: 700; text-transform: uppercase; flex-shrink: 0; }
.ro-win { color: var(--win); } .ro-loss { color: var(--loss); }
.content-sidebar { display: flex; flex-direction: column; gap: var(--sp-3); }
.sb-block { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.sb-head { padding: 9px var(--sp-4); border-bottom: 1px solid var(--border); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .09em; color: var(--ink-3); display: flex; align-items: center; justify-content: space-between; }
.sb-link { color: var(--gold); font-weight: 600; text-decoration: none; }
.sb-body { padding: var(--sp-3) var(--sp-4); }
.sb-row { display: flex; align-items: center; gap: var(--sp-2); padding: 5px 0; border-bottom: 1px solid var(--border); font-size: var(--t-xs); }
.sb-row:last-child { border-bottom: 0; }
.sb-row-lbl { width: 80px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink-2); }
.sb-bar { flex: 1; height: 3px; background: var(--border); border-radius: 2px; overflow: hidden; }
.sb-bar-fill { height: 100%; background: linear-gradient(90deg, var(--gold-dim), var(--gold)); border-radius: 2px; }
.sb-row-stat { width: 72px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; color: var(--ink-3); line-height: 1.3; }
.sb-kv { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: var(--t-xs); }
.sb-kv:last-child { border-bottom: 0; }
.sb-kv-k { color: var(--ink-3); text-transform: uppercase; letter-spacing: .06em; font-size: 9px; font-weight: 600; }
.sb-kv-v { font-variant-numeric: tabular-nums; font-weight: 700; font-size: var(--t-sm); }
"""

FONTS = """<link rel=preconnect href=https://fonts.googleapis.com>
<link rel=preconnect href=https://fonts.gstatic.com crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel=stylesheet>"""

PWA_META = """<meta name=theme-color content="#e6b252">
<meta name=apple-mobile-web-app-capable content=yes>
<meta name=apple-mobile-web-app-status-bar-style content=black-translucent>
<meta name=apple-mobile-web-app-title content=SabiAI>
<link rel=apple-touch-icon href=/icon-192.png>
<link rel=manifest href=/manifest.json>"""

SW_REGISTER = """<script>
if('serviceWorker' in navigator){
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));
}
</script>"""

ICONS_SVG = {
    "home":       '<path stroke-linecap="round" stroke-linejoin="round" d="M3 12l9-9 9 9M4.5 10.5V21h5v-5h5v5h5V10.5"/>',
    "chain":      '<path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>',
    "longshot":   '<path stroke-linecap="round" stroke-linejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"/>',
    "history":    '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    "diary":      '<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/>',
    "strategies": '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6"/>',
    "live":       '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"/>',
}

def nav_icon(name):
    return f'<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">{ICONS_SVG.get(name,"")}</svg>'

JS_SHARED = """
const f = u => fetch(u).then(r => r.json());
const NGN = '₦';
const ngn = x => NGN + Math.round(Math.abs(x)).toLocaleString();
const oStr = x => x ? parseFloat(x).toFixed(2) : '—';
const pStr = x => x != null ? x + '%' : '—';
const sign = x => (x >= 0 ? '+' : '-') + ngn(x);

function confPips(pct) {
  const n = Math.round((pct || 0) / 20);
  let s = '<span class=conf-bar>';
  for (let i = 1; i <= 5; i++) s += `<span class="conf-pip ${i <= n ? 'lit' : 'dim'}"></span>`;
  return s + '</span>';
}

function ring(pct, label, size, color) {
  const r = size * .38, cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  const dash = Math.max(0, Math.min(100, pct)) / 100 * circ;
  return `<div class=ring-wrap style="width:${size}px;height:${size}px">
    <svg viewBox="0 0 ${size} ${size}">
      <circle cx=${cx} cy=${cy} r=${r} fill=none stroke="oklch(24% .020 68)" stroke-width="${size*.09}"/>
      <circle cx=${cx} cy=${cy} r=${r} fill=none stroke="${color||'var(--compound)'}" stroke-width="${size*.09}"
        stroke-dasharray="${dash} ${circ}" stroke-dashoffset="${circ*.25}" stroke-linecap=round/>
    </svg>
    <div class=ring-label style="font-size:${size*.13}px">${label}</div>
  </div>`;
}

function sparkline(data, key, h) {
  if (!data || !data.length) return '<div class=empty style="padding:2rem"><p>No data yet</p></div>';
  const w = 900, p = 8;
  const vals = data.map(d => d[key]);
  const mn = Math.min(...vals, 0), mx = Math.max(...vals, .01);
  const rng = (mx - mn) || 1;
  const X = i => p + i * (w - 2*p) / Math.max(1, data.length - 1);
  const Y = v => h - p - (v - mn) / rng * (h - 2*p);
  const pts = data.map((d, i) => X(i) + ',' + Y(d[key]));
  const ln = 'M' + pts.join(' L');
  const ar = ln + ` L${X(data.length-1)},${h-p} L${X(0)},${h-p} Z`;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio=none style="width:100%;height:${h*.22}px">
    <defs><linearGradient id=area-grad x1=0 y1=0 x2=0 y2=1>
      <stop offset=0% stop-color="var(--gold)" stop-opacity=.45/>
      <stop offset=100% stop-color="var(--gold)" stop-opacity=0/>
    </linearGradient></defs>
    <path class=area-path d="${ar}"/>
    <path class=line-path d="${ln}"/>
  </svg>`;
}
"""

def shell(title, nav_active, body, extra_head=""):
    links = [
        ("home",       "/",             "Home",       "home"),
        ("betchain",   "/betchain",     "Chain",      "chain"),
        ("longshot",   "/longshot",     "Shot",       "longshot"),
        ("history",    "/history",      "History",    "history"),
        ("diary",      "/diary",        "Diary",      "diary"),
        ("strategies", "/strategies",   "Strategy",   "strategies"),
        ("live",       "/live",          "Live",       "live"),
    ]
    desk = "".join(
        f'<a href="{href}" class="{"active" if k==nav_active else ""}">{label}</a>'
        for k,href,label,_ in links)
    bottom = "".join(
        f'<a href="{href}" class="{"active" if k==nav_active else ""}">{nav_icon(ico)}<span>{label}</span></a>'
        for k,href,label,ico in links)
    return f"""<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>SabiAI — {title}</title>
<meta name="description" content="SabiAI — your personal AI betting analyst. Picks, compound chain, long shot, history and diary at a glance.">
<link rel="icon" href="/favicon.ico" type="image/svg+xml">
{FONTS}
{PWA_META}
{extra_head}
<style>{TOKENS}{BASE_CSS}</style>
</head>
<body>
<header class=site-header>
  <div class=header-inner>
    <div class=brand>
      <span class=brand-name>Sabi<span class=ai>AI</span></span>
      <span class=brand-tag>knows ball</span>
    </div>
    <nav class=desk-nav>{desk}</nav>
  </div>
</header>
<main class=page-wrap>
{body}
</main>
<nav class=bottom-nav>
  <div class=bottom-nav-inner>{bottom}</div>
</nav>
{SW_REGISTER}
</body>
</html>"""

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home():
    body = """
<!-- Page title + status -->
<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--sp-3);padding:var(--sp-4) 0 var(--sp-2)">
  <div>
    <h1 class=display style="font-size:var(--t-2xl);letter-spacing:-.03em">Performance <span style="color:var(--gold)">Dashboard</span></h1>
    <p id=hero-date style="font-size:var(--t-xs);color:var(--ink-3);margin-top:4px;font-variant-numeric:tabular-nums"></p>
  </div>
  <div style="display:flex;align-items:center;gap:var(--sp-3)">
    <span id=hero-pending style="font-size:var(--t-xs);color:var(--ink-3);font-variant-numeric:tabular-nums"></span>
    <span class="badge badge-live" style="font-size:9px">LIVE</span>
  </div>
</div>

<!-- 5-column stats strip -->
<div class=stats-strip>
  <div class=stat-cell>
    <div class=sc-label>Bankroll</div>
    <div class=sc-val id=sc-bank style="color:var(--gold)">—</div>
    <div class=sc-sub id=sc-bank-sub>started ₦—</div>
  </div>
  <div class=stat-cell>
    <div class=sc-label>Net P&amp;L</div>
    <div class=sc-val id=sc-pnl>—</div>
    <div class=sc-sub id=sc-roi>—</div>
  </div>
  <div class=stat-cell>
    <div class=sc-label>Record</div>
    <div class=sc-val id=sc-record>—</div>
    <div class=sc-sub id=sc-winrate>—</div>
  </div>
  <div class=stat-cell>
    <div class=sc-label>Streak</div>
    <div class=sc-val id=sc-streak>—</div>
    <div class=sc-sub id=sc-streak-sub>current run</div>
  </div>
  <div class=stat-cell>
    <div class=sc-label>Open bets</div>
    <div class=sc-val id=sc-open>—</div>
    <div class=sc-sub>pending settlement</div>
  </div>
</div>

<!-- Main 2-col grid -->
<div class=content-grid>

  <!-- ── Left: picks + results ─────────────────────────── -->
  <div>
    <!-- Channel strip -->
    <div class=ch-strip id=ch-strip></div>

    <!-- Today's picks -->
    <div class=list-sec>
      <div class=sec-head>
        <span class=sec-lbl>Today's picks</span>
        <span class=sec-meta id=picks-meta></span>
      </div>
      <div id=today-picks></div>
    </div>

    <!-- Settled today -->
    <div class=list-sec id=settled-section style="display:none">
      <div class=sec-head>
        <span class=sec-lbl>Settled today</span>
        <span class=sec-meta id=settled-meta></span>
      </div>
      <div id=settled-rows></div>
    </div>

    <!-- Live alerts -->
    <div class=list-sec id=live-section style="display:none">
      <div class=sec-head>
        <span class=sec-lbl>Live alerts</span>
        <span class="badge badge-live" style="font-size:9px">LIVE</span>
      </div>
      <div id=live-rows></div>
    </div>
  </div>

  <!-- ── Right sidebar ─────────────────────────────────── -->
  <aside class=content-sidebar>

    <!-- Bankroll chart -->
    <div class=sb-block>
      <div class=sb-head>Bankroll trend</div>
      <div class=sb-body id=sb-chart></div>
    </div>

    <!-- Compound chain -->
    <div class=sb-block>
      <div class=sb-head>Compound chain <a href=/betchain class=sb-link>detail →</a></div>
      <div class=sb-body id=sb-chain></div>
    </div>

    <!-- By sport -->
    <div class=sb-block>
      <div class=sb-head>By sport</div>
      <div class=sb-body id=sb-sport></div>
    </div>

    <!-- Confidence calibration -->
    <div class=sb-block>
      <div class=sb-head title="Win rate vs stated confidence — how accurate the model is">Confidence calibration</div>
      <div class=sb-body id=sb-conf></div>
    </div>

    <!-- Markets -->
    <div class=sb-block>
      <div class=sb-head>Markets covered</div>
      <div class="sb-body" id=sb-markets style="display:flex;flex-wrap:wrap;gap:var(--sp-2)"></div>
    </div>

    <!-- Latest insight -->
    <div class=sb-block id=sb-insight-block style="display:none">
      <div class=sb-head>Latest insight</div>
      <div class=sb-body id=sb-insight></div>
    </div>

  </aside>
</div>

<script>""" + JS_SHARED + r"""

// ── Shared fetches (each called once) ──────────────────────────────────────
const todayP        = f('/api/today').catch(()=>[]);
const overviewP     = f('/api/overview').catch(()=>({}));
const cbP           = f('/api/continuous-bet').catch(()=>({}));
const lsP           = f('/api/long-shot/latest').catch(()=>({}));
const liveP         = f('/api/live-bets').catch(()=>[]);
const settledTodayP = f('/api/today-settled').catch(()=>[]);

// ── Date/status line ────────────────────────────────────────────────────────
const _d = new Date();
const _days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const _mons = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
document.getElementById('hero-date').textContent =
  `${_days[_d.getDay()]} ${_d.getDate()} ${_mons[_d.getMonth()]} ${_d.getFullYear()} · Lagos (UTC+1)`;

// ── Stats strip ─────────────────────────────────────────────────────────────
overviewP.then(o => {
  const w=o.won||0, l=o.lost||0, n=w+l, pu=o.profit_units;
  const profit=o.profit||0;
  const bank=o.bankroll_current;

  document.getElementById('sc-bank').textContent = bank!=null ? ngn(bank) : '—';
  document.getElementById('sc-bank-sub').textContent = `started ${ngn(o.bankroll_start||0)}`;

  document.getElementById('sc-pnl').textContent = profit!=0 ? (profit>=0?'+':'-')+ngn(Math.abs(profit)) : '₦0';
  document.getElementById('sc-pnl').style.color = profit>0?'var(--win)':profit<0?'var(--loss)':'var(--ink)';
  document.getElementById('sc-roi').textContent = o.roi_pct!=null?(o.roi_pct>=0?'+':'')+o.roi_pct+'% ROI':'—';

  document.getElementById('sc-record').textContent = n ? `${w}W – ${l}L` : '0 – 0';
  document.getElementById('sc-winrate').textContent = o.win_rate!=null ? o.win_rate+'% win rate' : 'no settled bets yet';

  const sk=o.streak||0;
  document.getElementById('sc-streak').textContent = sk ? sk+(o.streak_kind==='win'?'W':'L') : '—';
  document.getElementById('sc-streak-sub').textContent = sk ? (o.streak_kind==='win'?'wins in a row':'losses in a row') : 'no streak yet';

  document.getElementById('sc-open').textContent = o.pending||0;
  document.getElementById('hero-pending').textContent = `${o.pending||0} pending · ${n} settled`;
});

// ── Channel strip ───────────────────────────────────────────────────────────
Promise.all([cbP, lsP, todayP, liveP]).then(([cb, ls, today, live]) => {
  const day=cb.streak_day||0, stake=cb.current_stake||1000, wins=cb.streak_wins||0;
  const strong=today.filter(p=>p.confidence_pct>=67).length;
  const avgOdds=today.length?(today.reduce((s,p)=>s+(parseFloat(p.odds)||0),0)/today.length).toFixed(2):'—';
  const liveN=(live||[]).filter(l=>!l.result&&l.status!=='settled').length;
  const lo=cb.last_outcome;
  // Restrategy countdown: chain is on a 7-day break after a loss
  const inBreak = cb.streak_status==='restrategy' && cb.restrategy_until;
  let breakDays = 0;
  if (inBreak) {
    breakDays = Math.max(0, Math.ceil((new Date(cb.restrategy_until+'T00:00:00Z') - new Date()) / 86400000));
  }
  const chainVal = inBreak ? (breakDays>0?`${breakDays}d break`:'Restart today') : `Day ${day}`;
  const chainSub = inBreak ? `back ${cb.restrategy_until} · ₦${Math.round(stake).toLocaleString()} ready`
    :lo==='win'?`Last: WIN · ${ngn(cb.amount_won||0)}`
    :lo==='loss'?'Last: LOSS · reset'
    :`${wins} win${wins!==1?'s':''} banked`;

  document.getElementById('ch-strip').innerHTML = `
    <a class=ch-strip-item href=/ style="border-color:oklch(62% .14 155 / .3);background:oklch(13% .025 155 / .5)">
      <div class=csi-lbl style="color:var(--kelly)">Kelly picks</div>
      <div class=csi-val>${today.length||0}</div>
      <div class=csi-sub>${strong} high-conf · avg ${avgOdds}</div>
    </a>
    <a class=ch-strip-item href=/betchain style="border-color:oklch(70% .16 65 / .3);background:oklch(13% .030 65 / .5)">
      <div class=csi-lbl style="color:var(--compound)">Compound</div>
      <div class=csi-val>${chainVal}</div>
      <div class=csi-sub>${chainSub}</div>
    </a>
    <a class=ch-strip-item href=/longshot style="border-color:oklch(62% .18 295 / .3);background:oklch(13% .025 295 / .5)">
      <div class=csi-lbl style="color:var(--longshot)">Long shot</div>
      <div class=csi-val>${ls&&ls.combined_odds?Math.round(ls.combined_odds).toLocaleString()+'×':'Mon'}</div>
      <div class=csi-sub>${ls&&ls.slip_code?ls.slip_code:'₦100 · builds Monday'}</div>
    </a>
    <div class=ch-strip-item style="border-color:oklch(62% .18 22 / .3);background:oklch(13% .025 22 / .5)">
      <div class=csi-lbl style="color:var(--live)">Live alerts</div>
      <div class=csi-val>${liveN}</div>
      <div class=csi-sub>Hourly 10am–midnight</div>
    </div>`;
});

// ── Today's picks (flat rows) ───────────────────────────────────────────────
function renderPickRow(p, onToggle) {
  const conf = p.confidence_pct;
  const confColor = conf>=67?'var(--win)':conf>=58?'var(--gold)':'var(--ink-3)';
  const isCompound = p.bet_type&&p.bet_type!=='singles'&&p.bet_type!=='';
  const sel = !!p.selected;
  const rowStyle = sel ? '' : 'opacity:0.55;';
  const btnId = `sel-btn-${p.id}`;
  return `<div class=pick-row id="pick-row-${p.id}" style="${rowStyle}">
    <div class=pr-left>
      <div class=pr-match>
        <span class=pr-match-name>${p.match||''}</span>
        ${p.sport?`<span class=pr-sport>${p.sport}</span>`:''}
        ${sel?`<span style="font-size:9px;color:var(--win);font-weight:700;flex-shrink:0">PLACED</span>`:`<span style="font-size:9px;color:var(--ink-3);font-weight:600;flex-shrink:0">model only</span>`}
      </div>
      <div class=pr-pick><strong>${p.plain_pick||p.pick||''}</strong>${(!p.plain_pick&&p.market)?` · ${p.market}`:''}</div>
      <div class=pr-meta>
        ${conf!=null?`<span style="color:${confColor};font-weight:700">${conf}% confidence</span>`:''}
        ${p.kickoff?`<span>⏰ ${p.kickoff.slice(11,16)} UTC</span>`:''}
        ${isCompound?`<span class="badge badge-pending" style="font-size:9px;text-transform:capitalize">${p.bet_type}</span>`:''}
      </div>
      ${p.plain_rationale?`<div class=pr-why>${p.plain_rationale}</div>`:''}
    </div>
    <div class=pr-right style="gap:6px">
      <div class=pr-odds>${oStr(p.odds)}</div>
      ${conf!=null?`<div class=pr-conf>${confPips(conf)}</div>`:''}
      <button id="${btnId}" onclick="toggleSelect(${p.id},${sel?'false':'true'})"
        style="font-size:10px;font-weight:700;padding:4px 8px;border-radius:6px;border:1px solid;cursor:pointer;
               background:${sel?'oklch(20% .03 140 / .8)':'oklch(62% .18 140 / .15)'};
               color:${sel?'var(--win)':'oklch(62% .18 140)'};
               border-color:${sel?'oklch(62% .18 140 / .4)':'oklch(62% .18 140 / .3)'};
               min-width:56px">
        ${sel?'✓ Placed':'Place'}
      </button>
    </div>
  </div>`;
}

async function getWriteKey() {
  let key = localStorage.getItem('sabiai_write_key');
  if (key) return key;
  const pin = prompt('Enter PIN to confirm placing bets:');
  if (!pin) return null;
  const r = await fetch('/api/write-key?pin=' + encodeURIComponent(pin));
  if (!r.ok) { alert('Wrong PIN'); return null; }
  key = (await r.json()).key;
  localStorage.setItem('sabiai_write_key', key);
  return key;
}

async function toggleSelect(id, placing) {
  const url = placing ? `/api/bets/${id}/select` : `/api/bets/${id}/deselect`;
  const btn = document.getElementById(`sel-btn-${id}`);
  if (btn) btn.disabled = true;
  try {
    const key = await getWriteKey();
    if (!key) throw new Error('no key');
    let res = await fetch(url, {method:'POST', headers:{'X-SabiAI-Key': key}});
    if (res.status === 401) {
      localStorage.removeItem('sabiai_write_key');
      const k2 = await getWriteKey();
      if (!k2) throw new Error('no key');
      res = await fetch(url, {method:'POST', headers:{'X-SabiAI-Key': k2}});
    }
    if (!res.ok) throw new Error('failed');
    const d = await res.json();
    const row = document.getElementById(`pick-row-${id}`);
    if (row) {
      const newSel = d.selected;
      row.style.opacity = newSel ? '' : '0.55';
      const b = document.getElementById(`sel-btn-${id}`);
      if (b) {
        b.textContent = newSel ? '✓ Placed' : 'Place';
        b.style.background = newSel ? 'oklch(20% .03 140 / .8)' : 'oklch(62% .18 140 / .15)';
        b.style.color = newSel ? 'var(--win)' : 'oklch(62% .18 140)';
        b.onclick = () => toggleSelect(id, !newSel);
        b.disabled = false;
      }
      // update PLACED/model-only badge
      const nameRow = row.querySelector('.pr-match');
      if (nameRow) {
        const old = nameRow.querySelector('span:last-child');
        if (old && (old.textContent.includes('PLACED') || old.textContent.includes('model'))) {
          old.textContent = newSel ? 'PLACED' : 'model only';
          old.style.color = newSel ? 'var(--win)' : 'var(--ink-3)';
        }
      }
    }
  } catch(e) {
    if (btn) btn.disabled = false;
  }
}

todayP.then(picks => {
  const meta = document.getElementById('picks-meta');
  const el   = document.getElementById('today-picks');
  if (!picks.length) {
    meta.textContent = '0 picks';
    el.innerHTML = `<p style="font-size:var(--t-sm);color:var(--ink-3);padding:var(--sp-5) 0">No picks yet today. Daily scan runs at 8am Lagos time.</p>`;
    return;
  }
  const placed = picks.filter(p=>p.selected).length;
  const strong = picks.filter(p=>p.selected&&p.confidence_pct>=67).length;
  meta.textContent = `${picks.length} picks · ${placed} placed · ${strong} high-conf`;
  el.innerHTML = picks.map(p => renderPickRow(p)).join('');
});

// ── Settled today ───────────────────────────────────────────────────────────
settledTodayP.then(rows => {
  const sec = document.getElementById('settled-section');
  if (!rows.length) { sec.style.display='none'; return; }
  sec.style.display='';
  const wins=rows.filter(r=>r.outcome==='win').length;
  const losses=rows.filter(r=>r.outcome==='loss').length;
  document.getElementById('settled-meta').textContent = `${wins}W · ${losses}L`;
  document.getElementById('settled-rows').innerHTML = rows.map(r=>`
    <div class=result-row>
      <div class="res-dot ${r.outcome==='win'?'rd-win':'rd-loss'}"></div>
      <div class=res-match>${r.match||''}</div>
      <div class=res-pick>${r.plain_pick||r.pick||''}</div>
      <div class=res-odds>${oStr(r.odds)}</div>
      <div class="res-out ${r.outcome==='win'?'ro-win':'ro-loss'}">${r.outcome==='win'?'WON':'LOST'}</div>
    </div>`).join('');
});

// ── Live alerts ─────────────────────────────────────────────────────────────
liveP.then(live => {
  const active=(live||[]).filter(l=>!l.result&&l.status!=='settled');
  const sec=document.getElementById('live-section');
  if (!active.length) { sec.style.display='none'; return; }
  sec.style.display='';
  document.getElementById('live-rows').innerHTML = active.slice(0,5).map(l=>`
    <div class=pick-row style="border-color:oklch(62% .18 22 / .35)">
      <div class=pr-left>
        <div class=pr-match>
          <span class="badge badge-live" style="font-size:9px;margin-right:4px">LIVE</span>
          <span class=pr-match-name>${l.match||''}</span>
          ${l.sport?`<span class=pr-sport>${l.sport}</span>`:''}
        </div>
        <div class=pr-pick><strong>${l.pick||''}</strong>${l.market?` · ${l.market}`:''}</div>
        ${l.plain_rationale?`<div class=pr-why>${l.plain_rationale}</div>`:''}
      </div>
      <div class=pr-right><div class=pr-odds>${oStr(l.odds)}</div></div>
    </div>`).join('');
});

// ── Sidebar: bankroll chart ─────────────────────────────────────────────────
f('/api/over-time').catch(()=>({})).then(d => {
  const profitData=d.cumulative_profit||[], bankData=d.bankroll||[];
  const el=document.getElementById('sb-chart');
  if (profitData.length) {
    el.innerHTML=`<p style="font-size:9px;color:var(--ink-3);margin-bottom:var(--sp-2)">Cumulative profit (units)</p>`+sparkline(profitData,'units',320);
  } else if (bankData.length) {
    el.innerHTML=`<p style="font-size:9px;color:var(--ink-3);margin-bottom:var(--sp-2)">Bankroll balance (₦)</p>`+sparkline(bankData,'balance',320);
  } else {
    el.innerHTML=`<p style="font-size:var(--t-xs);color:var(--ink-3)">Chart appears after first settled bets.</p>`;
  }
});

// ── Sidebar: compound chain ─────────────────────────────────────────────────
cbP.then(cb => {
  const day=cb.streak_day||0, wins=cb.streak_wins||0, mult=cb.running_mult||1;
  const stake=cb.current_stake||1000, amt=cb.amount_won||0;
  const statusMap={idle:'Idle',active:'Active',won_30day:'Cycle complete 🎯',
    restrategy:`7-day rest${cb.restrategy_until?' until '+cb.restrategy_until:''}`,broken:'Reset'};
  const lo=cb.last_outcome;
  document.getElementById('sb-chain').innerHTML=`
    <div class=sb-kv>
      <div class=sb-kv-k>Status</div>
      <div class=sb-kv-v>${statusMap[cb.streak_status]||cb.streak_status||'—'}</div>
    </div>
    <div class=sb-kv>
      <div class=sb-kv-k>Day</div>
      <div class=sb-kv-v>${day} / 30</div>
    </div>
    <div class=sb-kv>
      <div class=sb-kv-k>Next stake</div>
      <div class=sb-kv-v style="color:var(--compound)">${ngn(stake)}</div>
    </div>
    <div class=sb-kv>
      <div class=sb-kv-k>Net profit</div>
      <div class=sb-kv-v style="color:${amt>=0?'var(--win)':'var(--loss)'}">${amt>=0?'+':'-'}${ngn(Math.abs(amt))}</div>
    </div>
    <div class=sb-kv>
      <div class=sb-kv-k>Running odds</div>
      <div class=sb-kv-v>${mult.toFixed(2)}×</div>
    </div>
    <div class=sb-kv>
      <div class=sb-kv-k>Last pick</div>
      <div class=sb-kv-v style="color:${lo==='win'?'var(--win)':lo==='loss'?'var(--loss)':'var(--ink-2)'}">${lo?lo.toUpperCase():'—'}</div>
    </div>`;
});

// ── Sidebar: by sport ───────────────────────────────────────────────────────
f('/api/by-sport').catch(()=>[]).then(rows => {
  const el=document.getElementById('sb-sport');
  if (!rows.length) { el.innerHTML=`<p style="font-size:var(--t-xs);color:var(--ink-3)">Data after settled bets.</p>`; return; }
  el.innerHTML=rows.slice(0,8).map(r=>`
    <div class=sb-row>
      <div class=sb-row-lbl>${r.sport}</div>
      <div class=sb-bar><div class=sb-bar-fill style="width:${Math.max(3,r.win_rate)}%"></div></div>
      <div class=sb-row-stat>
        <div>${r.won||0}W ${(r.n||0)-(r.won||0)}L</div>
        <div style="color:${(r.roi||0)>=0?'var(--win)':'var(--loss)'};font-size:9px">${(r.roi||0)>=0?'+':''}${r.roi??0}%</div>
      </div>
    </div>`).join('');
});

// ── Sidebar: confidence calibration ────────────────────────────────────────
f('/api/breakdown').catch(()=>({})).then(b => {
  const el=document.getElementById('sb-conf');
  if (!b.by_confidence||!b.by_confidence.length) {
    el.innerHTML=`<p style="font-size:var(--t-xs);color:var(--ink-3)">Data after settled bets.</p>`; return;
  }
  el.innerHTML=b.by_confidence.map(c=>`
    <div class=sb-row>
      <div class=sb-row-lbl style="width:95px;font-size:9px">${c.band}</div>
      <div class=sb-bar><div class=sb-bar-fill style="width:${Math.max(3,c.win_rate)}%"></div></div>
      <div class=sb-row-stat style="width:36px">${c.win_rate}%</div>
    </div>`).join('');
});

// ── Sidebar: markets ────────────────────────────────────────────────────────
f('/api/markets').catch(()=>[]).then(ms => {
  const el=document.getElementById('sb-markets');
  el.innerHTML=ms.length
    ?ms.slice(0,10).map(x=>`<span class="badge badge-gold" style="font-size:9px">${x.market} <b>${x.n}</b></span>`).join('')
    :`<p style="font-size:var(--t-xs);color:var(--ink-3)">Appears after first bets.</p>`;
});

// ── Sidebar: latest insight ─────────────────────────────────────────────────
f('/api/insights').catch(()=>[]).then(rows => {
  const block=document.getElementById('sb-insight-block');
  if (!rows.length) { block.style.display='none'; return; }
  block.style.display='';
  const ins=rows[0];
  document.getElementById('sb-insight').innerHTML=`
    <div style="font-size:9px;color:var(--ink-3);margin-bottom:var(--sp-2);line-height:1.5">
      ${ins.period_start||''}–${ins.period_end||''} · ${ins.total_bets||0} bets<br>
      Win rate ${ins.win_rate!=null?ins.win_rate+'%':'—'} · ROI ${ins.roi!=null?(ins.roi>=0?'+':'')+ins.roi+'%':'—'}
    </div>
    ${ins.best_sport?`<div class=sb-kv style="padding:4px 0"><div class=sb-kv-k>Best sport</div><div class=sb-kv-v style="color:var(--win)">${ins.best_sport}</div></div>`:''}
    ${ins.worst_sport?`<div class=sb-kv style="padding:4px 0"><div class=sb-kv-k>Worst sport</div><div class=sb-kv-v style="color:var(--loss)">${ins.worst_sport}</div></div>`:''}
    ${ins.best_market?`<div class=sb-kv style="padding:4px 0"><div class=sb-kv-k>Best market</div><div class=sb-kv-v style="color:var(--win)">${ins.best_market}</div></div>`:''}
    ${ins.recommendations?`<p style="font-size:var(--t-xs);color:var(--gold);margin-top:var(--sp-2);line-height:1.5">${ins.recommendations}</p>`:''}`;
});
</script>"""
    return shell("Dashboard", "home", body)

# ── Bet Chain────────────────────────────────────────────────────
@app.get("/betchain", response_class=HTMLResponse)
def betchain():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <p class=label style="margin-bottom:var(--sp-2)">Compound chain</p>
  <h1 class=display style="font-size:clamp(2.5rem,8vw,5rem);margin-bottom:var(--sp-2)" id=chain-headline>Day — / 30</h1>
  <p id=chain-subhead style="color:var(--ink-2);font-size:var(--t-lg)">Loading chain status…</p>
</div>

<!-- KPIs -->
<div class=grid-4 id=chain-kpis style="margin-bottom:var(--sp-8)"></div>

<!-- Progress ring + today's pick -->
<div class=grid-2 style="margin-bottom:var(--sp-8)">
  <div>
    <div class=section-head><h2>Cycle progress</h2><div class=section-rule></div></div>
    <div style="display:flex;align-items:center;gap:var(--sp-6);flex-wrap:wrap;margin-bottom:var(--sp-6)">
      <div id=chain-ring></div>
      <div id=chain-ring-meta></div>
    </div>
    <div class=day-grid id=day-grid></div>
    <div style="display:flex;gap:var(--sp-4);margin-top:var(--sp-3);font-size:var(--t-xs);color:var(--ink-3);flex-wrap:wrap">
      <span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:3px;background:oklch(68% .15 155 / .35);display:inline-block"></span>Win</span>
      <span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:3px;background:oklch(62% .18 22 / .35);display:inline-block"></span>Loss</span>
      <span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:3px;background:oklch(70% .16 65 / .35);display:inline-block"></span>Today</span>
      <span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:3px;border:1px solid var(--border);display:inline-block"></span>Upcoming</span>
    </div>
  </div>
  <div>
    <div class=section-head><h2>Today's pick</h2><div class=section-rule></div></div>
    <div id=chain-today></div>
  </div>
</div>

<!-- Chain history table -->
<div class=section style="margin-bottom:var(--sp-6)">
  <div class=section-head><h2>Record</h2><div class=section-rule></div></div>
  <div class=grid-3 id=chain-record style="margin-bottom:var(--sp-4)"></div>
</div>

<!-- Chain history table -->
<div class=section>
  <div class=section-head><h2>Chain history</h2><div class=section-rule></div></div>
  <div class=surface style="padding:0;overflow-x:auto">
    <table id=chain-table>
      <tr><th>#</th><th>Date</th><th>Match</th><th>Pick</th><th>Odds</th><th>Stake</th><th>Return</th><th>Result</th></tr>
    </table>
  </div>
</div>

<!-- Rules -->
<div class=section style="margin-bottom:var(--sp-10)">
  <div class=section-head><h2>Rules</h2><div class=section-rule></div></div>
  <div class=grid-2>
    <div>
      <div class=stat-row><span class=label>Starting stake</span><span class=sv>₦1,000</span></div>
      <div class=stat-row><span class=label>Target odds</span><span class=sv>≥ 1.30 combined</span></div>
      <div class=stat-row><span class=label>Selection</span><span class=sv>Highest Kelly value</span></div>
      <div class=stat-row><span class=label>Cycle length</span><span class=sv>30 days</span></div>
      <div class=stat-row><span class=label>On win</span><span class=sv style="color:var(--win)">Compounds</span></div>
      <div class=stat-row><span class=label>On loss</span><span class=sv style="color:var(--loss)">7-day break</span></div>
      <div class=stat-row><span class=label>30-day target (1.35 avg)</span><span class=sv style="color:var(--compound)">~57×</span></div>
    </div>
    <div style="color:var(--ink-2);font-size:var(--t-sm);line-height:1.75">
      <p style="margin-bottom:var(--sp-3)">One pick per day. Pure Kelly criterion — no odds cap. The daily scanner picks the highest Kelly-value bets and combines them until the slip reaches ≥1.30 combined odds. A 400-odds value bet is valid if Kelly says so.</p>
      <p style="margin-bottom:var(--sp-3)">All sports valid — Premier League, La Liga, NBA, MLB, international friendlies, everything. No restrictions.</p>
      <p>Forward your pick to clawson: <code style="background:var(--surface-2);padding:2px 6px;border-radius:4px">compound: Belgium @ 1.35</code></p>
    </div>
  </div>
</div>

<script>""" + JS_SHARED + r"""
Promise.all([
  f('/api/continuous-bet').catch(()=>({})),
  f('/api/betchain/history').catch(()=>[])
]).then(([cb, hist]) => {
  const day=cb.streak_day||0, wins=cb.streak_wins||0;
  const pct=cb.cycle_progress_pct||0, amt=cb.amount_won||0;
  const mult=cb.running_mult||1.0, stake=cb.current_stake||1000;
  const startStake=cb.starting_stake||1000;
  // Count actual losses from history (pending days are not losses).
  // streak_day is the current POSITION, not the count of completed days.
  const losses = (hist||[]).filter(r => r.outcome==='loss').length;
  const settledCount = (hist||[]).filter(r => r.outcome==='win' || r.outcome==='loss').length;

  document.getElementById('chain-headline').textContent = `Day ${day} / 30`;
  const statusMap = {idle:'Waiting to start',active:`Active · Day ${day}`,won_30day:'Cycle complete 🎯',
    restrategy:`Restrategy break${cb.restrategy_until?' until '+cb.restrategy_until:''}`,broken:'Chain reset'};
  document.getElementById('chain-subhead').textContent = statusMap[cb.streak_status]||cb.streak_status||'Idle';

  document.getElementById('chain-kpis').innerHTML = [
    ['Day', `${day}<span style="font-size:var(--t-sm);color:var(--ink-3)">/30</span>`, 'current position'],
    ['Current stake', ngn(stake), 'start ' + ngn(startStake)],
    ['Net won', (amt>=0?'+':'-') + ngn(Math.abs(amt)), amt>=0?'ahead':'behind start'],
    ['Running odds', mult.toFixed(2)+'×', `${wins} win${wins!==1?'s':''} this cycle`],
  ].map(([l,v,s]) => `<div class=surface>
    <div class=kpi-block>
      <span class=label>${l}</span>
      <span class="kpi-value num">${v}</span>
      <span class=kpi-sub>${s}</span>
    </div>
  </div>`).join('');

  // Ring
  document.getElementById('chain-ring').innerHTML = ring(pct, day.toString(), 120, 'var(--compound)');
  // Target: startStake * 1.35^30 (uses real starting stake, standard 1.35 avg odds assumption)
  const targetAmt = startStake * Math.pow(1.35, 30);
  document.getElementById('chain-ring-meta').innerHTML =
    `<div><p class=label style="margin-bottom:var(--sp-2)">${pct}% through cycle</p>
     <p style="font-size:var(--t-sm);color:var(--ink-2);line-height:1.65">
       ${wins} win${wins!==1?'s':''} · ${losses} loss${losses!==1?'es':''}<br>
       <span style="color:${amt>=0?'var(--win)':'var(--loss)'}"><b>${amt>=0?'+':'-'}${ngn(Math.abs(amt))}</b></span> net<br>
       <b>${mult.toFixed(2)}×</b> running odds<br>
       Target (30d · 1.35avg): <span style="color:var(--compound)"><b>${ngn(targetAmt)}</b></span>
     </p></div>`;

  // Day grid — use actual outcomes from history
  const dayOutcome = {};
  hist.forEach(r => { if (r.chain_day) dayOutcome[r.chain_day] = r.outcome; });
  let grid = '';
  for (let i = 1; i <= 30; i++) {
    const oc = dayOutcome[i];
    if (i === day) {
      grid += `<div class="day-cell day-today" title="Day ${i} — today">${i}</div>`;
    } else if (oc === 'win') {
      grid += `<div class="day-cell day-win" title="Day ${i} — win">✓</div>`;
    } else if (oc === 'loss') {
      grid += `<div class="day-cell day-loss" title="Day ${i} — loss">✗</div>`;
    } else if (i < day) {
      grid += `<div class="day-cell day-win" title="Day ${i} — pending">·</div>`;
    } else {
      grid += `<div class="day-cell day-future" title="Day ${i}">${i}</div>`;
    }
  }
  document.getElementById('day-grid').innerHTML = grid;

  // Record section
  const longest = cb.longest_streak || 0;
  const totalCycles = cb.total_cycles || 0;
  document.getElementById('chain-record').innerHTML = [
    ['Current streak', `${day-1} day${day-1!==1?'s':''}`, `Day ${day} in progress`],
    ['Longest streak', `${longest} day${longest!==1?'s':''}`, longest >= 30 ? '🏆 Perfect cycle!' : `${30-longest} day${30-longest!==1?'s':''} to beat record`],
    ['Total cycles', `${totalCycles}`, totalCycles > 0 ? `${totalCycles} completed` : 'First cycle running'],
  ].map(([l,v,s]) => `<div class=surface>
    <div class=kpi-block>
      <span class=label>${l}</span>
      <span class="kpi-value num">${v}</span>
      <span class=kpi-sub>${s}</span>
    </div>
  </div>`).join('');

  // Chain history table (rendered here so we already have hist data)
  const t = document.getElementById('chain-table');
  if (!hist.length) {
    t.innerHTML += '<tr><td colspan=8 class=empty><p>No chain bets logged yet. Day 1 logs after your first compound pick.</p></td></tr>';
  } else {
    t.innerHTML += hist.map((r,i) => `<tr>
      <td><b>${r.chain_day||i+1}</b></td>
      <td style="color:var(--ink-3)">${(r.scan_date||'').slice(5)}</td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.match||''}</td>
      <td><b>${r.pick||''}</b><br><span style="color:var(--ink-3);font-size:var(--t-xs)">${r.sport||''}</span></td>
      <td style="color:var(--gold);font-variant-numeric:tabular-nums">${oStr(r.odds)}</td>
      <td style="font-variant-numeric:tabular-nums">${ngn(r.stake||0)}</td>
      <td style="font-variant-numeric:tabular-nums">${r.outcome==='win'
        ? `<span style="color:var(--win)">+${ngn((parseFloat(r.odds||1)-1)*(r.stake||0))}</span>`
        : r.outcome==='loss' ? `<span style="color:var(--loss)">-${ngn(r.stake||0)}</span>` : '—'}</td>
      <td><span class="badge badge-${r.outcome==='win'?'win':r.outcome==='loss'?'loss':'pending'}">${r.outcome||'pending'}</span></td>
    </tr>`).join('');
  }
});

f('/api/betchain/today').catch(()=>({})).then(pick => {
  const el = document.getElementById('chain-today');
  if (pick && pick.on_break) {
    const until = pick.restrategy_until;
    const days = Math.max(0, Math.ceil((new Date(until+'T00:00:00Z') - new Date()) / 86400000));
    el.innerHTML = `<div class=surface style="border-color:oklch(62% .18 22 / .4);background:oklch(13% .025 22)">
      <p class=label style="margin-bottom:var(--sp-3)">Restrategy break — chain paused</p>
      <p style="font-size:var(--t-md);color:var(--ink-2);line-height:1.65;margin-bottom:var(--sp-4)">
        The last chain lost, so we're on the 7-day break.
        Chain restarts <strong style="color:var(--gold)">${until}</strong>${days>0?` — ${days} day${days===1?'':'s'} to go`:' — today!'},
        from Day 1 with <strong style="color:var(--compound)">${ngn(pick.stake||1000)}</strong>.
      </p>
      <div class=surface-2>
        <div class=stat-row><span class=label>Restart date</span><span class=sv>${until}</span></div>
        <div class=stat-row><span class=label>Restart stake</span><span class=sv style="color:var(--compound)">${ngn(pick.stake||1000)}</span></div>
        <div class=stat-row><span class=label>Kelly picks</span><span class=sv style="color:var(--win)">Still running daily</span></div>
      </div>
    </div>`;
    return;
  }
  if (!pick || pick.waiting_for_pick) {
    const day = pick ? pick.chain_day||2 : 2;
    const stake = pick ? pick.stake||1340 : 1340;
    el.innerHTML = `<div class=surface style="border-color:oklch(70% .16 65 / .4);background:oklch(13% .030 65)">
      <p class=label style="margin-bottom:var(--sp-3)">Day ${day} — waiting for your pick</p>
      <p style="font-size:var(--t-md);color:var(--ink-2);line-height:1.65;margin-bottom:var(--sp-4)">
        Your next compound stake is <strong style="color:var(--compound)">${ngn(stake)}</strong>.
        Find a match in the 1.30–1.40 odds range and forward it to clawson to log it.
      </p>
      <div class=surface-2>
        <div class=stat-row><span class=label>Stake ready</span><span class=sv style="color:var(--compound)">${ngn(stake)}</span></div>
        <div class=stat-row><span class=label>Target odds</span><span class=sv>1.30 – 1.40</span></div>
        <div class=stat-row><span class=label>Example</span><span class=sv style="font-size:var(--t-sm)">compound: Arsenal @ 1.35</span></div>
      </div>
    </div>`;
    return;
  }
  if (pick.match) {
    const isSettled = pick.outcome != null;
    el.innerHTML = `<div class="pick-card" style="border-color:oklch(70% .16 65 / .4);background:oklch(13% .030 65);${isSettled?'opacity:.7':''}">
      ${isSettled ? `<div style="margin-bottom:var(--sp-2)"><span class="badge badge-${pick.outcome==='win'?'win':'loss'}">${pick.outcome==='win'?'WON':'LOST'} — Day ${pick.chain_day||1} settled</span></div>` : ''}
      <div class=pick-match>${pick.match} ${confPips(pick.confidence_pct)}</div>
      <div class=pick-line>
        <span style="font-weight:700">${pick.pick||''}</span>
        <span class=pick-odds>${oStr(pick.odds)}</span>
        ${pick.market ? `<span class="badge badge-gold">${pick.market}</span>` : ''}
      </div>
      ${pick.plain_rationale ? `<p class=pick-why>${pick.plain_rationale}</p>` : ''}
      <div class=surface-2 style="margin-top:var(--sp-3)">
        <div class=stat-row><span class=label>${isSettled?'Was':'Today\'s'} stake</span><span class=sv style="color:var(--compound)">${ngn(pick.stake||1000)}</span></div>
        ${!isSettled?`<div class=stat-row><span class=label>If this wins → next stake</span><span class=sv style="color:var(--win)">${ngn((pick.stake||1000)*parseFloat(pick.odds||1.35))}</span></div>`:''}
      </div>
    </div>`;
  } else {
    el.innerHTML = `<div class=empty><p class=empty-title>No pick yet</p><p>Forward your pick to clawson: <code>compound: Belgium @ 1.35</code></p></div>`;
  }
});

</script>"""
    return shell("Bet Chain", "betchain", body)

# ── Long Shot ─────────────────────────────────────────────────────────────────
@app.get("/longshot", response_class=HTMLResponse)
def longshot():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <p class=label style="margin-bottom:var(--sp-2)">Long shot accumulator</p>
  <h1 class="display num" id=ls-hero style="font-size:clamp(3rem,10vw,6rem);color:var(--longshot)">—</h1>
  <p id=ls-hero-sub style="color:var(--ink-2);font-size:var(--t-lg);margin-top:var(--sp-2)">Loading…</p>
</div>

<div class=grid-4 id=ls-kpis style="margin-bottom:var(--sp-8)"></div>

<!-- Latest slip -->
<div class=section>
  <div class=section-head><h2>Current slip</h2><div class=section-rule></div></div>
  <div id=ls-latest></div>
</div>

<!-- Live monitoring -->
<div class=section id=ls-monitor-section style="display:none">
  <div class=section-head><h2>Live progress</h2><div class=section-rule></div><span id=ls-monitor-badge></span></div>
  <div class=grid-4 id=ls-monitor-kpis style="margin-bottom:var(--sp-4)"></div>
  <div class=surface style="padding:0;overflow-x:auto">
    <table id=ls-monitor-table>
      <tr><th>#</th><th>Match</th><th>Pick</th><th>Odds</th><th>Status</th><th>Score</th></tr>
    </table>
  </div>
</div>

<!-- Win/Loss history (no individual legs) -->
<div class=section>
  <div class=section-head><h2>History</h2><div class=section-rule></div></div>
  <div class=surface style="padding:0;overflow-x:auto">
    <table id=ls-hist>
      <tr><th>Week</th><th>Legs</th><th>Combined odds</th><th>Booking code</th><th>Stake</th><th>Result</th><th>Return</th></tr>
    </table>
  </div>
</div>

<!-- How it works -->
<div class=section style="margin-bottom:var(--sp-10)">
  <div class=section-head><h2>How it works</h2><div class=section-rule></div></div>
  <div class=grid-2>
    <div>
      <div class=stat-row><span class=label>When</span><span class=sv>Every Monday</span></div>
      <div class=stat-row><span class=label>Stake</span><span class=sv>₦100</span></div>
      <div class=stat-row><span class=label>Target</span><span class=sv>1,000×+</span></div>
      <div class=stat-row><span class=label>Legs</span><span class=sv>25–35 near-sure picks</span></div>
      <div class=stat-row><span class=label>Each leg</span><span class=sv>74%+ confidence · 1.10–1.35 odds</span></div>
      <div class=stat-row><span class=label>Booking</span><span class=sv>SportyBet (auto)</span></div>
    </div>
    <div style="color:var(--ink-2);font-size:var(--t-sm);line-height:1.8">
      <p style="margin-bottom:var(--sp-3)"><strong style="color:var(--ink)">Each individual leg is almost certain.</strong> Every pick in the slip has 74%+ chance of winning — things like "over 1.5 goals", "a strong favourite at home", "a team on a 6-game winning run".</p>
      <p style="margin-bottom:var(--sp-3)">Stacking 28 near-certain things together makes the slip itself a long shot. At 80% per leg, all 28 landing at once happens roughly 1 in 500 times.</p>
      <p>₦100 in. When it lands: ₦100,000+.</p>
    </div>
  </div>
</div>

<script>""" + JS_SHARED + r"""
f('/api/long-shot').catch(()=>[]).then(rows => {
  const settled = rows.filter(r => r.status==='won'||r.status==='lost');
  const won = rows.filter(r => r.status==='won').length;
  const staked = rows.reduce((s,r) => s+(r.stake||100), 0);
  const totalReturn = rows.filter(r=>r.status==='won').reduce((s,r)=>s+(r.payout||0),0);
  const netPnl = totalReturn - staked;
  const best = rows.reduce((mx,r) => Math.max(mx, r.combined_odds||0), 0);

  document.getElementById('ls-kpis').innerHTML = [
    ['Slips placed', rows.length,                              `${settled.length} settled`],
    ['Hit rate',     settled.length ? Math.round(won/settled.length*100)+'%' : '—', `${won} won`],
    ['Best odds',    best ? Math.round(best).toLocaleString()+'×' : '—',            'combined'],
    ['Net P&L',      staked ? (netPnl>=0?'+':'')+ngn(Math.abs(netPnl)) : '—',       netPnl>=0?'profit':'loss'],
  ].map(([l,v,s]) => `<div class=surface>
    <div class=kpi-block><span class=label>${l}</span><span class="kpi-value num">${v}</span><span class=kpi-sub>${s}</span></div>
  </div>`).join('');

  const ls = rows[0];
  if (ls) {
    document.getElementById('ls-hero').textContent = ls.combined_odds ? Math.round(ls.combined_odds).toLocaleString()+'×' : '—';
    document.getElementById('ls-hero-sub').textContent = `${ls.legs||'?'} legs · ${ls.week_of||''} · ₦${ls.stake||100} stake · ${ls.status||'pending'}`;
    document.getElementById('ls-latest').innerHTML = `
      <div class=surface style="border-color:oklch(62% .18 295 / .4)">
        <div style="display:flex;align-items:start;justify-content:space-between;flex-wrap:wrap;gap:var(--sp-4)">
          <div>
            <div class=stat-row><span class=label>Week</span><span class=sv>${ls.week_of||'—'}</span></div>
            <div class=stat-row><span class=label>Legs</span><span class=sv>${ls.legs||'?'}</span></div>
            <div class=stat-row><span class=label>Stake</span><span class=sv>${ngn(ls.stake||100)}</span></div>
            <div class=stat-row><span class=label>Status</span><span class=sv><span class="badge badge-${ls.status==='won'?'win':ls.status==='lost'?'loss':'pending'}">${ls.status||'pending'}</span></span></div>
            ${ls.status==='won'&&ls.payout?`<div class=stat-row><span class=label>Payout</span><span class=sv style="color:var(--win)">+${ngn(ls.payout)}</span></div>`:''}
          </div>
          <div style="text-align:center">
            ${ls.slip_code
              ?`<p class=label style="margin-bottom:var(--sp-2)">Booking code — tap to copy</p>
                <div class=booking-code onclick="navigator.clipboard.writeText('${ls.slip_code}');this.textContent='Copied!';setTimeout(()=>this.textContent='${ls.slip_code}',1800)">${ls.slip_code}</div>`
              :`<p style="color:var(--ink-3)">No booking code yet</p>`}
          </div>
        </div>
      </div>`;
  } else {
    document.getElementById('ls-hero').textContent = 'Mon';
    document.getElementById('ls-hero-sub').textContent = 'First long shot builds next Monday morning at 8am Lagos';
    document.getElementById('ls-latest').innerHTML = `<div class=empty><p class=empty-title>No slips yet</p><p>First one lands next Monday.</p></div>`;
  }

  // Monitoring widget
  f('/api/long-shot/monitor').catch(()=>null).then(m => {
    if (!m || m.status === 'no_active_slip' || m.error) return;
    document.getElementById('ls-monitor-section').style.display = '';
    const badge = m.eliminated
      ? `<span class="badge badge-loss">Eliminated</span>`
      : m.status === 'won'
        ? `<span class="badge badge-win">Won</span>`
        : `<span class="badge badge-pending">Active</span>`;
    document.getElementById('ls-monitor-badge').innerHTML = badge;
    document.getElementById('ls-monitor-kpis').innerHTML = [
      ['Legs won',    m.legs_won,     `of ${m.legs_total}`],
      ['Legs lost',   m.legs_lost,    m.eliminated ? '⚠️ slip dead' : 'survived'],
      ['Pending',     m.legs_pending, 'to play'],
      ['Potential',   m.eliminated ? '₦0' : '₦'+Math.round(m.potential_payout).toLocaleString(), m.eliminated ? 'eliminated' : m.running_odds.toFixed(1)+'× running'],
    ].map(([l,v,s]) => `<div class=surface>
      <div class=kpi-block><span class=label>${l}</span><span class="kpi-value num">${v}</span><span class=kpi-sub>${s}</span></div>
    </div>`).join('');
    const mt = document.getElementById('ls-monitor-table');
    mt.innerHTML = '<tr><th>#</th><th>Match</th><th>Pick</th><th>Odds</th><th>Status</th><th>Score</th></tr>';
    (m.legs||[]).forEach((leg,i) => {
      const icon = leg.won === true ? '✅' : leg.won === false ? '❌' : leg.status === 'inprogress' ? '🔴' : '⏳';
      const scoreCell = leg.score || '—';
      mt.innerHTML += `<tr>
        <td>${i+1}</td>
        <td style="font-size:var(--t-xs)">${leg.match}</td>
        <td><b>${leg.pick}</b></td>
        <td>${leg.odds.toFixed(2)}</td>
        <td>${icon} ${leg.status}</td>
        <td style="font-variant-numeric:tabular-nums">${scoreCell}</td>
      </tr>`;
    });
  });

  // History table — slips only, no legs
  const t = document.getElementById('ls-hist');
  t.innerHTML += rows.length ? rows.map(r => `<tr>
    <td><b>${r.week_of||''}</b></td>
    <td style="font-variant-numeric:tabular-nums">${r.legs||'?'}</td>
    <td style="color:var(--longshot);font-variant-numeric:tabular-nums;font-family:'Fraunces',serif;font-weight:700">${r.combined_odds?Math.round(r.combined_odds).toLocaleString():'—'}×</td>
    <td>${r.slip_code
      ?`<span class=booking-code style="font-size:.7rem;padding:2px 8px;cursor:pointer"
           onclick="navigator.clipboard.writeText('${r.slip_code}')">${r.slip_code}</span>`
      :'—'}</td>
    <td style="font-variant-numeric:tabular-nums">${ngn(r.stake||100)}</td>
    <td><span class="badge badge-${r.status==='won'?'win':r.status==='lost'?'loss':'pending'}">${r.status||'pending'}</span></td>
    <td style="font-variant-numeric:tabular-nums">
      ${r.status==='won'&&r.payout?`<span style="color:var(--win)">+${ngn(r.payout)}</span>`
        :r.status==='lost'?`<span style="color:var(--loss)">-${ngn(r.stake||100)}</span>`:'—'}
    </td>
  </tr>`).join('')
  : '<tr><td colspan=7 class=empty><p>No slips yet — first one lands next Monday</p></td></tr>';
});
</script>"""
    return shell("Long Shot", "longshot", body)

# ── History ───────────────────────────────────────────────────────────────────
@app.get("/history", response_class=HTMLResponse)
def history():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <h1 class=display style="font-size:clamp(2.5rem,7vw,4.5rem)">Kelly Bet History</h1>
  <p style="color:var(--ink-2);margin-top:var(--sp-2);font-size:var(--t-md)">
    Every pick you gave Clawson to place. <span id=hist-count style="color:var(--ink-3);font-size:var(--t-sm)"></span>
  </p>
  <p style="color:var(--ink-3);font-size:var(--t-sm);margin-top:var(--sp-2)">
    To log a bet: tell Clawson <em>"log: Arsenal win @ 1.65"</em> or <em>"kelly pick: Man City 1.45"</em>.
    Chain bets live on the <a href="/betchain" style="color:var(--gold)">Chain page</a>.
    Long shots live on the <a href="/longshot" style="color:var(--gold)">Long Shot page</a>.
  </p>
</div>
<div class=grid-4 id=hist-kpis style="margin-bottom:var(--sp-6)"></div>

<!-- Filter bar -->
<div class=surface style="display:flex;gap:var(--sp-3);flex-wrap:wrap;align-items:center;margin-bottom:var(--sp-4);padding:var(--sp-3) var(--sp-4)">
  <input id=flt-q placeholder="Search match or pick…" style="flex:1;min-width:160px;background:var(--surface-2);
    border:1px solid var(--border-2);border-radius:8px;padding:8px 12px;color:var(--ink);font-size:var(--t-sm);outline:none">
  <select id=flt-sport class=hist-flt></select>
  <select id=flt-outcome class=hist-flt>
    <option value="">All results</option>
    <option value="win">Won</option>
    <option value="loss">Lost</option>
    <option value="pending">Pending</option>
  </select>
  <select id=flt-bookmaker class=hist-flt></select>
  <button id=flt-clear style="background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;
    padding:8px 14px;color:var(--ink-2);font-size:var(--t-sm);cursor:pointer">Clear</button>
</div>
<style>
.hist-flt{background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;
  padding:8px 12px;color:var(--ink);font-size:var(--t-sm);outline:none;cursor:pointer}
.pg-btn{background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;
  padding:8px 16px;color:var(--ink);font-size:var(--t-sm);cursor:pointer}
.pg-btn:disabled{opacity:.35;cursor:default}
</style>

<div class=surface style="padding:0;overflow-x:auto">
  <table id=hist-table>
    <tr><th>Date</th><th>Match</th><th>Score</th><th>Pick</th><th>Market</th><th>Odds</th><th>Confidence</th><th>Bookmaker</th><th>Result</th></tr>
  </table>
</div>

<!-- Pagination -->
<div style="display:flex;justify-content:space-between;align-items:center;margin-top:var(--sp-4)">
  <button class=pg-btn id=pg-prev>← Prev</button>
  <span id=pg-info style="color:var(--ink-3);font-size:var(--t-sm)"></span>
  <button class=pg-btn id=pg-next>Next →</button>
</div>

<script>""" + JS_SHARED + r"""
const state = {page: 1, page_size: 25, q: '', sport: '', outcome: '', bookmaker: ''};
let debounceT = null;

function loadHistory() {
  const params = new URLSearchParams();
  params.set('page', state.page); params.set('page_size', state.page_size);
  if (state.q) params.set('q', state.q);
  if (state.sport) params.set('sport', state.sport);
  if (state.outcome) params.set('outcome', state.outcome);
  if (state.bookmaker) params.set('bookmaker', state.bookmaker);

  f('/api/history?' + params).catch(()=>({rows:[],total:0,pages:1,stats:{}})).then(d => {
    const rows = d.rows || [];
    const s = d.stats || {};
    const settledN = (s.won||0) + (s.lost||0);
    const wr = settledN ? Math.round(s.won/settledN*1000)/10 : null;
    document.getElementById('hist-kpis').innerHTML = [
      ['Settled',      settledN,                                        'matching bets'],
      ['Win rate',     wr!=null?wr+'%':'—',                             `${s.won||0}W · ${s.lost||0}L`],
      ['Profit units', settledN?((s.profit_units>=0?'+':'')+s.profit_units+' u'):'—', 'per unit staked'],
      ['Pending',      s.pending||0,                                    'awaiting settlement'],
    ].map(([lbl,v,sub]) => `<div class=surface>
      <div class=kpi-block><span class=label>${lbl}</span><span class="kpi-value num">${v}</span><span class=kpi-sub>${sub}</span></div>
    </div>`).join('');

    document.getElementById('hist-count').textContent = `${d.total||0} bet${d.total!==1?'s':''}`;

    // Populate dropdowns once
    const spSel = document.getElementById('flt-sport');
    if (spSel.options.length <= 1 && d.sports) {
      spSel.innerHTML = '<option value="">All sports</option>' +
        d.sports.map(x=>`<option value="${x}">${x}</option>`).join('');
      spSel.value = state.sport;
    }
    const bkSel = document.getElementById('flt-bookmaker');
    if (bkSel.options.length <= 1 && d.bookmakers) {
      bkSel.innerHTML = '<option value="">All bookmakers</option>' +
        d.bookmakers.map(x=>`<option value="${x}">${x}</option>`).join('');
      bkSel.value = state.bookmaker;
    }

    const t = document.getElementById('hist-table');
    t.innerHTML = '<tr><th>Date</th><th>Match</th><th>Score</th><th>Pick</th><th>Market</th><th>Odds</th><th>Confidence</th><th>Bookmaker</th><th>Result</th></tr>';
    if (!rows.length) {
      t.innerHTML += `<tr><td colspan=9><div class=empty>
        <p class=empty-title>No bets match</p>
        <p>Try clearing the filters, or tell Clawson: <em>"log: Arsenal win @ 1.65"</em>.</p>
      </div></td></tr>`;
    } else {
      t.innerHTML += rows.map(r => `<tr>
        <td style="color:var(--ink-3);white-space:nowrap">${(r.scan_date||'').slice(5)}</td>
        <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          <span style="font-size:var(--t-xs);color:var(--ink-3);display:block">${r.sport||''}</span>${r.match||''}
        </td>
        <td style="font-size:var(--t-sm);color:var(--ink-2);white-space:nowrap;font-variant-numeric:tabular-nums">${r.result_score||'—'}</td>
        <td><b>${r.pick||''}</b></td>
        <td style="color:var(--ink-2);font-size:var(--t-sm)">${r.market||''}</td>
        <td style="color:var(--gold);font-variant-numeric:tabular-nums">${oStr(r.odds)}</td>
        <td>${confPips(r.confidence_pct)}<span style="font-size:var(--t-xs);color:var(--ink-3);margin-left:4px">${r.confidence_pct!=null?r.confidence_pct+'%':'—'}</span></td>
        <td style="font-size:var(--t-xs);color:var(--ink-3)">${r.bookmaker||'—'}</td>
        <td>
          ${r.outcome==='win'?`<span class="badge badge-win">Won</span>`
            :r.outcome==='loss'?`<span class="badge badge-loss">Lost</span>`
            :`<span class="badge badge-pending">Pending</span>`}
        </td>
      </tr>`).join('');
    }

    document.getElementById('pg-info').textContent = `Page ${d.page||1} of ${d.pages||1} · ${d.total||0} bets`;
    document.getElementById('pg-prev').disabled = (d.page||1) <= 1;
    document.getElementById('pg-next').disabled = (d.page||1) >= (d.pages||1);
  });
}

document.getElementById('flt-q').addEventListener('input', e => {
  clearTimeout(debounceT);
  debounceT = setTimeout(() => { state.q = e.target.value.trim(); state.page = 1; loadHistory(); }, 350);
});
['sport','outcome','bookmaker'].forEach(k => {
  document.getElementById('flt-'+k).addEventListener('change', e => {
    state[k] = e.target.value; state.page = 1; loadHistory();
  });
});
document.getElementById('flt-clear').addEventListener('click', () => {
  state.q = state.sport = state.outcome = state.bookmaker = ''; state.page = 1;
  document.getElementById('flt-q').value = '';
  document.getElementById('flt-sport').value = '';
  document.getElementById('flt-outcome').value = '';
  document.getElementById('flt-bookmaker').value = '';
  loadHistory();
});
document.getElementById('pg-prev').addEventListener('click', () => { state.page--; loadHistory(); });
document.getElementById('pg-next').addEventListener('click', () => { state.page++; loadHistory(); });

loadHistory();
</script>"""
    return shell("History", "history", body)

# ── Diary ─────────────────────────────────────────────────────────────────────
@app.get("/diary", response_class=HTMLResponse)
def diary():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <h1 class=display style="font-size:clamp(2.5rem,7vw,4.5rem)">The Diary</h1>
  <p style="color:var(--ink-2);margin-top:var(--sp-2);font-size:var(--t-md);max-width:55ch">SabiAI's daily notebook — what it backed, what landed, what it learned. Honest, in plain words.</p>
</div>
<div id=entries></div>
<script>
fetch('/api/diary').then(r=>r.json()).then(rows=>{
  const e=document.getElementById('entries');
  if(!rows.length){
    e.innerHTML=`<div class=empty><p class=empty-title>The story starts today</p><p>SabiAI writes a daily entry once picks and results roll in. First entry tomorrow morning.</p></div>`;
    return;
  }
  e.innerHTML=rows.map(r=>`<div class=diary-entry>
    <div class=diary-date>${r.date}${r.mood?' · '+r.mood:''}</div>
    <h2 class=diary-title>${r.title||'Daily note'}</h2>
    <p class=diary-body>${(r.body||'').replace(/</g,'&lt;')}</p>
  </div>`).join('');
});
</script>"""
    return shell("Diary", "diary", body)

# ── Strategies (now a clean reference page) ───────────────────────────────────
@app.get("/strategies", response_class=HTMLResponse)
def strategies():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <h1 class=display style="font-size:clamp(2.5rem,7vw,4.5rem)">Strategies</h1>
  <p style="color:var(--ink-2);margin-top:var(--sp-2);font-size:var(--t-md)">4 channels running in parallel. All to WhatsApp. No sport restrictions.</p>
</div>

<div class=section>
  <div class=section-head><h2>1 · Kelly picks</h2><div class=section-rule></div></div>
  <div class=grid-2>
    <div>
      <div class=stat-row><span class=label>When</span><span class=sv>Daily · 8am Lagos</span></div>
      <div class=stat-row><span class=label>Minimum confidence</span><span class=sv>58%</span></div>
      <div class=stat-row><span class=label>50/50 picks</span><span class=sv style="color:var(--win)">Removed</span></div>
      <div class=stat-row><span class=label>Odds range</span><span class=sv>Unrestricted — pure Kelly</span></div>
      <div class=stat-row><span class=label>Sports</span><span class=sv>Everything</span></div>
    </div>
    <p style="color:var(--ink-2);font-size:var(--t-sm);line-height:1.75;align-self:center">Picks with higher confidence get larger stake recommendations automatically. Model-estimated odds used for smaller leagues where no bookmaker line is available. Only high-confidence (🟢) and decent-confidence (🟡) picks are sent.</p>
  </div>
</div>

<div class=section>
  <div class=section-head><h2>2 · Compound chain</h2><div class=section-rule></div><a href=/betchain style="color:var(--gold);font-size:var(--t-sm)">Full detail →</a></div>
  <div class=grid-2>
    <div>
      <div class=stat-row><span class=label>Start</span><span class=sv>₦1,000</span></div>
      <div class=stat-row><span class=label>Target odds</span><span class=sv>≥ 1.30 combined</span></div>
      <div class=stat-row><span class=label>Pick selection</span><span class=sv>Highest Kelly value, no cap</span></div>
      <div class=stat-row><span class=label>On win</span><span class=sv style="color:var(--win)">Compounds</span></div>
      <div class=stat-row><span class=label>On loss</span><span class=sv style="color:var(--loss)">7-day break</span></div>
      <div class=stat-row><span class=label>30-day target</span><span class=sv style="color:var(--compound)">~₦57,000</span></div>
    </div>
    <p style="color:var(--ink-2);font-size:var(--t-sm);line-height:1.75;align-self:center">Picks the best bets by Kelly fraction — no individual odds cap. A single 400-odds value bet is valid if Kelly says so. Target is ≥1.30 combined odds, built from as few legs as needed. Forward to clawson: <code style="background:var(--surface-2);padding:2px 6px;border-radius:4px">compound: Belgium @ 1.35</code>.</p>
  </div>
</div>

<div class=section>
  <div class=section-head><h2>3 · Long shot</h2><div class=section-rule></div><a href=/longshot style="color:var(--gold);font-size:var(--t-sm)">Full detail →</a></div>
  <div class=grid-2>
    <div>
      <div class=stat-row><span class=label>When</span><span class=sv>Every Monday</span></div>
      <div class=stat-row><span class=label>Stake</span><span class=sv>₦100</span></div>
      <div class=stat-row><span class=label>Target</span><span class=sv>1,000×+</span></div>
      <div class=stat-row><span class=label>Legs</span><span class=sv>25–35 near-sure picks</span></div>
      <div class=stat-row><span class=label>Each leg</span><span class=sv>74%+ confidence · 1.10–1.35 odds</span></div>
      <div class=stat-row><span class=label>Booking</span><span class=sv>Bet9ja auto-code</span></div>
    </div>
    <p style="color:var(--ink-2);font-size:var(--t-sm);line-height:1.75;align-self:center">25–30 near-certain picks stacked into one slip. Each individual leg is almost guaranteed — over 1.5 goals, a heavy favourite to win, that kind of thing. Stacking 28 of them makes the combined slip itself a genuine long shot (roughly 1-in-500 chance). ₦100 in, potentially ₦100,000+ out when it lands. Auto-booked on Bet9ja. Code sent to WhatsApp Monday morning.</p>
  </div>
</div>

<div class=section style="margin-bottom:var(--sp-10)">
  <div class=section-head><h2>4 · Live alerts</h2><div class=section-rule></div></div>
  <div class=grid-2>
    <div>
      <div class=stat-row><span class=label>When</span><span class=sv>10am–midnight Lagos</span></div>
      <div class=stat-row><span class=label>Frequency</span><span class=sv>Hourly</span></div>
      <div class=stat-row><span class=label>Confidence floor</span><span class=sv>67%+</span></div>
      <div class=stat-row><span class=label>Delivery</span><span class=sv>WhatsApp (instant)</span></div>
    </div>
    <p style="color:var(--ink-2);font-size:var(--t-sm);line-height:1.75;align-self:center">In-play scanner. Only strong-conviction events. Fires immediately on qualifying alert. Cron: <code style="background:var(--surface-2);padding:2px 6px;border-radius:4px">0 9-23 * * *</code> UTC.</p>
  </div>
</div>

<div class=section>
  <div class=section-head><h2>Model health</h2><div class=section-rule></div></div>
  <div class=grid-2>
    <div>
      <p class=label style="margin-bottom:var(--sp-3)">Calibration — predicted vs actual win rate</p>
      <div id=calib-table><p style="color:var(--ink-3);font-size:var(--t-sm)">Loading…</p></div>
    </div>
    <div>
      <p class=label style="margin-bottom:var(--sp-3)">Closing line value</p>
      <div id=clv-kpis></div>
      <p class=label style="margin:var(--sp-5) 0 var(--sp-3)">P/L by channel</p>
      <div id=bkpl-table></div>
    </div>
  </div>
</div>

<script>
const f2 = u => fetch(u).then(r => r.json());
f2('/api/calibration').then(rows => {
  if (!rows.length) { document.getElementById('calib-table').innerHTML = '<p style="color:var(--ink-3);font-size:var(--t-sm)">No settled picks yet.</p>'; return; }
  document.getElementById('calib-table').innerHTML = rows.map(r => {
    const ok = Math.abs(r.gap) <= 10;
    return `<div class=stat-row>
      <span class=label>${r.bucket} <span style="color:var(--ink-3)">(${r.n})</span></span>
      <span class="sv num">${r.predicted}% → ${r.actual}%
        <span style="color:${ok?'var(--win)':'var(--loss)'};font-size:var(--t-xs);margin-left:6px">${r.gap>0?'+':''}${r.gap}</span>
      </span></div>`;
  }).join('');
});
f2('/api/clv').then(d => {
  document.getElementById('clv-kpis').innerHTML = d.n
    ? `<div class=stat-row><span class=label>Picks tracked</span><span class="sv num">${d.n}</span></div>
       <div class=stat-row><span class=label>Average CLV</span><span class="sv num" style="color:${d.avg_clv>=0?'var(--win)':'var(--loss)'}">${d.avg_clv>0?'+':''}${d.avg_clv}%</span></div>
       <div class=stat-row><span class=label>Beat the close</span><span class="sv num">${d.pct_beat_close}%</span></div>`
    : '<p style="color:var(--ink-3);font-size:var(--t-sm)">No CLV data yet — picks gain closing odds when re-scanned before kickoff.</p>';
});
f2('/api/bookmaker-pl').then(rows => {
  document.getElementById('bkpl-table').innerHTML = rows.length ? rows.map(r =>
    `<div class=stat-row><span class=label>${r.channel}</span>
      <span class="sv num" style="color:${r.pl>=0?'var(--win)':'var(--loss)'}">${r.pl>=0?'+':'-'}₦${Math.abs(r.pl).toLocaleString()} <span style="color:var(--ink-3);font-size:var(--t-xs)">(${r.roi_pct!=null?(r.roi_pct>0?'+':'')+r.roi_pct+'%':'—'})</span></span>
    </div>`).join('') : '<p style="color:var(--ink-3);font-size:var(--t-sm)">No settled money events yet.</p>';
});
</script>"""
    return shell("Strategies", "strategies", body)

# ── Live Bets ─────────────────────────────────────────────────────────────────
@app.get("/live", response_class=HTMLResponse)
def live_page():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <h1 class=display style="font-size:clamp(2.5rem,7vw,4.5rem)">Live Alerts</h1>
  <p style="color:var(--ink-2);margin-top:var(--sp-2);font-size:var(--t-md);max-width:60ch">
    SabiAI watches live scores every hour during match windows and fires an alert to your WhatsApp when a game turns juicy mid-match.
  </p>
</div>

<!-- How it works -->
<div class=grid-2 style="margin-bottom:var(--sp-8)">
  <div class=surface>
    <p class=label style="margin-bottom:var(--sp-3)">How it works</p>
    <div class=stat-row><span class=label>Runs</span><span class=sv>Hourly · 10am–midnight Lagos</span></div>
    <div class=stat-row><span class=label>What it watches</span><span class=sv>30+ live scoreboards (ESPN)</span></div>
    <div class=stat-row><span class=label>Fires when</span><span class=sv>Game turns "juicy"</span></div>
    <div class=stat-row><span class=label>Alert to</span><span class=sv>WhatsApp</span></div>
    <div class=stat-row><span class=label>Confidence floor</span><span class=sv>67%+</span></div>
  </div>
  <div class=surface>
    <p class=label style="margin-bottom:var(--sp-3)">What "juicy" means</p>
    <p style="font-size:var(--t-sm);color:var(--ink-2);line-height:1.75">
      A game becomes juicy when it hits certain triggers mid-match:
    </p>
    <ul style="font-size:var(--t-sm);color:var(--ink-2);line-height:1.8;margin-top:var(--sp-3);padding-left:var(--sp-5)">
      <li>Still tight (within 1 goal) past the 60th minute — both sides still in it</li>
      <li>0–0 at half but both teams normally score a lot — goals due</li>
      <li>One team completely dominating but score stays flat — worth backing "next goal"</li>
      <li>Red card or penalty — match dynamics suddenly shift, markets reprice</li>
    </ul>
    <p style="font-size:var(--t-sm);color:var(--ink-3);margin-top:var(--sp-3)">
      Live alerts are for fun / observation. Log your pick via Clawson if you act on one.
    </p>
  </div>
</div>

<!-- Win/Loss record -->
<div class=section>
  <div class=section-head>
    <h2>Alert record</h2>
    <div class=section-rule></div>
    <span id=live-record-meta class=label></span>
  </div>
  <div class=grid-4 id=live-kpis style="margin:var(--sp-4) 0 var(--sp-6)"></div>
  <div class=surface style="padding:0;overflow-x:auto">
    <table id=live-table>
      <tr><th>Date</th><th>Match</th><th>Signals</th><th>Was juicy?</th><th>Outcome</th><th>Result</th></tr>
    </table>
  </div>
</div>

<script>""" + JS_SHARED + r"""
f('/api/live-history').catch(()=>({rows:[]})).then(data => {
  const rows = data.rows||[];
  const alerted = data.total_alerted||0;
  const settled = data.settled||0;
  const won = data.won||0;
  const lost = data.lost||0;

  document.getElementById('live-record-meta').textContent = `${alerted} alerts fired`;

  document.getElementById('live-kpis').innerHTML = [
    ['Alerts fired',  alerted,                                   'games flagged'],
    ['Settled',       settled,                                   'outcome known'],
    ['Won',           won,                                       `${settled?Math.round(won/settled*100):0}% hit rate`],
    ['Lost',          lost,                                      'missed calls'],
  ].map(([l,v,s]) => `<div class=surface>
    <div class=kpi-block><span class=label>${l}</span><span class="kpi-value num">${v}</span><span class=kpi-sub>${s}</span></div>
  </div>`).join('');

  const t = document.getElementById('live-table');
  if (!rows.length) {
    t.innerHTML += `<tr><td colspan=6>
      <div class=empty>
        <p class=empty-title>No live alerts yet</p>
        <p>The live scanner runs every hour 10am–midnight Lagos time. First juicy game will appear here.</p>
      </div>
    </td></tr>`;
    return;
  }
  t.innerHTML += rows.map(r => {
    const signals = (() => { try { return JSON.parse(r.signals||'[]').join(' · '); } catch { return r.signals||''; } })();
    const oc = r.outcome;
    return `<tr>
      <td style="color:var(--ink-3);white-space:nowrap;font-size:var(--t-xs)">${(r.date||'').slice(5)||'—'}</td>
      <td style="font-weight:600;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        <span style="font-size:var(--t-xs);color:var(--ink-3);display:block">${r.sport||''}</span>${r.match||'—'}
      </td>
      <td style="font-size:var(--t-xs);color:var(--ink-2);max-width:200px">${signals||'—'}</td>
      <td style="font-size:var(--t-xs)">
        ${r.was_juicy?`<span style="color:var(--win);font-weight:700">Yes (${r.juicy_score||''})</span>`
          :`<span style="color:var(--ink-3)">Watched</span>`}
      </td>
      <td>
        ${oc==='win'?`<span class="badge badge-win">Won</span>`
          :oc==='loss'?`<span class="badge badge-loss">Lost</span>`
          :r.status==='alerted'?`<span class="badge badge-live" style="font-size:9px">Alerted</span>`
          :`<span class="badge badge-pending">${r.status||'watching'}</span>`}
      </td>
      <td style="font-size:var(--t-sm);color:var(--ink-2)">${r.result||'—'}</td>
    </tr>`;
  }).join('');
});
</script>"""
    return shell("Live", "live", body)

# ── Finance (password-protected) ──────────────────────────────────────────────
@app.get("/finance", response_class=HTMLResponse)
def finance():
    body = """
<div style="padding:var(--sp-4) 0 var(--sp-6)">
  <h1 class=display style="font-size:clamp(2.5rem,7vw,4.5rem)">Finance</h1>
  <p style="color:var(--ink-2);margin-top:var(--sp-2);font-size:var(--t-md)">Private bankroll details. Enter PIN to unlock.</p>
</div>

<div id=finance-lock style="max-width:320px;margin:0 auto;text-align:center;padding:var(--sp-10) 0">
  <div class=surface style="padding:var(--sp-8)">
    <p class=label style="margin-bottom:var(--sp-4)">Enter PIN</p>
    <input id=pin-input type=password inputmode=numeric maxlength=6
      style="width:100%;background:var(--surface-2);border:1px solid var(--border-2);border-radius:10px;
             padding:var(--sp-3) var(--sp-4);font-size:var(--t-xl);text-align:center;
             color:var(--ink);font-family:'Fraunces',serif;font-weight:900;letter-spacing:.2em;outline:none"
      placeholder="······">
    <p id=pin-error style="color:var(--loss);font-size:var(--t-sm);margin-top:var(--sp-3);display:none">Wrong PIN</p>
    <button onclick="checkPin()"
      style="margin-top:var(--sp-4);width:100%;background:var(--gold);color:var(--bg);
             border-radius:10px;padding:var(--sp-3) var(--sp-4);font-weight:700;font-size:var(--t-md)">
      Unlock
    </button>
  </div>
</div>

<div id=finance-content style="display:none">
  <div class=grid-4 id=finance-kpis style="margin-bottom:var(--sp-8)"></div>

  <div class=section>
    <div class=section-head><h2>Bankroll over time</h2><div class=section-rule></div></div>
    <div id=finance-chart></div>
  </div>

  <div class=grid-2 style="margin-top:var(--sp-8)">
    <div>
      <div class=section-head><h2>Configuration</h2><div class=section-rule></div></div>
      <div id=finance-config></div>
    </div>
    <div>
      <div class=section-head><h2>Staking summary</h2><div class=section-rule></div></div>
      <div id=finance-staking></div>
    </div>
  </div>
</div>

<script>""" + JS_SHARED + r"""
const FINANCE_PIN = localStorage.getItem('sabiai_pin');
if (FINANCE_PIN) unlockFinance(FINANCE_PIN);

document.getElementById('pin-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') checkPin();
});

function checkPin() {
  const val = document.getElementById('pin-input').value;
  // Simple 4-digit PIN stored in localStorage after first unlock
  // Default PIN: 1234 (change via onboarding / config)
  const stored = localStorage.getItem('sabiai_finance_pin') || '1234';
  if (val === stored) {
    localStorage.setItem('sabiai_pin', val);
    unlockFinance(val);
  } else {
    document.getElementById('pin-error').style.display = '';
  }
}

function unlockFinance() {
  document.getElementById('finance-lock').style.display = 'none';
  document.getElementById('finance-content').style.display = '';

  f('/api/overview').catch(()=>({})).then(o => {
    const pu = o.profit_units;
    document.getElementById('finance-kpis').innerHTML = [
      ['Starting bankroll', o.bankroll_start!=null?ngn(o.bankroll_start):'—', 'initial capital'],
      ['Current bankroll',  o.bankroll_current!=null?ngn(o.bankroll_current):'—', 'today'],
      ['Net profit',        o.profit!=null?(o.profit>=0?'+':'-')+ngn(Math.abs(o.profit)):'—',
        o.roi_pct!=null?(o.roi_pct>=0?'+':'')+o.roi_pct+'% ROI':''],
      ['Units P&L',         pu!=null?(pu>=0?'+':'')+pu+' u':'—', 'per unit staked'],
    ].map(([l,v,s]) => `<div class=surface>
      <div class=kpi-block><span class=label>${l}</span><span class="kpi-value num">${v}</span><span class=kpi-sub>${s}</span></div>
    </div>`).join('');

    document.getElementById('finance-config').innerHTML = `
      <div class=stat-row><span class=label>Currency</span><span class=sv>${o.currency||'NGN'}</span></div>
      <div class=stat-row><span class=label>Started</span><span class=sv>${o.started_on||'—'}</span></div>
      <div class=stat-row><span class=label>Target ROI</span><span class=sv>${o.target_roi_pct!=null?o.target_roi_pct+'%':'—'}</span></div>
      <div class=stat-row><span class=label>Stop loss</span><span class=sv style="color:var(--loss)">—</span></div>`;

    document.getElementById('finance-staking').innerHTML = `
      <div class=stat-row><span class=label>Settled bets</span><span class=sv>${(o.won||0)+(o.lost||0)}</span></div>
      <div class=stat-row><span class=label>Win / Loss</span><span class=sv>${o.won||0} / ${o.lost||0}</span></div>
      <div class=stat-row><span class=label>Pending</span><span class=sv>${o.pending||0}</span></div>
      <div class=stat-row><span class=label>Current streak</span><span class=sv>${o.streak?o.streak+(o.streak_kind==='win'?' W':' L'):'—'}</span></div>`;
  });

  f('/api/over-time').catch(()=>({})).then(d => {
    const bankData = (d.bankroll||[]);
    document.getElementById('finance-chart').innerHTML = bankData.length
      ? `<p class=label style="margin-bottom:var(--sp-2)">Bankroll balance (₦)</p>` + sparkline(bankData, 'balance', 800)
      : `<div class=empty><p>No bankroll history yet</p></div>`;
  });
}
</script>"""
    return shell("Finance", "home", body)
