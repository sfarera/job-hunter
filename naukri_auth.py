"""
Naukri Authentication Assistant - Real Google Chrome Edition.
Launches your real installed Google Chrome browser on macOS so Google Sign-In and Naukri
authentication work seamlessly without security blocks.
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
    print("Naukri Authentication Assistant (Real Google Chrome)")
    print("=" * 60)
    print("Launching your REAL Google Chrome browser...")
    print("1. Log in to your Naukri account (Google Sign-In, Email, or OTP).")
    print("2. Once you reach your profile or homepage, the session")
    print("   will automatically be detected and saved to .auth/naukri_state.json")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",  # Uses your real installed Google Chrome!
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
        print("[*] Waiting for login completion (polling every 2s, up to 5 minutes)...")

        for _ in range(150):
            await asyncio.sleep(2)
            try:
                current_url = page.url
                cookies = await context.cookies()
                cookie_names = [c["name"] for c in cookies]

                # Check URL or auth cookies
                if any(x in current_url for x in ["mnjuser/homepage", "mnjuser/profile", "naukri.com/mnjuser"]):
                    logged_in = True
                    print(f"\n[+] Login detected on URL: {current_url}")
                    break

                if any(token in cookie_names for token in ["nauk_at", "_nk", "NAUKRI_USER"]):
                    logged_in = True
                    print(f"\n[+] Auth token detected in cookies: {[c for c in cookie_names if c in ['nauk_at', '_nk', 'NAUKRI_USER']]}")
                    break
            except Exception:
                # Browser or window closed by user
                break

        if logged_in:
            print("[*] Saving authenticated session state...")
            await context.storage_state(path=str(STATE_FILE))
            print("[+] Session state saved successfully to .auth/naukri_state.json!")
            print("[*] Closing browser in 3 seconds...")
            await asyncio.sleep(3)
        else:
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
        print("=" * 60)
    else:
        print("[!] Warning: Could not verify saved session file.")

if __name__ == "__main__":
    asyncio.run(manual_naukri_login())
