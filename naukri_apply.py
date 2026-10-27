#!/usr/bin/env python3
"""
Naukri 1-Click Auto-Apply Bot
Automates job discovery, 1-click apply, and questionnaire drawer answering
for 8+ Yrs Senior Java / Spring Boot roles in Pune/Remote.

Features:
- Real Chrome binary execution to bypass Akamai WAF
- Intelligent questionnaire solver for chatbot drawer:
    * Notice Period: 2 months / 60 days
    * Total Experience: 8 years
    * Relevant Java Experience: 8 years
    * Current CTC: 18.4 LPA
    * Expected CTC: 30 LPA
    * Location / Relocation: Pune / Yes
- CSV ledgers for both 1-click applied jobs and external company site redirects
- Humanized random jitter delays (18-30s) to maintain account safety
"""

import os
import sys
import csv
import json
import random
import asyncio
import logging
import argparse
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("naukri_apply.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("NaukriApply")

AUTH_STATE = Path(".auth/naukri_state.json")
APPLIED_LEDGER = Path("naukri_applied_jobs.csv")
EXTERNAL_LEDGER = Path("naukri_external_jobs.csv")

# Candidate profile parameters
CANDIDATE_PROFILE = {
    "notice_period": "2 month",
    "notice_period_days": "60",
    "total_experience": "8",
    "relevant_experience": "8",
    "current_ctc_lpa": "18.4",
    "current_ctc_inr": "1840000",
    "expected_ctc_lpa": "30",
    "expected_ctc_inr": "3000000",
    "current_location": "Pune",
    "preferred_location": "Pune",
}

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""

def init_ledgers():
    if not APPLIED_LEDGER.exists():
        with open(APPLIED_LEDGER, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "job_id", "title", "company", "experience", "location", "url", "status"])

    if not EXTERNAL_LEDGER.exists():
        with open(EXTERNAL_LEDGER, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "job_id", "title", "company", "experience", "location", "url"])

def get_applied_ids() -> set:
    if not APPLIED_LEDGER.exists():
        return set()
    applied = set()
    with open(APPLIED_LEDGER, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("job_id"):
                applied.add(row["job_id"])
            if row.get("url"):
                applied.add(row["url"])
    return applied

def record_applied_job(job_info: dict, status: str = "Applied"):
    with open(APPLIED_LEDGER, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            job_info.get("id", ""),
            job_info.get("title", ""),
            job_info.get("company", ""),
            job_info.get("experience", ""),
            job_info.get("location", ""),
            job_info.get("url", ""),
            status
        ])

def record_external_job(job_info: dict):
    with open(EXTERNAL_LEDGER, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            job_info.get("id", ""),
            job_info.get("title", ""),
            job_info.get("company", ""),
            job_info.get("experience", ""),
            job_info.get("location", ""),
            job_info.get("url", "")
        ])

