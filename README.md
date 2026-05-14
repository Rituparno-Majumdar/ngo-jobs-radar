# 🌱 NGO Job Tracker — Rituparno's Automated Career Pipeline

A fully automated NGO/social sector job alert system built on **GitHub Actions + Telegram**, 
designed specifically for Rituparno's expertise: social work, CSR, community development, 
AI for social impact, and project coordination.

## 🎯 What It Tracks

Based on profile expertise:
- **NGO / Development Sector**: Project Coordinator, Program Officer, Field Coordinator roles
- **CSR**: Corporate Social Responsibility programme management
- **Community Development**: Livelihood, rural development, tribal welfare, capacity building
- **Social Work**: MSW-level roles in India (especially Jharkhand & East India)
- **AI for Social Impact**: Prompt engineering, AI literacy, tech for good
- **M&E**: Monitoring & Evaluation positions
- **International Organisations**: UNDP, UNICEF, Oxfam, CARE India aligned roles

## 📡 Job Sources (6 Platforms)

| Platform | Type | Focus |
|---|---|---|
| **DevNetJobs** | RSS | International development sector |
| **ReliefWeb (UN OCHA)** | REST API | Humanitarian / UN org jobs |
| **Idealist** | Web scrape | Nonprofit / social enterprise |
| **LinkedIn** | Web scrape | India-focused NGO & CSR roles |
| **NGOJobsIndia** | RSS | India-specific NGO board |
| **Remotive** | REST API | Remote social impact / AI roles |

## 🏗️ Architecture

```
ngo/
├── main.py               # Orchestrator — deduplication, logging, summary
├── scraper.py            # 6 job scrapers with profile-matched keyword filters
├── notifier.py           # Telegram bot with rich HTML formatting
├── test_notification.py  # Test credentials before deploying
├── seen_jobs.json        # Persisted job IDs (auto-committed by GitHub Actions)
├── requirements.txt
├── .env                  # Local credentials (NOT committed)
└── .github/
    └── workflows/
        └── ngo_tracker.yml   # Runs every 6 hours
```

## 🚀 Setup

### 1. Clone and install locally

```bash
cd /Users/pari/Documents/ANTIGRAVITY/jobsearch/ngo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Telegram credentials

Edit `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

> 💡 Reuse the **same bot token and chat ID** from your data annotation tracker — 
> they're already set up! You'll receive both alert streams in the same chat, 
> distinguished by emoji (🇺🇳 ReliefWeb, 🇮🇳 NGOJobsIndia, 🔗 LinkedIn, etc.)

### 3. Test locally

```bash
python test_notification.py   # Sends a sample alert to your Telegram
python main.py                # Full dry run
```

### 4. Push to GitHub

```bash
git init
git add .
git commit -m "Initial NGO job tracker setup"
git remote add origin https://github.com/YOUR_USERNAME/ngo-job-tracker.git
git push -u origin main
```

### 5. Add GitHub Secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**:

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |

## ⏰ Schedule

Runs automatically **every 6 hours** (00:23, 06:23, 12:23, 18:23 UTC = 05:53, 11:53, 17:53, 23:53 IST).

Staggered 6 minutes after the data annotation tracker to avoid simultaneous GitHub Actions runs.

## 📬 What a Telegram Alert Looks Like

```
🇺🇳 New NGO Job Alert — ReliefWeb

📋 Title: Project Coordinator – WASH Programme
🏢 Organisation: UNICEF India
📍 Location: Jharkhand, India

Seeking a coordinator with 3+ years experience in rural 
community development and M&E frameworks...

🔍 View & Apply
```

## 🔧 Customisation

Edit `scraper.py` → `CORE_TERMS` list to broaden or narrow the job matching.  
Edit `scraper.py` → `EXCLUDE_TERMS` to filter out unwanted listings.
