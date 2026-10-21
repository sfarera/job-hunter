import os
import re
import asyncio
import yaml
import urllib.parse
from datetime import datetime
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv
from browser import get_browser, get_context, save_state
from agent import execute_smart_form_fill, get_easy_apply_modal

load_dotenv()

JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "240"))

def load_profile():
    profile_name = os.getenv("PROFILE", "shubham_profile")
    profile_path = os.path.join("profiles", f"{profile_name}.yaml")
    if not os.path.exists(profile_path):
        print(f"ERROR: Profile not found at '{profile_path}'. Check your PROFILE setting in .env.")
        raise FileNotFoundError(profile_path)
    print(f"Loading profile: {profile_path}")
    with open(profile_path, "r") as f:
        return yaml.safe_load(f)

def load_applied_jobs(filepath="applied_jobs.txt"):
    """Load previously applied jobs into a set."""
    if not os.path.exists(filepath):
        return set()
    with open(filepath, "r") as f:
        # Extract just the URL portion before the ' | ' if a timestamp exists
        return set(line.split(" | ")[0].strip() for line in f if line.strip())

def save_applied_job(job_url, filepath="applied_jobs.txt"):
    """Append a successfully applied job to the tracking file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(filepath, "a") as f:
        f.write(f"{job_url} | {timestamp}\n")

def build_search_url(keywords, locations, profile=None):
    base_url = "https://www.linkedin.com/jobs/search/?"
    if isinstance(keywords, list):
        # Format top keywords with Boolean OR for effective LinkedIn search matching
        top_kws = keywords[:3] if len(keywords) > 3 else keywords
        query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in top_kws)
    else:
        query = str(keywords)

    keyword_str = urllib.parse.quote(query)
    location_str = urllib.parse.quote(locations[0]) if locations else "Remote"
    
    # f_AL=true  = Easy Apply only
    # f_I=96,4,556,6 = IT Services & Consulting, Software Development, Technology & Information, Computer Hardware
    # f_WT=2,3,4 = Remote (2), Hybrid (3), On-site (4) — keeps all
    # f_JT=F = Full-time only (filters out Contract, Part-time, Temporary)
    exclude_contract = True
    if profile:
        exclude_contract = profile.get("job_preferences", {}).get("exclude_contract", True)
    job_type_param = "&f_JT=F" if exclude_contract else ""

    params = (
        f"keywords={keyword_str}"
        f"&location={location_str}"
        f"&f_AL=true"
        f"&f_I=96%2C4%2C556%2C6"
        f"&f_WT=2%2C3%2C4"
        f"{job_type_param}"
    )
    return base_url + params

CONTRACT_KEYWORDS = [
    "contract",
    "contractor",
    "c2c",
    "c2h",
    "corp to corp",
    "corp-to-corp",
    "contract-to-hire",
    "contract to hire",
    "fixed term",
    "fixed-term",
    "temporary",
    "temp",
    "freelance",
    "part-time",
    "part time",
    "hourly",
    "internship",
    "intern",
]

def is_contract_job(text: str) -> tuple[bool, str]:
    """
    Checks if a job title, description, badge, or card snippet indicates a contract,
    freelance, temporary, or non-permanent position.
    Returns (is_contract: bool, reason: str).
    """
    if not text:
        return False, ""
    
    text_lower = text.lower()
    
    # Check for duration patterns like "6-month contract", "12 months contract", "6 month", etc.
    month_match = re.search(
        r"\b\d+\s*[-_ ]*(?:month|year|week|day|mo|yr)s?\s*(?:contract|c2c|c2h|temp|fixed[\s-]*term)\b",
        text_lower
    )
    if month_match:
        return True, f"Found duration contract '{month_contract_match.group(0) if 'month_contract_match' in locals() else month_match.group(0)}'"
        
    for kw in CONTRACT_KEYWORDS:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, text_lower):
            return True, f"Matched contract term '{kw}'"
            
    return False, ""

def is_job_relevant(job_title: str, profile: dict) -> bool:
    """
    Checks if a job title contains at least one keyword from the profile.
    Case-insensitive. Rejects contract roles if exclude_contract is True.
    """
    if profile.get("job_preferences", {}).get("exclude_contract", True):
        is_c, _ = is_contract_job(job_title)
        if is_c:
            return False

    keywords = profile.get("job_preferences", {}).get("keywords", [])
    title_lower = job_title.lower()
    
    return any(kw.lower() in title_lower for kw in keywords)

def is_location_allowed(text: str, profile: dict) -> tuple[bool, str]:
    """
    Checks if text (from a job card, header, or job details) contains any excluded location.
    Returns (allowed: bool, reason: str).
    """
    if not text:
        return True, ""
    
    excluded = profile.get("job_preferences", {}).get("excluded_locations", [])
    # Always include common variants for explicitly blacklisted locations
    if not excluded:
        excluded = ["Israel", "Tel Aviv"]
        
    text_lower = text.lower()
    for loc in excluded:
        loc_clean = loc.strip().lower()
        if not loc_clean:
            continue
        pattern = r"\b" + re.escape(loc_clean) + r"\b"
        if re.search(pattern, text_lower):
            return False, f"Matched excluded location '{loc}'"
            
    return True, ""

async def process_job(page: Page, job_url: str, profile: dict):
    print(f"\nProcessing job: {job_url}")
    await page.goto(job_url, wait_until="domcontentloaded")
    await asyncio.sleep(0.8)  # Brief delay for dynamic scripts / hydration
    
    # --- Relevance check: skip irrelevant jobs before doing anything ---
    try:
        job_title_el = page.locator("h1.t-24, h1.jobs-unified-top-card__job-title, .job-details-jobs-unified-top-card__job-title h1, h1[class*='job-title']").first
        job_title = (await job_title_el.inner_text()).strip() if await job_title_el.count() > 0 else ""
    except Exception:
        job_title = ""
    
    if job_title and not is_job_relevant(job_title, profile):
        is_c, r = is_contract_job(job_title)
        if is_c:
            print(f"  Skipping contract job: {r} in title '{job_title}'")
        else:
            print(f"  Skipping irrelevant job: '{job_title}'")
        return False
    
    if job_title:
        print(f"  Job title: '{job_title}' — relevant, proceeding.")

    # --- Contract check: inspect page employment details & insights ---
    if profile.get("job_preferences", {}).get("exclude_contract", True):
        try:
            job_details_snippet = await page.evaluate("""() => {
                const selectors = [
                    '.job-details-jobs-unified-top-card__job-insight',
                    '.jobs-unified-top-card__job-insight',
                    'li[class*="job-insight"]',
                    'span[class*="job-insight"]',
                    '.job-details-jobs-unified-top-card__primary-description',
                    '.job-details-jobs-unified-top-card',
                    '.jobs-unified-top-card'
                ];
                const matched = [];
                for (const s of selectors) {
                    const elements = Array.from(document.querySelectorAll(s));
                    for (const el of elements) {
                        if (el && el.innerText) matched.push(el.innerText);
                    }
                }
                return matched.join(' ');
            }""")
        except Exception:
            job_details_snippet = ""

        is_c_insight, c_reason = is_contract_job(job_details_snippet)
        if is_c_insight:
            print(f"  Skipping job: {c_reason} in employment type details ({job_url})")
            return False

    # --- Location check: reject jobs in excluded locations ---
    try:
        page_location_snippet = await page.evaluate("""() => {
            const selectors = [
                '.job-details-jobs-unified-top-card',
                '.jobs-unified-top-card',
                '[class*="topcard"]',
                '[class*="top-card"]',
                '.job-details-jobs-unified-top-card__primary-description-container',
                'div[data-view-name="job-details"]'
            ];
            for (const s of selectors) {
                const el = document.querySelector(s);
                if (el && el.innerText.trim().length > 10) {
                    return el.innerText;
                }
            }
            return document.title + ' ' + (document.body ? document.body.innerText.slice(0, 3000) : '');
        }""")
    except Exception:
        page_location_snippet = ""
        
    allowed, reason = is_location_allowed(page_location_snippet, profile)
    if not allowed:
        print(f"  Skipping job: {reason} ({job_url})")
        return False
    
    # Check for Easy Apply button
    try:
        easy_apply_locator = page.locator(
            "button.jobs-apply-button, "
            "button:has-text('Easy Apply'), "
            "[aria-label*='Easy Apply' i]"
        ).first
        
        try:
            await easy_apply_locator.wait_for(state="visible", timeout=6000)
        except Exception:
            pass
        
        if await easy_apply_locator.is_visible():
            print("Found Easy Apply button. Clicking...")
            clicked = False
            for attempt in range(3):
                try:
                    await easy_apply_locator.click(timeout=5000)
                    clicked = True
                    break
                except Exception as click_err:
                    err_msg = str(click_err).lower()
                    if ("detached" in err_msg or "timeout" in err_msg) and attempt < 2:
                        print(f"  Easy Apply click retry {attempt + 1}/3 due to DOM change...")
                        await asyncio.sleep(1)
                        continue
                    raise click_err

            if not clicked:
                print("Could not click Easy Apply button.")
                return False
            
            modal = await get_easy_apply_modal(page, timeout=15000)
            if not await modal.is_visible():
                print("Easy Apply modal did not appear.")
                return False
            
            await asyncio.sleep(0.5)  # Brief pause for modal animation and buttons to mount

            # AI Agent takes over here
            print("Form opened. Handing over to Smart AI Agent.")
            success = await execute_smart_form_fill(page, profile)
            return success
        else:
            print("No Easy Apply button found on this job.")
            return False
    except Exception as e:
        print(f"Error or timeout finding Easy Apply button: {e}")
        return False

async def has_valid_linkedin_session(page: Page) -> bool:
    """Detect expired auth before starting the job loop."""
    url = page.url.lower()
    if "/login" in url or "checkpoint" in url:
        return False

    login_indicators = page.locator("input[name='session_key'], input[name='session_password'], text=/sign in/i")
    try:
        return not await login_indicators.first.is_visible(timeout=2500)
    except Exception:
        return True

async def dismiss_easy_apply_modal(page: Page):
    """Best-effort cleanup so one failed application does not block the next job."""
    try:
        discard_selectors = (
            "button:has-text('Discard'), "
            "[data-testid='dialog'] button:has-text('Discard'), "
            "button[data-control-name*='discard'], "
            "button[data-test-dialog-secondary-action]"
        )

        # 1. If 'Save this application?' popup is already open, click Discard immediately
        discard_btn = page.locator(discard_selectors).first
        if await discard_btn.count() > 0 and await discard_btn.is_visible():
            await discard_btn.click(timeout=3000)
            await asyncio.sleep(1)
            return

        # 2. Otherwise click Dismiss (X)
        dismiss_btn = page.locator(
            "dialog[open] button[aria-label='Dismiss'], "
            "dialog[open] button:has-text('Dismiss'), "
            "[data-testid='dialog'] button[aria-label='Dismiss'], "
            "[data-testid='dialog'] button:has-text('Dismiss'), "
            "[role='dialog'] button[aria-label='Dismiss'], "
            ".artdeco-modal button[aria-label='Dismiss'], "
            "button[aria-label='Dismiss']"
        ).first
        if await dismiss_btn.count() > 0 and await dismiss_btn.is_visible():
            await dismiss_btn.click(timeout=3000)
            await asyncio.sleep(1)

        # 3. Handle the 'Save this application?' confirmation popup
        discard_btn = page.locator(discard_selectors).first
        try:
            await discard_btn.wait_for(state="visible", timeout=3000)
            await discard_btn.click(timeout=3000)
            await asyncio.sleep(0.5)
        except Exception:
            pass
    except Exception:
        pass

async def main():
    print("Starting Job Hunter...")
    profile = load_profile()
    keywords = profile.get("job_preferences", {}).get("keywords", [])
    locations = profile.get("job_preferences", {}).get("locations", [])
    
    if not keywords or not locations:
        print("Error: Keywords and locations must be defined in profile.")
        return

    search_url = build_search_url(keywords, locations, profile)
    print(f"Search URL: {search_url}")
    
    async with async_playwright() as p:
        browser = await get_browser(p, headless=False)
        # Attempt to load persistent context. Ensure user has run auth.py first!
        context = await get_context(browser, persist=True)
        page = await context.new_page()
        
        print("Navigating to search results...")
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        current_url = page.url
        if not await has_valid_linkedin_session(page) or any(auth_kw in current_url for auth_kw in ["/login", "/uas/login", "checkpoint", "authwall"]):
            print("\n" + "=" * 60)
            print("[ERROR] LinkedIn session is expired or not authenticated!")
            print(f"Current page URL: {current_url}")
            print("LinkedIn requires an active session to search and Easy Apply.")
            print("Please run:")
            print("    python auth.py")
            print("to log in and save your session, then re-run 'python main.py'.")
            print("=" * 60 + "\n")
            await browser.close()
            return
        
        # Scrape job cards (robust method)
        job_links = []
        max_apps = int(os.getenv("MAX_APPLICATIONS", "15"))
        try:
            # Wait for the job list to appear with multiple fallback selectors
            job_list_selector = ".jobs-search-results__list, .jobs-search-results-list, .scaffold-layout__list, .scaffold-layout__list-container"
            try:
                await page.wait_for_selector(job_list_selector, timeout=15000)
            except Exception:
                # If container selector times out, check if any job links are already loaded
                if await page.locator("a[href*='/jobs/view/']").count() == 0:
                    raise
            
            # Scroll the job list panel to lazy-load more cards
            target_links = max(max_apps * 5, max_apps)
            print(f"Collecting up to {target_links} candidate job links...")
            for scroll_pass in range(6): # Fast scroll passes
                # High-speed DOM evaluation in a single browser call (takes ~5ms)
                cards_data = await page.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll(
                        'li[data-occludable-job-id], .jobs-search-results__list-item, div.job-card-container, div[data-view-name="job-card"]'
                    ));
                    return cards.map(c => {
                        const link = c.querySelector('a[href*="/jobs/view/"]');
                        return {
                            text: c.innerText || '',
                            href: link ? link.getAttribute('href') : ''
                        };
                    }).filter(item => item.href);
                }""")

                for item in cards_data:
                    card_text = item.get("text", "")
                    href = item.get("href", "")

                    allowed, _ = is_location_allowed(card_text, profile)
                    if not allowed:
                        continue

                    if profile.get("job_preferences", {}).get("exclude_contract", True):
                        is_c, _ = is_contract_job(card_text)
                        if is_c:
                            continue

                    clean_url = "https://www.linkedin.com" + href.split("?")[0] if href.startswith("/") else href.split("?")[0]
                    if clean_url not in job_links:
                        job_links.append(clean_url)

                if len(job_links) >= target_links:
                    break

                # Scroll the job list panel down to load more cards
                await page.evaluate("""
                    const list = document.querySelector('.jobs-search-results__list, .jobs-search-results-list, .scaffold-layout__list, .scaffold-layout__list-container');
                    if (list) list.scrollBy(0, 800);
                """)
                await asyncio.sleep(0.4) # Fast scroll wait
            
            print(f"Found {len(job_links)} unique job links after scrolling.")
            # We no longer hardcode a limit here, we check max_applications below
        except Exception as e:
            print(f"Error scraping job list: {e}")
            
        print(f"Found {len(job_links)} jobs to process.")
        
        applied_jobs_set = load_applied_jobs()
        success_count = 0
        successful_jobs = []
        

        for link in job_links:
            if success_count >= max_apps:
                print(f"\\n[INFO] Reached maximum requested applications ({max_apps}). Stopping.")
                break
                
            if not link.startswith("http"):
                continue
                
            # Normalize the link to avoid query param mismatches
            clean_link = link.split('?')[0]
            if clean_link in applied_jobs_set:
                print(f"Skipping already applied job: {clean_link}")
                continue
                
            success = False
            try:
                success = await asyncio.wait_for(
                    process_job(page, link, profile),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
                if not success:
                    await dismiss_easy_apply_modal(page)
            except asyncio.TimeoutError:
                print(f"Timed out processing job after {JOB_TIMEOUT_SECONDS}s: {link}")
                await dismiss_easy_apply_modal(page)
            except Exception as e:
                print(f"Error processing job {link}: {e}")
                await dismiss_easy_apply_modal(page)
            if success:
                success_count += 1
                successful_jobs.append(link)
                save_applied_job(clean_link)
                applied_jobs_set.add(clean_link)
                
            # Add human-like delay
            await asyncio.sleep(2)
            
        print("\n=================================")
        print(f"Job Hunter Run Complete!")
        print(f"Total Successfully Applied: {success_count}")
        for job in successful_jobs:
            print(f" - {job}")
        print("=================================\n")
            
        await save_state(context)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
