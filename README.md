# Job Hunter Agent

An automated job application agent that uses Playwright and Python to apply for jobs on LinkedIn.

## Prerequisites
- Python 3.9+
- Chrome/Chromium browser

## Setup

1. **Install dependencies**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure your profile**:
   Copy the template and fill in your details:
   ```bash
   cp profile_template.yaml profile.yaml
   ```
   Open `profile.yaml` and add your real information, skills, and preferences.

3. **Authenticate with LinkedIn**:
   Run the authentication script to perform a one-time manual login. This saves your session securely so the bot can run headlessly later.
   ```bash
   python auth.py
   ```
   *A browser window will open. Log into your LinkedIn account. Once logged in, simply close the browser window.*

3. **LinkedIn Stealth Networking**:
   Run the human-paced networking engine (25 invites/day cap, 45-75s pacing):
   ```bash
   python stealth_connect.py --limit 25
   ```

## Naukri Automation Suite

### 1. One-Time Naukri Authentication
Bypasses Akamai WAF using your local Google Chrome installation:
```bash
python naukri_auth.py
```
*A Chrome window opens. Once you are logged into Naukri, press Enter in the terminal to save your session.*

### 2. Daily Profile Refresher
Touches your Resume Headline daily to keep your profile timestamp at **"Profile last updated - Today"**, boosting recruiter search ranking by 5-10x:
```bash
python naukri_refresh.py
```

### 3. 1-Click Auto-Apply Bot
Automatically searches 8+ Yrs Senior Java / Spring Boot jobs in Pune/Remote, applies, and answers questionnaire drawers (Notice period: 1 month, Experience: 8 years, CTC: 18.4 LPA / 30 LPA):
```bash
python naukri_apply.py --limit 10
```
- Tracks all applied jobs in [naukri_applied_jobs.csv](file:///Users/shubhamfarera/repos/job-hunter/naukri_applied_jobs.csv) to avoid duplicate applies.
- Saves company site applications to [naukri_external_jobs.csv](file:///Users/shubhamfarera/repos/job-hunter/naukri_external_jobs.csv).