async def solve_chatbot_drawer(page: Page, max_rounds: int = 5) -> bool:
    """
    Intelligently inspects and answers questions presented in the chatbot drawer.
    """
    drawer_selector = "._chatBotContainer, div[class*='chatBot'], div.chatbot_DrawerContentWrapper"
    
    for round_num in range(1, max_rounds + 1):
        drawer = page.locator(drawer_selector).first
        if await drawer.count() == 0 or not await drawer.is_visible():
            # Drawer closed or redirect happened
            break

        # Check if already completed
        drawer_text = await drawer.inner_text()
        if any(w in drawer_text.lower() for w in ["successfully applied", "application sent", "thank you", "saved application"]):
            logger.info("  [Chatbot] Application completion message detected.")
            return True

        logger.info(f"  [Chatbot] Question round {round_num}...")
        answered = False

        # Extract latest question text
        question_items = await page.eval_on_selector_all(
            "._chatBotContainer li.botItem, ._chatBotContainer .chatbot_ListItem",
            "elements => elements.map(e => e.innerText.trim()).filter(t => t.length > 0)"
        )
        current_question = question_items[-1].lower() if question_items else ""
        logger.info(f"  [Chatbot Question]: {current_question[:80]}...")

        # 1. Notice Period Question
        if any(w in current_question for w in ["notice", "period", "joining", "how soon", "available"]):
            opt = page.locator("._chatBotContainer label:has-text('1 month'), ._chatBotContainer span:has-text('2 month'), ._chatBotContainer li:has-text('1 month'), ._chatBotContainer label:has-text('60 days')").first
            if await opt.count() > 0 and await opt.is_visible():
                await opt.click()
                logger.info("  -> Selected: '2 month'")
                answered = True
            else:
                input_box = page.locator("._chatBotContainer input[type='text'], ._chatBotContainer textarea").first
                if await input_box.count() > 0 and await input_box.is_visible():
                    await input_box.fill(CANDIDATE_PROFILE["notice_period"])
                    logger.info(f"  -> Entered notice period: {CANDIDATE_PROFILE['notice_period']}")
                    answered = True

        # 2. Experience Question (Total, AI, Core Stack, or Other Tech)
        elif any(w in current_question for w in ["experience", "years", "relevant"]):
            input_box = page.locator("._chatBotContainer input[type='text'], ._chatBotContainer textarea").first
            if await input_box.count() > 0 and await input_box.is_visible():
                if any(w in current_question for w in ["ai", "copilot", "chatgpt", "genai", "generative ai", "llm"]):
                    exp_val = "1"
                elif any(w in current_question for w in ["java", "spring", "microservice", "sql", "hibernate", "total", "overall"]):
                    exp_val = CANDIDATE_PROFILE["total_experience"]
                else:
                    # Non-core tech stack
                    exp_val = "2"
                await input_box.fill(exp_val)
                logger.info(f"  -> Entered experience: {exp_val} years")
                answered = True
            else:
                # Look for radio option containing '8' or '5-8'
                opt = page.locator("._chatBotContainer label:has-text('8'), ._chatBotContainer label:has-text('5-8'), ._chatBotContainer label:has-text('7-10')").first
                if await opt.count() > 0 and await opt.is_visible():
                    await opt.click()
                    logger.info("  -> Selected experience option")
                    answered = True

        # 3. Current CTC Question
        elif any(w in current_question for w in ["current ctc", "current salary", "present ctc", "fixed ctc"]):
            input_box = page.locator("._chatBotContainer input[type='text'], ._chatBotContainer textarea").first
            if await input_box.count() > 0 and await input_box.is_visible():
                val = CANDIDATE_PROFILE["current_ctc_lpa"] if "lakh" in current_question or "lpa" in current_question else CANDIDATE_PROFILE["current_ctc_inr"]
                await input_box.fill(val)
                logger.info(f"  -> Entered Current CTC: {val}")
                answered = True

        # 4. Expected CTC Question
        elif any(w in current_question for w in ["expected ctc", "expected salary"]):
            input_box = page.locator("._chatBotContainer input[type='text'], ._chatBotContainer textarea").first
            if await input_box.count() > 0 and await input_box.is_visible():
                val = CANDIDATE_PROFILE["expected_ctc_lpa"] if "lakh" in current_question or "lpa" in current_question else CANDIDATE_PROFILE["expected_ctc_inr"]
                await input_box.fill(val)
                logger.info(f"  -> Entered Expected CTC: {val}")
                answered = True

        # 5. Relocation / Remote / Location / Yes-No questions
        elif any(w in current_question for w in ["relocate", "relocation", "pune", "willing", "ready", "remote", "wfh", "work from home"]):
            yes_opt = page.locator("._chatBotContainer label:has-text('Yes'), ._chatBotContainer span:has-text('Yes')").first
            if await yes_opt.count() > 0 and await yes_opt.is_visible():
                await yes_opt.click()
                logger.info("  -> Selected: 'Yes'")
                answered = True

        # Fallback: If an input box exists and is empty, answer with total experience or Yes
        if not answered:
            input_box = page.locator("._chatBotContainer input[type='text'], ._chatBotContainer textarea").first
            if await input_box.count() > 0 and await input_box.is_visible():
                val = await input_box.input_value()
                if not val:
                    await input_box.fill(CANDIDATE_PROFILE["total_experience"])
                    logger.info(f"  -> Fallback filled: {CANDIDATE_PROFILE['total_experience']}")
                    answered = True

        await asyncio.sleep(1.0)

        # Click the blue Save / Send button
        save_btn = page.locator("div.sendMsg, [class*='sendMsg'], div.send:not(.disabled), button:has-text('Save')").first
        if await save_btn.count() > 0 and await save_btn.is_visible():
            await save_btn.click()
            logger.info("  -> Clicked chatbot Save/Send button.")
            await asyncio.sleep(2.5)

        # Check if URL redirected to saveApply
        if "saveApply" in page.url or "myapply" in page.url:
            logger.info("  -> Success: Redirected to saveApply confirmation page.")
            return True

    return "saveApply" in page.url or "myapply" in page.url

