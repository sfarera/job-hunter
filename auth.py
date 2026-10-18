import os
import json
import asyncio
from playwright.async_api import async_playwright
from browser import get_browser, get_context, save_state, STATE_FILE

async def manual_login():
    """Opens a headed browser for the user to manually log in to LinkedIn."""
    print("=" * 60)
    print("LinkedIn Authentication Assistant")
    print("=" * 60)
    print("Launching headed browser for manual login...")
    print("1. Log in to your LinkedIn account in the browser.")
    print("2. Complete any 2FA or verification prompts if asked.")
    print("3. Once logged in and on your LinkedIn feed, the session")
    print("   will be automatically detected and saved.")
    print("=" * 60)
    
    async with async_playwright() as p:
        # Launch headed browser for manual login
        browser = await get_browser(p, headless=False)
        context = await get_context(browser, persist=False)
        page = await context.new_page()
        
        await page.goto("https://www.linkedin.com/login")
        
        logged_in = False
        print("Waiting for login... (polling every 2s, up to 5 minutes)")
        
        for _ in range(150): # up to 5 minutes
            await asyncio.sleep(2)
            try:
                cookies = await context.cookies()
                cookie_names = [c["name"] for c in cookies]
                current_url = page.url
                
                # 'li_at' is LinkedIn's main authentication session cookie
                if "li_at" in cookie_names or "/feed" in current_url:
                    logged_in = True
                    print("\n[SUCCESS] Login detected!")
                    print("Saving session state to .auth/state.json...")
                    await save_state(context)
                    print("Session saved successfully!")
                    print("Closing browser...")
                    await asyncio.sleep(2)
                    break
            except Exception:
                # Browser or tab might have been closed by user
                break
                
        if not logged_in:
            print("\nBrowser closed or timeout reached. Attempting to save session...")
            try:
                await save_state(context)
            except Exception as e:
                print(f"Could not save state: {e}")
                
        try:
            await browser.close()
        except Exception:
            pass
            
    # Verify saved session
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            saved_cookies = [c["name"] for c in data.get("cookies", [])]
            if "li_at" in saved_cookies:
                print("\n" + "=" * 60)
                print("Authentication verified successfully! (li_at cookie present)")
                print("You can now run: python main.py")
                print("=" * 60)
                return
        except Exception:
            pass
            
    print("\n" + "=" * 60)
    print("[WARNING] Could not verify authenticated session.")
    print("If you were unable to finish logging in, please run 'python auth.py' again.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(manual_login())
