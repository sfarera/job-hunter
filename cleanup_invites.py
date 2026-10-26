"""
Cleanup Pending LinkedIn Invitations.
Safely withdraws unaccepted connection invitations to restore LinkedIn invitation quotas.
- Targets stale unaccepted sent invites
- Confirms each withdrawal through the native LinkedIn confirmation dialog
- Uses natural human pauses between actions
"""

import asyncio
import random
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent
AUTH_STATE = BASE_DIR / ".auth/state.json"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""

async def cleanup_invitations(target_count: int = 50):
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

        print("=== Starting Pending Invitations Cleanup ===")
        url = "https://www.linkedin.com/mynetwork/invitation-manager/sent/"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3500)

        withdrawn = 0
        consecutive_failures = 0

        while withdrawn < target_count:
            # Find all withdraw buttons currently rendered
            withdraw_btns = page.locator("a[aria-label*='Withdraw invitation sent to'], a:has-text('Withdraw')")
            count = await withdraw_btns.count()

            if count == 0:
                print("[*] No more withdraw buttons visible on current view. Reloading page...")
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                withdraw_btns = page.locator("a[aria-label*='Withdraw invitation sent to'], a:has-text('Withdraw')")
                count = await withdraw_btns.count()
                if count == 0:
                    print("[!] No pending invitations found to withdraw.")
                    break

            # Click the first withdraw button
            target_btn = withdraw_btns.first
            label = await target_btn.get_attribute("aria-label") or "invitation"
            try:
                await target_btn.click()
                await asyncio.sleep(random.uniform(0.6, 1.2))

                # Handle confirmation dialog
                confirm_btn = page.locator("dialog button:has-text('Withdraw'), [data-testid='dialog'] button:has-text('Withdraw')").first
                await confirm_btn.wait_for(state="visible", timeout=4000)
                await confirm_btn.click()
                
                withdrawn += 1
                consecutive_failures = 0
                print(f"[{withdrawn}/{target_count}] Successfully withdrawn: {label}")
                
                # Human pacing pause between withdrawals
                await asyncio.sleep(random.uniform(1.2, 2.5))
            except Exception as e:
                consecutive_failures += 1
                print(f"[-] Issue withdrawing ({e}). Retrying... (attempt {consecutive_failures})")
                if consecutive_failures >= 3:
                    print("[*] Refreshing view after consecutive issues...")
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(3500)
                    consecutive_failures = 0

        # Check final pending count
        heading = await page.locator("a[href*='sent']").all_text_contents()
        remaining = [h.strip() for h in heading if "People" in h]
        remaining_str = remaining[0] if remaining else "Unknown"

        print(f"\n=== Cleanup Finished: {withdrawn} invitations withdrawn ===")
        print(f"=== Remaining in Queue: {remaining_str} ===")
        await browser.close()
        return withdrawn, remaining_str

if __name__ == "__main__":
    count_to_remove = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    asyncio.run(cleanup_invitations(count_to_remove))
