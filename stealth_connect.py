"""
Stealth LinkedIn Connection Automation - Safe Human Model.
- Simulates genuine human browsing and reading patterns:
  - Natural dwell reading headlines and summaries (4.0 - 7.5s)
  - Organic mouse-wheel scrolling through experience sections with micro-jitters
  - Relaxed human cooldown pacing (45.0 - 75.0s between requests)
  - Organic micro-breaks (80.0 - 130.0s every 6 invites)
  - Safe daily batch cap: defaults to 25 invites per day
- Precise locator targeting (only elements with aria-label containing 'to connect')
- Verified dispatch confirmation (Pending status or 'Invitation sent' toast)
- Automatic weekly limit and security prompt monitoring
- Tab recycling to avoid browser memory bloat
"""

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent
AUTH_STATE = BASE_DIR / ".auth/state.json"
HISTORY_FILE = BASE_DIR / "sent_invites.json"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""

SEARCH_QUERIES = [
    "Software Engineer",
    "Java Developer",
    "Backend Engineer",
    "Full Stack Engineer",
    "Senior Software Engineer",
    "Cloud Engineer",
    "DevOps Engineer"
]

def load_history() -> set:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("sent_urls", []))
        except Exception:
            return set()
    return set()

def save_history(url: str, name: str):
    data = {"sent_urls": [], "records": []}
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if url not in data["sent_urls"]:
        data["sent_urls"].append(url)
        data.setdefault("records", []).append({
            "url": url,
            "name": name,
            "timestamp": datetime.now().isoformat()
        })
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

async def human_scroll(page, distance: int = 450):
    """Simulates organic human wheel scrolling with variable speed and micro-jitters."""
    steps = random.randint(4, 7)
    step_dist = distance // steps
    for _ in range(steps):
        await page.mouse.wheel(0, step_dist + random.randint(-15, 25))
        await asyncio.sleep(random.uniform(0.18, 0.42))
    await asyncio.sleep(random.uniform(1.2, 2.5))

async def scrape_search_candidates(page, query: str, page_num: int = 1) -> list:
    """Scrapes 2nd-degree candidate profile URLs from LinkedIn search results."""
    search_url = f"https://www.linkedin.com/search/results/people/?keywords={query.replace(' ', '%20')}&network=%5B%22S%22%5D&page={page_num}"
    print(f"\n[*] Searching 2nd-degree connections: '{query}' (Page {page_num}) -> {search_url}")
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Human-like scrolling through search results
        for _ in range(random.randint(3, 5)):
            await page.mouse.wheel(0, random.randint(300, 500))
            await asyncio.sleep(random.uniform(0.4, 0.8))

        links = await page.eval_on_selector_all(
            "a[href*='/in/']",
            "elements => elements.map(e => e.href)"
        )
        cleaned = []
        for l in links:
            base = l.split("?")[0].rstrip("/")
            if "/in/" in base and base not in cleaned:
                if not any(x in base for x in ["/overlay/", "/recent-activity/", "/edit/"]):
                    cleaned.append(base)
        print(f"[*] Discovered {len(cleaned)} candidates on page {page_num}.")
        return cleaned
    except Exception as e:
        print(f"[!] Error loading search results: {e}")
        return []

async def check_weekly_limit_or_checkpoint(page) -> tuple:
    """Checks for weekly limits, security checkpoints, or CAPTCHA challenges."""
    try:
        alerts = await page.eval_on_selector_all(
            ".artdeco-toast-item, [role='alert'], dialog, [role='dialog'], .artdeco-modal, .checkpoint-main",
            "elements => elements.map(e => (e.innerText || '').toLowerCase())"
        )
        for text in alerts:
            if any(term in text for term in ["weekly limit", "reached the weekly limit", "out of invitations", "invitation limit", "try again next week"]):
                return True, "WEEKLY_LIMIT"
            if any(term in text for term in ["security check", "verify your account", "unusual activity", "checkpoint", "enter the code"]):
                return True, "CHECKPOINT"
    except Exception:
        pass
    return False, ""

