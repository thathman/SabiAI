#!/usr/bin/env python3
"""
bet9ja_book.py — Auto-book a multi-leg slip on Bet9ja via Playwright + real Chrome.

Usage:
  python3 bet9ja_book.py --legs '[{"match":"France vs Northern Ireland","pick":"France","sport":"Soccer"}]'
  python3 bet9ja_book.py --legs-file /tmp/legs.json
  python3 bet9ja_book.py --dry-run

Outputs the booking code to stdout on success.
"""
import argparse, json, sys, time, re, os

BET9JA_URL   = "https://sports.bet9ja.com/"
CHROME_PATH  = "/usr/bin/google-chrome"
NAV_TIMEOUT  = 30000
WAIT_MS      = 2500

# League pages: (keywords in match) -> URL slug
LEAGUE_PAGES = [
    (["world cup", "fifa", "wc"],                 "popularCoupons/0/fifaworldcup2026"),
    (["friendly", "international", "intl"],       "popularCoupons/0/internationalfriendlygames/1730"),
    (["copa libertadores"],                       "popularCoupons/0/copalibertadores"),
    (["nba"],                                     "popularCoupons/4/nba"),
    (["wnba"],                                    "popularCoupons/4/wnba"),
    (["mlb", "baseball", "yankees", "red sox",
      "orioles", "mariners", "phillies", "blue jays",
      "padres", "giants", "brewers", "athletics",
      "guardians", "rays", "astros", "angels"],   "popularCoupons/3/mlb"),
    (["nhl", "hurricanes", "golden knights",
      "hockey"],                                  "popularCoupons/5/nhl"),
]


def _chrome_browser(p):
    return p.chromium.launch(
        executable_path=CHROME_PATH,
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled"],
    )


def _new_ctx(browser):
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    return ctx


def _dismiss_overlay(page):
    """Remove the novasdk-inbox-widget overlay if present."""
    page.evaluate("""() => {
        const w = document.getElementById("novasdk-inbox-widget");
        if (w) w.remove();
        document.querySelectorAll(".popcontainer, .novasdk-inbox-app-widget__background")
            .forEach(el => el.remove());
    }""")


def _guess_league(leg: dict) -> str | None:
    """Guess which Bet9ja league page to use for a leg."""
    sport = (leg.get("sport") or "").lower()
    match = (leg.get("match") or "").lower()
    combined = sport + " " + match
    for keywords, slug in LEAGUE_PAGES:
        if any(kw in combined for kw in keywords):
            return slug
    # Default: international friendlies
    return "popularCoupons/0/internationalfriendlygames/1730"


