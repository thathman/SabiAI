#!/usr/bin/env python3
"""
SabiAI Bet Alert Scraper
Scrapes bet alerts from t.me/s/bet_sabi_ai, captures screenshots,
extracts odds via OpenAI vision, and logs picks to JSON.
"""

import json
import os
import sys
import time
import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("ERROR: selenium not installed. Run: pip install selenium")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

# ── Config ──────────────────────────────────────────────────────────────
CHANNEL_URL = "https://t.me/s/bet_sabi_ai"
CHROME_PROFILE = os.path.expanduser("~/.config/google-chrome")
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
PICKS_DIR = os.path.join(WORKSPACE, "data", "sabiai")
SCREENSHOTS_DIR = os.path.join(PICKS_DIR, "screenshots")
PICKS_LOG = os.path.join(PICKS_DIR, "picks.json")
STATE_FILE = os.path.join(PICKS_DIR, "scraper_state.json")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Helpers ─────────────────────────────────────────────────────────────
LA = timezone(timedelta(hours=1))  # Africa/Lagos


def ts():
    return datetime.now(LA).isoformat(timespec="seconds")


def log(msg):
    print(f"[{ts()}] {msg}", flush=True)


def ensure_dirs():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_scrape": None, "seen_ids": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_picks():
    if os.path.exists(PICKS_LOG):
        with open(PICKS_LOG) as f:
            return json.load(f)
    return {"picks": [], "last_updated": None}


def save_picks(picks_data):
    picks_data["last_updated"] = ts()
    with open(PICKS_LOG, "w") as f:
        json.dump(picks_data, f, indent=2, ensure_ascii=False)


def msg_id_from_text(text):
    """Generate a stable ID from message content hash."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


# ── Driver Setup ────────────────────────────────────────────────────────
def create_driver(headless=True):
    opts = Options()

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
    else:
        opts.add_argument("--start-maximized")

    # Don't load the full Chrome profile — it's heavy and causes OOM.
    # The public channel page t.me/s/ doesn't need login.

    # Stealth flags
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    # Use a temp profile to avoid OOM from real Chrome profile
    import tempfile
    tmp_profile = tempfile.mkdtemp(prefix="sabiai_chrome_")
    opts.add_argument(f"--user-data-dir={tmp_profile}")

    if ChromeDriverManager:
        service = Service(ChromeDriverManager().install())
    else:
        service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=opts)


# ── Scraping ────────────────────────────────────────────────────────────
def scroll_to_load_all(driver, max_scrolls=50):
    """Scroll up repeatedly to load older messages."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    scrolls = 0
    while scrolls < max_scrolls:
        # Scroll to top to trigger loading of older messages
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1.5)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        scrolls += 1
        if scrolls % 10 == 0:
            log(f"  Scrolled {scrolls} times, page height: {new_height}")
    return scrolls


def scrape_messages(driver):
    """Extract all messages from the loaded page."""
    messages = []
    # Telegram web uses div.tgme_widget_message
    msg_elements = driver.find_elements(By.CSS_SELECTOR, "div.tgme_widget_message")

    for el in msg_elements:
        try:
            # Text content
            text_el = el.find_elements(By.CSS_SELECTOR, "div.tgme_widget_message_text")
            text = text_el[0].text.strip() if text_el else ""

            # Date/time
            date_el = el.find_elements(By.CSS_SELECTOR, "time")
            datetime_str = date_el[0].get_attribute("datetime") if date_el else ""

            # Message link (for dedup)
            link_el = el.find_elements(By.CSS_SELECTOR, "a.tgme_widget_message_date")
            msg_url = link_el[0].get_attribute("href") if link_el else ""

            # Images
            images = []
            img_els = el.find_elements(By.CSS_SELECTOR, "img.tgme_widget_message_photo")
            for img in img_els:
                src = img.get_attribute("src")
                if src and not src.endswith(".svg"):
                    images.append(src)

            # Screenshots (attached images that look like bet slips)
            attached = el.find_elements(
                By.CSS_SELECTOR, "a.tgme_widget_message_photo_wrap"
            )
            for att in attached:
                style = att.get_attribute("style") or ""
                # Extract background-image URL
                match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
                if match:
                    images.append(match.group(1))

            if text or images:
                messages.append({
                    "id": msg_url.split("/")[-1] if msg_url else msg_id_from_text(text),
                    "text": text,
                    "datetime": datetime_str,
                    "url": msg_url,
                    "images": images,
                })
        except Exception as e:
            log(f"  Warning: failed to parse message element: {e}")

    return messages