async def process_profile(page, profile_url: str, history: set) -> tuple:
    """
    Visits a profile with genuine human dwell time and sends an invitation safely.
    Returns (status: str, reached_limit: bool)
    """
    if profile_url in history:
        return "skipped", False

    print(f"\n--- Navigating: {profile_url} ---")
    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        print(f"[!] Timeout loading {profile_url}: {e}")
        return "error", False

    # 1. Human dwell time: reading headline and location
    dwell = random.uniform(4.0, 7.5)
    print(f"[*] Reading profile headline for {dwell:.1f}s...")
    await asyncio.sleep(dwell)

    # Check for security alert on load
    triggered, reason = await check_weekly_limit_or_checkpoint(page)
    if triggered:
        print(f"[!] Encountered alert on load: {reason}")
        try:
            await page.screenshot(path="scratch/alert_screenshot.png")
        except Exception:
            pass
        return reason.lower(), True

    # Extract member name for logging
    name = "Member"
    try:
        h1_el = page.locator("main h1").first
        if await h1_el.count() > 0:
            name = (await h1_el.inner_text()).strip()
            print(f"[*] Viewing: {name}")
    except Exception:
        pass

    # 2. Human scroll down to review experience
    print("[*] Human scroll down to review experience...")
    await human_scroll(page, distance=random.randint(450, 700))
    await asyncio.sleep(random.uniform(1.8, 3.2))

    # Scroll back up towards actions
    await page.mouse.wheel(0, -random.randint(400, 600))
    await asyncio.sleep(random.uniform(1.0, 1.8))

    # 3. Check if already Pending
    try:
        pending_btn = page.locator("main section:first-of-type button:has-text('Pending'), main section:first-of-type a:has-text('Pending'), main [aria-label*='Pending']").first
        if await pending_btn.count() > 0 and await pending_btn.is_visible():
            print(f"[*] Already pending for {name}. Skipping.")
            history.add(profile_url)
            return "already_pending", False
    except Exception:
        pass

    # 4. Locate precise Connect element in top card
    connect_el = page.locator(
        "main section:first-of-type a[aria-label*='to connect'], "
        "main section:first-of-type button[aria-label*='to connect'], "
        "a[aria-label*='Invite'][aria-label*='to connect']"
    ).first

    has_direct = await connect_el.count() > 0 and await connect_el.is_visible()

    if not has_direct:
        more_btn = page.locator("main section:first-of-type button[aria-label='More'], main section:first-of-type button:has-text('More')").first
        if await more_btn.count() > 0 and await more_btn.is_visible():
            await more_btn.click()
            await asyncio.sleep(random.uniform(0.9, 1.4))
            dropdown_connect = page.locator(
                "div.artdeco-dropdown__content [role='button'][aria-label*='to connect'], "
                "div.artdeco-dropdown__content [role='menuitem'][aria-label*='to connect'], "
                "div.artdeco-dropdown__content [role='button']:has-text('Connect'), "
                "div.artdeco-dropdown__content [role='menuitem']:has-text('Connect')"
            ).first
            if await dropdown_connect.count() > 0 and await dropdown_connect.is_visible():
                connect_el = dropdown_connect
                has_direct = True

    if not has_direct:
        print(f"[-] No direct connect button available for {name} (may be 1st degree or private).")
        history.add(profile_url)
        return "no_connect_option", False

    # 5. Click Connect
    print(f"[*] Clicking Connect for {name}...")
    try:
        await connect_el.evaluate("el => el.click()")
    except Exception:
        await connect_el.click(force=True)

    await asyncio.sleep(random.uniform(1.5, 2.2))

    # 6. Check weekly limit / alert
    triggered, reason = await check_weekly_limit_or_checkpoint(page)
    if triggered:
        print(f"[!] Weekly limit/checkpoint triggered: {reason}")
        try:
            await page.screenshot(path="scratch/alert_screenshot.png")
        except Exception:
            pass
        return reason.lower(), True

    # 7. Handle modal
    send_without_note = page.locator(
        "button:has-text('Send without a note'), "
        "button[aria-label*='Send without a note'], "
        "button[aria-label*='Send now']"
    ).first

    if await send_without_note.count() > 0 and await send_without_note.is_visible():
        print("[*] Modal detected: clicking 'Send without a note'...")
        await asyncio.sleep(random.uniform(0.6, 1.2))
        await send_without_note.click()
        await asyncio.sleep(random.uniform(2.0, 3.0))
    else:
        send_btn = page.locator("dialog button:has-text('Send'), [role='dialog'] button:has-text('Send')").first
        if await send_btn.count() > 0 and await send_btn.is_visible():
            await send_btn.click()
            await asyncio.sleep(random.uniform(2.0, 3.0))

    # 8. Check weekly limit after sending
    triggered, reason = await check_weekly_limit_or_checkpoint(page)
    if triggered:
        print(f"[!] Weekly limit triggered after sending: {reason}")
        try:
            await page.screenshot(path="scratch/alert_screenshot.png")
        except Exception:
            pass
        return reason.lower(), True

    # 9. Verify success
    is_pending = False
    try:
        pending_check = page.locator("main section:first-of-type button:has-text('Pending'), main section:first-of-type a:has-text('Pending'), main [aria-label*='Pending']").first
        if await pending_check.count() > 0:
            is_pending = True
    except Exception:
        pass

    toasts = []
    try:
        toasts = await page.eval_on_selector_all(
            ".artdeco-toast-item, [role='alert']",
            "elements => elements.map(e => e.innerText.trim())"
        )
    except Exception:
        pass
    toast_sent = any("invitation sent" in t.lower() for t in toasts)

    if toast_sent or is_pending:
        print(f"[+] VERIFIED SUCCESS: Invitation dispatched to {name} ({profile_url})")
        save_history(profile_url, name)
        history.add(profile_url)
        return "sent", False
    else:
        print(f"[-] Unverified dispatch for {name}. Skipping.")
        history.add(profile_url)
        return "unverified", False