def _find_and_click_odds(page, leg: dict) -> bool:
    """
    Find the match on the current page and click the correct odds button.
    Returns True if successfully added to bet slip.
    """
    home_team, away_team = _parse_teams(leg.get("match", ""))
    pick = (leg.get("pick") or "").strip()
    market = (leg.get("market") or "1X2").upper()

    # Determine sign (1 = home, X = draw, 2 = away)
    sign = _guess_sign(pick, home_team, away_team)
    print(f"  Looking for: {home_team} vs {away_team} | {pick} | sign={sign}", file=sys.stderr)

    # Find event ID from DOM — look for the match row
    event_id = page.evaluate(f"""() => {{
        const teams = document.querySelectorAll(
            ".sports-table__home, .sports-table__away, [class*='home'], [class*='away']");
        let row = null;
        for (let i = 0; i < teams.length; i++) {{
            const txt = teams[i].textContent.trim().toLowerCase();
            const homeMatch = txt.includes("{home_team.lower()[:8]}");
            const awayMatch = txt.includes("{away_team.lower()[:8]}");
            if (homeMatch || awayMatch) {{
                // Find the parent event row
                let el = teams[i];
                for (let d = 0; d < 8; d++) {{
                    if (el.id && el.id.startsWith("prematch_event-")) {{
                        return el.id.replace("prematch_event-", "");
                    }}
                    el = el.parentElement;
                    if (!el) break;
                }}
            }}
        }}
        return null;
    }}""")

    if not event_id:
        # Try broader search: scan all text for home team name
        event_id = page.evaluate(f"""() => {{
            const html = document.body.innerHTML;
            const re = /prematch_event-(\\d+)[^"]*home[^"]*>({re.escape(home_team[:6])})/i;
            const m = re.exec(html);
            return m ? m[1] : null;
        }}""")

    if not event_id:
        print(f"  [!] Match not found: {home_team} vs {away_team}", file=sys.stderr)
        return False

    # Build the odds button ID
    btn_id = f"prematch_event-{event_id}_event-{event_id}_odds_market-1x2_sign-{sign}"
    print(f"  Clicking: #{btn_id}", file=sys.stderr)

    btn = page.locator(f"#{btn_id}")
    if not btn.count():
        # Try alt market IDs
        for market_key in ["1x2", "fulltime", "matchresult"]:
            btn_id_alt = f"prematch_event-{event_id}_event-{event_id}_odds_market-{market_key}_sign-{sign}"
            btn = page.locator(f"#{btn_id_alt}")
            if btn.count():
                btn_id = btn_id_alt
                break

    if not btn.count():
        print(f"  [!] Odds button not found for {btn_id}", file=sys.stderr)
        return False

    try:
        btn.first.click(timeout=5000)
        page.wait_for_timeout(800)
        # Verify it was added (button should get an 'active' or 'selected' class)
        is_selected = page.evaluate(f"""() => {{
            const el = document.getElementById("{btn_id}");
            return el ? (el.classList.contains("sports-table__odds-item--active") ||
                         el.classList.contains("active") || el.classList.contains("selected")) : false;
        }}""")
        print(f"  {'✓' if is_selected else '~'} Added to slip (selected={is_selected})", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  [!] Click failed: {e}", file=sys.stderr)
        return False


def _parse_teams(match_str: str) -> tuple[str, str]:
    parts = re.split(r"\s+(?:vs\.?|v\.?|-)\s+", match_str, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return match_str.strip(), ""


def _guess_sign(pick: str, home: str, away: str) -> str:
    """Return '1', 'X', or '2' based on pick."""
    p = pick.strip().lower()
    h = home.strip().lower()
    a = away.strip().lower()
    if p in ("x", "draw", "tie"):
        return "X"
    if h and (h in p or p in h or p.split()[-1] in h):
        return "1"
    if a and (a in p or p in a or p.split()[-1] in a):
        return "2"
    # Default: pick is the team name, try to match
    if p.split()[0] in h.split()[0]:
        return "1"
    return "2"


def _get_booking_code(page) -> str | None:
    """Click 'Book a Bet' and extract the booking code."""
    # Look for the Book a Bet button in bet slip
    for selector in [
        "#betslip_buttons_bookabet",
        "text=Book a Bet",
        "text=Book Bet",
        "[class*='bookabet']",
        "[class*='book-a-bet']",
    ]:
        btn = page.locator(selector).first
        if btn.count() and btn.is_visible():
            print(f"  Clicking Book a Bet ({selector})", file=sys.stderr)
            btn.click()
            page.wait_for_timeout(3000)
            break
    else:
        print("  [!] 'Book a Bet' button not found", file=sys.stderr)
        return None

    # Extract code — Bet9ja shows it in .booking-code-display span
    for sel in [
        ".booking-code-display",
        ".share-coupon-modal-book_secondary-booking-code",
        ".share-coupon-modal-book_booking-code",
        "[class*='booking-code-display']",
        "[class*='secondary-booking-code']",
    ]:
        el = page.locator(sel).first
        if el.count():
            try:
                val = el.inner_text().strip()
                if val and re.match(r"^[A-Z0-9]{4,15}$", val):
                    return val
            except Exception:
                pass

    # Fallback: scan modal text for code pattern
    modal_text = ""
    for sel in [".share-coupon-modal-book", ".modals", "[class*='modal']"]:
        el = page.locator(sel).first
        if el.count():
            try:
                modal_text = el.inner_text()
                break
            except Exception:
                pass

    # Look for "Booking Code: XXXXXXX" pattern
    m = re.search(r"Booking Code[:\s]+([A-Z0-9]{4,15})", modal_text, re.I)
    if m:
        return m.group(1)

    # Last resort: any short alphanumeric code in modal
    codes = re.findall(r"\b([A-Z0-9]{5,10})\b", modal_text)
    skip = {"FRANCE", "ENGLAND", "BRAZIL", "GERMANY", "FIFA", "UEFA", "WNBA", "MLB", "NBA",
            "BET9JA", "BOOKBET", "BOOKING", "COUPON", "STAKE", "TOTAL", "ODDS"}
    valid = [c for c in codes if c not in skip and not c.isalpha()]
    if valid:
        return valid[0]

    page.screenshot(path="/tmp/bet9ja_booking.png")
    print("  [!] Code not found. Screenshot: /tmp/bet9ja_booking.png", file=sys.stderr)
    return None


def book_bet9ja(legs: list, dry_run: bool = False) -> str | None:
    """Main booking function. Returns booking code or None."""
    from playwright.sync_api import sync_playwright

    print(f"Booking {len(legs)} legs on Bet9ja...", file=sys.stderr)

    with sync_playwright() as p:
        browser = _chrome_browser(p)
        ctx = _new_ctx(browser)
        page = ctx.new_page()
        page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')
        page.set_default_timeout(NAV_TIMEOUT)

        # Initial load
        print("Loading Bet9ja...", file=sys.stderr)
        page.goto(BET9JA_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(3000)
        _dismiss_overlay(page)

        if dry_run:
            print(f"[DRY-RUN] Would add {len(legs)} legs", file=sys.stderr)
            browser.close()
            return "DRY_RUN_CODE_PLACEHOLDER"

        added = 0
        # Group legs by league to minimise page navigations
        from collections import defaultdict
        by_league = defaultdict(list)
        for leg in legs:
            slug = _guess_league(leg)
            by_league[slug].append(leg)

        for slug, slug_legs in by_league.items():
            url = BET9JA_URL + slug
            print(f"\nNavigating to {url} ({len(slug_legs)} matches)", file=sys.stderr)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                page.wait_for_timeout(WAIT_MS)
                _dismiss_overlay(page)
            except Exception as e:
                print(f"  [!] Nav error: {e}", file=sys.stderr)
                continue

            for leg in slug_legs:
                print(f"\n  → {leg.get('match')} | {leg.get('pick')}", file=sys.stderr)
                ok = _find_and_click_odds(page, leg)
                if ok:
                    added += 1
                page.wait_for_timeout(500)

        print(f"\nAdded {added}/{len(legs)} selections to bet slip", file=sys.stderr)

        if added == 0:
            print("ERROR: No legs added", file=sys.stderr)
            browser.close()
            return None

        # Show betslip state
        betslip_count = page.evaluate("""() => {
            const el = document.querySelector("[class*='betslip'] [class*='count'], [class*='bet-count']");
            return el ? el.textContent : null;
        }""")
        print(f"Bet slip count: {betslip_count}", file=sys.stderr)

        # Get booking code
        code = _get_booking_code(page)
        browser.close()
        return code


def main():
    parser = argparse.ArgumentParser(description="Auto-book Bet9ja slip")
    parser.add_argument("--legs", help="JSON array of legs")
    parser.add_argument("--legs-file", help="Path to JSON file with legs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--screenshot", help="Save final screenshot here")
    args = parser.parse_args()

    if args.legs_file:
        with open(args.legs_file) as f:
            legs = json.load(f)
    elif args.legs:
        legs = json.loads(args.legs)
    else:
        print("ERROR: provide --legs or --legs-file", file=sys.stderr)
        sys.exit(1)

    code = book_bet9ja(legs, dry_run=args.dry_run)
    if code and code not in ("DRY_RUN_CODE_PLACEHOLDER",):
        print(f"Booking code: {code}", file=sys.stderr)
        print(code)
    elif args.dry_run:
        print(code)
    else:
        print("MANUAL_CODE_NEEDED")
        sys.exit(2)


if __name__ == "__main__":
    main()