async def apply_to_job(page: Page, job: dict) -> str:
    """
    Navigates to job URL, clicks Apply, handles questionnaire if needed,
    and returns status: 'Applied', 'External', 'AlreadyApplied', or 'Failed'.
    """
    logger.info(f"Inspecting job: {job['title']} @ {job['company']}")
    try:
        await page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.0)

        # Check if already applied
        already_applied = page.locator("button:has-text('Already Applied'), button[disabled]:has-text('Applied')").first
        if await already_applied.count() > 0 and await already_applied.is_visible():
            logger.info("  [Status] Already applied to this job previously. Skipping.")
            return "AlreadyApplied"

        # Check if external company site application
        external_btn = page.locator("#company-site-button, button:has-text('Apply on company site'), a:has-text('Apply on company site')").first
        if await external_btn.count() > 0 and await external_btn.is_visible():
            logger.info("  [Status] Company site application. Saving to external ledger.")
            record_external_job(job)
            return "External"

        # Locate 1-click apply button
        apply_btn = page.locator("#apply-button, button.apply-button, button:has-text('Apply')").first
        if await apply_btn.count() == 0 or not await apply_btn.is_visible():
            logger.warning("  [Warning] No Apply button found on page.")
            return "NoButton"

        btn_text = (await apply_btn.inner_text()).strip()
        if "Already Applied" in btn_text:
            return "AlreadyApplied"

        logger.info(f"  Clicking Apply button ('{btn_text}')...")
        await apply_btn.click()
        await asyncio.sleep(2.5)

        # Check if redirected directly to saveApply confirmation
        if "saveApply" in page.url or "myapply" in page.url:
            logger.info("  [Success] Direct 1-click apply succeeded!")
            record_applied_job(job, "Applied")
            return "Applied"

        # Check if chatbot drawer opened
        drawer = page.locator("._chatBotContainer, div[class*='chatBot']").first
        if await drawer.count() > 0 and await drawer.is_visible():
            logger.info("  Chatbot questionnaire drawer opened. Resolving answers...")
            success = await solve_chatbot_drawer(page)
            if success:
                logger.info("  [Success] Questionnaire solved & job application submitted!")
                record_applied_job(job, "Applied")
                return "Applied"
            else:
                logger.warning("  [Warning] Questionnaire could not be completed.")
                return "DrawerPending"

        # Final check of page text for confirmation
        page_content = await page.content()
        if "Applied" in page_content or "successfully" in page_content:
            record_applied_job(job, "Applied")
            return "Applied"

        return "Unknown"

    except Exception as e:
        logger.error(f"  [Error] Failed to process job {job['url']}: {e}")
        return "Failed"

