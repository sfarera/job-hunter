"""
Naukri Authentication Assistant.
Launches a headed browser for the user to manually log in to Naukri.com,
then saves the authenticated browser session state for automated headless runs.
"""

import os
import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent
AUTH_DIR = BASE_DIR / ".auth"
STATE_FILE = AUTH_DIR / "naukri_state.json"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""

async def manual_naukri_login():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("Naukri.com Authentication Assistant")
    print("=" * 60)
    print("Launching headed browser for manual login...")
    print("1. Log in to your Naukri account (Email/Password or OTP).")
    print("2. Once logged in and on your profile or homepage,")
    print("   the session will be automatically detected and saved.")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await context.add_init_script(STEALTH_JS)
        page = await context.new_page()

        print("[*] Navigating to Naukri login page...")
        await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")

        logged_in = False
        print("[*] Waiting for login completion (up to 5 minutes)...")

        for _ in range(150): # up to 5 minutes
            await asyncio.sleep(2)
            try:
                current_url = page.url
                # Naukri redirects to homepage, profile, or mnjuser upon login
                if any(x in current_url for x in ["mnjuser/homepage", "mnjuser/profile", "naukri.com/mnjuser"]):
                    logged_in = True
                    print(f"\n[+] Login detected on URL: {current_url}")
                    print(f"[*] Saving authenticated session state to: {STATE_FILE}")
                    await context.storage_state(path=str(STATE_FILE))
                    print("[+] Session state saved successfully!")
                    print("[*] Closing browser in 3 seconds...")
                    await asyncio.sleep(3)
                    break

                # Also inspect cookies for auth tokens
                cookies = await context.cookies()
                cookie_names = [c["name"] for c in cookies]
                if any(token in cookie_names for token in ["nauk_at", "_nk", "NAUKRI_USER"]):
                    logged_in = True
                    print(f"\n[+] Auth token detected in cookies: {[c for c in cookie_names if c in ['nauk_at', '_nk', 'NAUKRI_USER']]}")
                    print(f"[*] Saving authenticated session state to: {STATE_FILE}")
                    await context.storage_state(path=str(STATE_FILE))
                    print("[+] Session state saved successfully!")
                    print("[*] Closing browser in 3 seconds...")
                    await asyncio.sleep(3)
                    break
            except Exception:
                # User might have closed window
                break

        if not logged_in:
            print("\n[!] Attempting fallback session save before exit...")
            try:
                await context.storage_state(path=str(STATE_FILE))
            except Exception as e:
                print(f"[-] Could not save session: {e}")

        try:
            await browser.close()
        except Exception:
            pass

    if STATE_FILE.exists():
        print("=" * 60)
        print("SUCCESS: Naukri authentication setup completed!")
        print(f"State file: {STATE_FILE}")
        print("You can now run: python naukri_refresh.py")
        print("=" * 60)
    else:
        print("[!] Warning: Could not verify saved session file.")

if __name__ == "__main__":
    asyncio.run(manual_naukri_login())