async def main(max_invites: int = 25):
    history = load_history()
    print(f"=== Safe Human Model LinkedIn Invitation Agent Initializing ===")
    print(f"[*] Pre-loaded verified history: {len(history)} profiles.")
    print(f"[*] Target for this session: {max_invites} invites (Safe Human Daily Cap).")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            storage_state=str(AUTH_STATE),
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await context.add_init_script(STEALTH_JS)
        page = await context.new_page()

        total_sent = 0
        limit_reached = False
        profiles_processed = 0

        for query in SEARCH_QUERIES:
            if limit_reached or total_sent >= max_invites:
                break

            for page_num in range(1, 10):
                if limit_reached or total_sent >= max_invites:
                    break

                if profiles_processed > 20:
                    print("[*] Recycling page tab to maintain clean browser memory...")
                    try:
                        await page.close()
                    except Exception:
                        pass
                    page = await context.new_page()
                    profiles_processed = 0

                candidates = await scrape_search_candidates(page, query, page_num)
                uninvited = [c for c in candidates if c not in history]
                print(f"[*] {len(uninvited)} uninvited 2nd-degree candidates on page {page_num}.")

                for idx, profile_url in enumerate(uninvited):
                    try:
                        status, reached_limit = await process_profile(page, profile_url, history)
                        profiles_processed += 1
                    except Exception as err:
                        print(f"[!] Encountered page error ({err}), re-initializing tab...")
                        try:
                            await page.close()
                        except Exception:
                            pass
                        page = await context.new_page()
                        profiles_processed = 0
                        continue

                    if reached_limit:
                        limit_reached = True
                        break

                    if status == "sent":
                        total_sent += 1
                        print(f"=== Verified Sent Count: {total_sent}/{max_invites} (Total lifetime: {len(history)}) ===")

                        if total_sent >= max_invites:
                            print(f"[✓] Daily safe target ({max_invites}) achieved.")
                            break

                        # Human randomized cooldown pause
                        cooldown = random.uniform(45.0, 75.0)

                        # Micro-break every 6 invites (human coffee/distraction pause)
                        if total_sent % 6 == 0:
                            micro_break = random.uniform(85.0, 130.0)
                            print(f"\n[☕] Human micro-break: pausing for {micro_break:.1f}s...")
                            await asyncio.sleep(micro_break)
                        else:
                            print(f"[*] Human pacing cooldown: resting {cooldown:.1f}s...")
                            await asyncio.sleep(cooldown)

                    elif status in ("already_pending", "no_connect_option", "unverified"):
                        await asyncio.sleep(random.uniform(3.0, 6.0))

        print(f"\n=======================================================")
        print(f"Safe Human Session Finished:")
        print(f"- Sent This Session: {total_sent}")
        print(f"- Weekly Limit Reached: {limit_reached}")
        print(f"- Total Verified History: {len(history)}")
        print(f"=======================================================")

        await browser.close()

if __name__ == "__main__":
    max_count = 25
    if len(sys.argv) > 1:
        try:
            max_count = int(sys.argv[1])
        except ValueError:
            pass
    asyncio.run(main(max_count))
