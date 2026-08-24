#!/usr/bin/env python3
"""
sportybet_book.py — Auto-book a multi-leg slip on SportyBet NG via Playwright.

Usage:
  python3 sportybet_book.py --legs '[{"match":"Arsenal vs Chelsea","pick":"Arsenal","sport":"Soccer"}]'
  python3 sportybet_book.py --legs-file /tmp/legs.json --dry-run

Outputs the booking code to stdout on success.
"""
import argparse, json, sys, time, re, os

SPORTYBET_URL = "https://www.sportybet.com/ng/"
SEARCH_TIMEOUT = 8000   # ms
NAV_TIMEOUT    = 20000  # ms


def search_match(page, match_name: str, pick: str) -> bool:
    """Search for a match on SportyBet and click the correct pick. Returns True on success."""
    try:
        # Open search
        search_btn = page.locator("button[aria-label*='search' i], .search-btn, [class*='search']").first
        if search_btn.is_visible():
            search_btn.click()
        else:
            page.keyboard.press("Control+F")

        search_input = page.locator("input[placeholder*='search' i], input[type='search'], .search-input input").first
        search_input.wait_for(state="visible", timeout=SEARCH_TIMEOUT)
        search_input.fill(match_name)
        page.wait_for_timeout(2000)

        # Look for the match in results
        results = page.locator(f"text='{match_name.split(' vs ')[0]}'").all()
        if not results:
            # Try partial search with first team only
            first_team = match_name.split(" vs ")[0].split(" ")[-1]
            results = page.locator(f"text=/{first_team}/i").all()

        if not results:
            print(f"  [!] Match not found: {match_name}", file=sys.stderr)
            return False

        # Click first result (the match row)
        results[0].click()
        page.wait_for_timeout(1000)

        # Click the correct pick
        pick_btn = page.locator(f"text=/{re.escape(pick)}/i").first
        if pick_btn.is_visible():
            pick_btn.click()
            page.wait_for_timeout(500)
            return True

        print(f"  [!] Pick '{pick}' not found for {match_name}", file=sys.stderr)
        return False

    except Exception as e:
        print(f"  [!] Error searching {match_name}: {e}", file=sys.stderr)
        return False


def sportybet_search_and_add(page, legs: list) -> int:
    """Try to add each leg to the betslip via SportyBet search. Returns count added."""
    added = 0
    for leg in legs:
        match = leg.get("match", "")
        pick  = leg.get("pick", "")
        print(f"  → Adding: {match} | {pick}", file=sys.stderr)

        # Navigate to search page for each leg
        page.goto(SPORTYBET_URL + "?search=" + match.replace(" ", "+"), wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(3000)

        # Try to find match in search results and add pick
        success = _try_add_from_search(page, match, pick, leg)
        if success:
            added += 1
            print(f"  ✓ Added ({added}/{len(legs)})", file=sys.stderr)
        else:
            print(f"  ✗ Could not add {match}", file=sys.stderr)

    return added


def _try_add_from_search(page, match: str, pick: str, leg: dict) -> bool:
    """Find a match on the current search page and click the pick."""
    try:
        teams = match.split(" vs ")
        home = teams[0].strip() if teams else match.strip()

        # Wait for search results to load
        page.wait_for_timeout(2000)

        # Look for the event container containing the home team
        event_containers = page.locator("[class*='event'], [class*='match'], [class*='game']").all()
        target_container = None

        for container in event_containers[:20]:
            try:
                text = container.inner_text()
                if home.lower() in text.lower() and (len(teams) < 2 or teams[1].strip().lower() in text.lower()):
                    target_container = container
                    break
            except Exception:
                continue

        if not target_container:
            # Try simpler text search
            home_word = home.split()[-1]  # last word of home team
            candidates = page.locator(f"text=/{home_word}/i").all()
            if not candidates:
                return False
            # Use the parent container of first match
            target_container = candidates[0]

        # Within the container, click the pick button
        pick_clean = pick.replace("to win", "").replace("To Win", "").strip()
        # Try 1X2 buttons or direct text match
        pick_btns = target_container.locator(f"text=/{re.escape(pick_clean)}/i").all()
        if pick_btns:
            pick_btns[0].click()
            return True

        # Try direct text match without container scope
        broader = page.locator(f"text=/{re.escape(pick_clean)}/i").all()
        if broader:
            broader[0].click()
            return True

        return False

    except Exception as e:
        print(f"    [!] Container search error: {e}", file=sys.stderr)
        return False


def get_booking_code(page) -> str | None:
    """Click 'Get Booking Code' or 'Share' and extract the code."""
    try:
        # Look for booking code button
        for selector in [
            "text=/booking code/i",
            "text=/share bet/i",
            "text=/get code/i",
            "[class*='booking'], [class*='share-code']",
        ]:
            btn = page.locator(selector).first
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                break

        # Extract the code from modal/popup/input
        code_selectors = [
            "input[readonly][value]",
            "[class*='booking-code'] input",
            "[class*='code'] input",
            "text=/[A-Z0-9]{6,12}/",
        ]
        for sel in code_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    val = el.input_value() if el.element_handle().get_property("tagName").json_value().lower() == "input" else el.inner_text()
                    code = val.strip()
                    if re.match(r"[A-Z0-9]{4,}", code):
                        return code
            except Exception:
                continue

        # Last resort: scan page text for code-like strings
        body = page.locator("body").inner_text()
        codes = re.findall(r"\b([A-Z0-9]{6,12})\b", body)
        if codes:
            return codes[0]

        return None

    except Exception as e:
        print(f"  [!] Error getting booking code: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Auto-book SportyBet slip")
    parser.add_argument("--legs", help="JSON array of legs")
    parser.add_argument("--legs-file", help="Path to JSON file with legs")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually click, just browse")
    parser.add_argument("--screenshot", help="Save screenshot to this path")
    args = parser.parse_args()

    if args.legs_file:
        with open(args.legs_file) as f:
            legs = json.load(f)
    elif args.legs:
        legs = json.loads(args.legs)
    else:
        print("ERROR: provide --legs or --legs-file", file=sys.stderr)
        sys.exit(1)

    print(f"Booking {len(legs)} legs on SportyBet NG...", file=sys.stderr)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = ctx.new_page()
        page.set_default_timeout(NAV_TIMEOUT)

        # Load SportyBet
        print("Loading SportyBet...", file=sys.stderr)
        page.goto(SPORTYBET_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        page.wait_for_timeout(3000)

        if args.dry_run:
            print(f"[DRY-RUN] Would search for {len(legs)} matches", file=sys.stderr)
            if args.screenshot:
                page.screenshot(path=args.screenshot)
            print("DRY_RUN_CODE_PLACEHOLDER")
            browser.close()
            return

        added = sportybet_search_and_add(page, legs)
        print(f"Added {added}/{len(legs)} legs to slip", file=sys.stderr)

        if args.screenshot:
            page.screenshot(path=args.screenshot)

        if added == 0:
            print("ERROR: No legs added to betslip", file=sys.stderr)
            browser.close()
            sys.exit(2)

        # Get booking code
        code = get_booking_code(page)
        if code:
            print(f"Booking code: {code}", file=sys.stderr)
            print(code)  # stdout: just the code for piping
        else:
            print("WARNING: Could not extract booking code automatically", file=sys.stderr)
            print("MANUAL_CODE_NEEDED")

        browser.close()


if __name__ == "__main__":
    main()