def download_image(url, save_path):
    """Download an image from Telegram CDN."""
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        log(f"  Failed to download image: {e}")
        return False


# ── Odds Extraction via OpenAI Vision ───────────────────────────────────
def extract_odds_from_image(image_path, api_key):
    """Send bet slip image to OpenAI vision to extract odds/picks."""
    if not api_key:
        return {"error": "no_api_key"}

    try:
        import base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        ext = Path(image_path).suffix.lower()
        mime = {"jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp"}.get(ext, "image/jpeg")

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extract ALL bet picks from this bet slip image. "
                                    "Return a JSON array where each pick has: "
                                    "event (teams/match), market (e.g. 'Over 2.5'), "
                                    "odds (number), league (if visible). "
                                    "If it's an accumulator/parlay, also extract the "
                                    "total_odds and total_stake. "
                                    "Return ONLY valid JSON, no explanation."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,{img_b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 1000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Strip markdown code fences if present
        content = re.sub(r"```json\s*", "", content)
        content = re.sub(r"```\s*$", "", content)
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw_response": content, "parse_error": True}
    except Exception as e:
        return {"error": str(e)}


# ── Pick Parsing (text-based alerts) ────────────────────────────────────
def parse_text_alert(text):
    """Parse common SabiAI text alert formats into structured picks."""
    picks = []
    lines = text.split("\n")
    current_event = ""
    current_market = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Look for odds patterns like "1.50" or "@1.50"
        odds_match = re.search(r"[@]?\s*(\d+\.\d{1,2})", line)
        # Look for market patterns
        market_match = re.search(
            r"(over|under|both teams to score|btts|win|draw|"
            r"double chance|handicap|correct score|gg|ng|1x|2x|x2)",
            line, re.IGNORECASE
        )
        # Look for team/event patterns (contains vs or - or @)
        event_match = re.search(
            r"([A-Z][a-zA-Z\s]+(?:vs?|[-–@]|[A-Z][a-zA-Z\s]+))",
            line
        )

        if odds_match and market_match:
            pick = {
                "market": market_match.group(0),
                "odds": float(odds_match.group(1)),
            }
            if event_match:
                pick["event"] = event_match.group(0).strip()
            picks.append(pick)
        elif odds_match and line:
            picks.append({"text": line, "odds": float(odds_match.group(1))})

    return picks


# ── Main Pipeline ───────────────────────────────────────────────────────
def run_scrape(headless=True):
    ensure_dirs()
    state = load_state()
    picks_data = load_picks()
    seen_ids = set(state.get("seen_ids", []))

    log("Starting SabiAI scraper...")
    driver = create_driver(headless=headless)

    try:
        log(f"Navigating to {CHANNEL_URL}")
        driver.get(CHANNEL_URL)
        time.sleep(3)

        # Check if page loaded
        title = driver.title
        log(f"Page title: {title}")

        # Scroll to load messages
        log("Scrolling to load messages...")
        scrolls = scroll_to_load_all(driver, max_scrolls=30)
        log(f"Completed {scrolls} scrolls")

        # Scrape messages
        messages = scrape_messages(driver)
        log(f"Found {len(messages)} total messages on page")

        # Take a full-page screenshot of the channel
        screenshot_path = os.path.join(
            SCREENSHOTS_DIR,
            f"channel_{datetime.now(LA).strftime('%Y%m%d_%H%M%S')}.png"
        )
        driver.save_screenshot(screenshot_path)
        log(f"Channel screenshot saved: {screenshot_path}")

        # Process only new messages
        new_count = 0
        for msg in messages:
            if msg["id"] in seen_ids:
                continue

            # Only process messages from today (or recent)
            if msg["datetime"]:
                try:
                    msg_dt = datetime.fromisoformat(msg["datetime"].replace("Z", "+00:00"))
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                    if msg_dt < cutoff:
                        continue
                except ValueError:
                    pass  # If we can't parse date, include it

            new_count += 1
            seen_ids.add(msg["id"])

            # Download images
            saved_images = []
            for i, img_url in enumerate(msg["images"]):
                img_hash = hashlib.md5(img_url.encode()).hexdigest()[:8]
                img_path = os.path.join(
                    SCREENSHOTS_DIR,
                    f"slip_{msg['id']}_{i}_{img_hash}.jpg"
                )
                if download_image(img_url, img_path):
                    saved_images.append(img_path)
                    log(f"  Downloaded image: {img_path}")

                    # Extract odds via vision if API key available
                    if OPENAI_API_KEY:
                        odds_data = extract_odds_from_image(img_path, OPENAI_API_KEY)
                        log(f"  Vision odds extraction: {json.dumps(odds_data)[:200]}")
                    else:
                        odds_data = None
                else:
                    odds_data = None

            # Parse text for odds
            text_picks = parse_text_alert(msg["text"]) if msg["text"] else []

            # Build pick record
            pick = {
                "id": msg["id"],
                "timestamp": msg["datetime"] or ts(),
                "scraped_at": ts(),
                "text": msg["text"],
                "url": msg["url"],
                "images": saved_images,
                "text_picks": text_picks,
            }
            if saved_images and OPENAI_API_KEY:
                pick["vision_picks"] = odds_data if isinstance(odds_data, list) else []

            picks_data["picks"].append(pick)
            log(f"  Logged pick: {msg['id']} ({len(text_picks)} text picks, {len(saved_images)} images)")

        # Update state
        state["last_scrape"] = ts()
        state["seen_ids"] = list(seen_ids)[-500:]  # Keep last 500 IDs
        save_state(state)
        save_picks(picks_data)

        log(f"Done. {new_count} new picks logged. Total: {len(picks_data['picks'])}")

    except Exception as e:
        log(f"ERROR: {e}")
        raise
    finally:
        driver.quit()


def show_recent(n=10):
    """Show last N picks."""
    picks_data = load_picks()
    for pick in picks_data["picks"][-n:]:
        print(f"\n{'='*60}")
        print(f"ID: {pick['id']}")
        print(f"Time: {pick.get('timestamp', 'N/A')}")
        print(f"Text: {pick.get('text', '')[:200]}")
        if pick.get("text_picks"):
            print(f"Odds parsed: {json.dumps(pick['text_picks'], indent=2)}")
        if pick.get("images"):
            print(f"Images: {len(pick['images'])}")


# ── CLI ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SabiAI Bet Alert Scraper")
    parser.add_argument("--show", action="store_true", help="Show recent picks")
    parser.add_argument("--count", type=int, default=10, help="Number of recent picks to show")
    parser.add_argument("--no-headless", action="store_true", help="Run with visible browser")
    parser.add_argument("--status", action="store_true", help="Show scraper state")
    args = parser.parse_args()

    if args.show:
        show_recent(args.count)
    elif args.status:
        state = load_state()
        picks = load_picks()
        print(f"Last scrape: {state.get('last_scrape', 'Never')}")
        print(f"Total picks: {len(picks.get('picks', []))}")
        print(f"Tracked IDs: {len(state.get('seen_ids', []))}")
    else:
        run_scrape(headless=not args.no_headless)