async def run_auto_apply(
    query_slug: str = "senior-java-developer-jobs-in-pune",
    experience: int = 8,
    job_age: int = 7,
    limit: int = 5,
    headless: bool = True
):
    init_ledgers()
    applied_ids = get_applied_ids()
    logger.info(f"Naukri Auto-Apply starting. Ledger contains {len(applied_ids)} existing entries.")
    logger.info(f"Search Query: {query_slug} | Experience: {experience} Yrs | Job Age: {job_age} Days | Max Applications: {limit}")

    if not AUTH_STATE.exists():
        logger.error(f"Auth file not found at {AUTH_STATE}. Please run naukri_auth.py first!")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            channel="chrome",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context: BrowserContext = await browser.new_context(
            storage_state=str(AUTH_STATE),
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        await context.add_init_script(STEALTH_JS)
        page = await context.new_page()

        applied_count = 0
        external_count = 0
        page_num = 1
        max_search_pages = 6

        # Create separate tab for job detail pages to keep search page alive
        job_page = await context.new_page()

        while applied_count < limit and page_num <= max_search_pages:
            search_suffix = "" if page_num == 1 else f"-{page_num}"
            search_url = f"https://www.naukri.com/{query_slug}{search_suffix}?experience={experience}&jobAge={job_age}"
            logger.info(f"\n==================================================")
            logger.info(f"Navigating to search page {page_num}: {search_url}")
            logger.info(f"Progress so far: {applied_count}/{limit} applied")
            logger.info(f"==================================================")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4.0)

            # Scrape job cards from search results
            raw_jobs = await page.eval_on_selector_all(
                ".srp-jobtuple-wrapper, div[data-job-id], article.jobTuple",
                """elements => elements.map(e => {
                    const titleEl = e.querySelector('a.title, [class*="title"] a, a[class*="title"]');
                    const compEl = e.querySelector('a.comp-name, [class*="comp-name"], a[class*="subTitle"]');
                    const expEl = e.querySelector('.exp-wrap, [class*="exp"]');
                    const locEl = e.querySelector('.loc-wrap, [class*="loc"]');
                    const jobId = e.getAttribute('data-job-id') || (titleEl ? (titleEl.href.match(/(\\d{10,})/i) || ['',''])[1] : '');
                    return {
                        id: jobId,
                        title: titleEl ? titleEl.innerText.trim() : '',
                        url: titleEl ? titleEl.href : '',
                        company: compEl ? compEl.innerText.trim() : '',
                        experience: expEl ? expEl.innerText.trim() : '',
                        location: locEl ? locEl.innerText.trim() : ''
                    };
                }).filter(j => j.title && j.url)"""
            )

            logger.info(f"Discovered {len(raw_jobs)} job listings on page {page_num}.")
            
            # Filter out already applied
            eligible_jobs = [j for j in raw_jobs if j["id"] not in applied_ids and j["url"] not in applied_ids]
            logger.info(f"{len(eligible_jobs)} new eligible jobs to process on page {page_num}.")

            if not eligible_jobs and not raw_jobs:
                logger.info(f"No more jobs found. Ending search.")
                break

            for idx, job in enumerate(eligible_jobs):
                if applied_count >= limit:
                    logger.info(f"Target limit of {limit} applications reached for this session.")
                    break

                logger.info(f"\n[{idx + 1}/{len(eligible_jobs)} on p.{page_num}] Processing: {job['title']} @ {job['company']}")
                status = await apply_to_job(job_page, job)

                if status == "Applied":
                    applied_count += 1
                    applied_ids.add(job["id"])
                    applied_ids.add(job["url"])
                    logger.info(f"🎯 Total Applied This Session: {applied_count}/{limit}")
                    # Safe human cooldown between applications
                    cooldown = random.randint(18, 30)
                    logger.info(f"Sleeping {cooldown}s (Safe Human Pacing)...")
                    await asyncio.sleep(cooldown)

                elif status == "External":
                    external_count += 1
                    applied_ids.add(job["id"])
                    applied_ids.add(job["url"])
                    await asyncio.sleep(2.0)

                elif status == "AlreadyApplied":
                    record_applied_job(job, "AlreadyApplied")
                    applied_ids.add(job["id"])
                    applied_ids.add(job["url"])
                    await asyncio.sleep(1.5)

                else:
                    await asyncio.sleep(2.0)

            page_num += 1

        logger.info("\n" + "=" * 50)
        logger.info(f"SESSION SUMMARY:")
        logger.info(f" - Successfully Applied: {applied_count}")
        logger.info(f" - Saved to External Ledger: {external_count}")
        logger.info(f" - Total Ledger Entries: {len(get_applied_ids())}")
        logger.info("=" * 50)

        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naukri 1-Click Auto-Apply Bot")
    parser.add_argument("--query", default="senior-java-developer-jobs-in-pune", help="Naukri search URL slug")
    parser.add_argument("--experience", type=int, default=8, help="Years of experience filter")
    parser.add_argument("--job-age", type=int, default=7, help="Job posted within days filter")
    parser.add_argument("--limit", type=int, default=5, help="Max jobs to apply to in this run")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    args = parser.parse_args()

    asyncio.run(run_auto_apply(
        query_slug=args.query,
        experience=args.experience,
        job_age=args.job_age,
        limit=args.limit,
        headless=args.headless
    ))
