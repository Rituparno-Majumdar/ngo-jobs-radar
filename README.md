# Social Sector Job Tracker

![GitHub Actions](https://github.com/Rituparno-Majumdar/ngo-jobs-radar/actions/workflows/ngo_tracker.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-GitHub%20Actions-lightgrey)

I built this to stop manually checking job boards every day. It runs automatically on GitHub Actions, scrapes 6 platforms for NGO and development sector roles in India, filters them against my profile, and sends Telegram alerts in real time — twice daily, hands-free.

## What I Track

My focus areas:
- **NGO / Development Sector**: Project Coordinator, Program Officer, Field Coordinator roles
- **CSR**: Corporate Social Responsibility programme management
- **Community Development**: Livelihood, rural development, tribal welfare, capacity building
- **Social Work**: MSW-level roles in India (especially Jharkhand & East India)
- **AI for Social Impact**: Prompt engineering, AI literacy, tech for good
- **M&E**: Monitoring & Evaluation positions
- **International Organisations**: UNDP, UNICEF, Oxfam, CARE India aligned roles

## Job Sources

| Platform | Type | Focus |
|---|---|---|
| **DevNetJobs** | RSS | International development sector |
| **ReliefWeb (UN OCHA)** | REST API | Humanitarian / UN org jobs |
| **Idealist** | Web scrape | Nonprofit / social enterprise |
| **LinkedIn** | Web scrape | India-focused NGO & CSR roles |
| **NGOJobsIndia** | RSS | India-specific NGO board |
| **Remotive** | REST API | Remote social impact / AI roles |

## Architecture

```
├── main.py               # Orchestrator — deduplication, logging, summary
├── scraper.py            # 6 job scrapers with keyword profile matching
├── notifier.py           # Telegram bot with rich HTML formatting + retry logic
├── test_notification.py  # Test credentials before deploying
├── seen_jobs.json        # Persisted job IDs (auto-committed by GitHub Actions)
├── requirements.txt
├── .env                  # Local credentials (NOT committed)
└── .github/
    └── workflows/
        └── ngo_tracker.yml   # Runs twice daily
```

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Rituparno-Majumdar/social-sector-job-tracker.git
cd social-sector-job-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Telegram credentials

Create a `.env` file:
```
NGO_TELEGRAM_BOT_TOKEN=your_bot_token_here
NGO_TELEGRAM_CHAT_ID=your_chat_id_here
```

To find your chat ID, message your bot on Telegram, then run:
```bash
python test_notification.py
```

### 3. Add GitHub Secrets

In your repo: **Settings → Secrets and variables → Actions**

| Secret | Value |
|---|---|
| `NGO_TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `NGO_TELEGRAM_CHAT_ID` | Your personal chat ID |

Also enable **Read and write permissions** under **Settings → Actions → General → Workflow permissions**.

## Schedule

Runs automatically twice daily at **06:15 AM and 06:15 PM IST** (00:45 and 12:45 UTC).

## Sample Telegram Alert

```
🇺🇳 New NGO Job Alert — ReliefWeb

📋 Title: Project Coordinator – WASH Programme
🏢 Organisation: UNICEF India
📍 Location: Jharkhand, India

Seeking a coordinator with 3+ years experience in rural
community development and M&E frameworks...

🔍 View & Apply
```

## Customisation

Edit `scraper.py` → `CORE_TERMS` to broaden or narrow job matching.
Edit `scraper.py` → `EXCLUDE_TERMS` to filter out unwanted listings.
