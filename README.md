# 📡 NGO Jobs Radar

![GitHub Actions](https://github.com/Rituparno-Majumdar/ngo-jobs-radar/actions/workflows/ngo_tracker.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-22c55e)
![Runs on](https://img.shields.io/badge/runs%20on-GitHub%20Actions-2088ff?logo=github-actions&logoColor=white)
![Notifications](https://img.shields.io/badge/alerts-Telegram-26a5e4?logo=telegram&logoColor=white)

> **Stop checking job boards manually.** This pipeline wakes up twice a day, scrapes 6 development sector platforms, filters for roles that match my profile, and pushes alerts straight to Telegram — fully automated, zero maintenance.

---

## 🎯 What I Track

| Category | Examples |
|---|---|
| **NGO / Development Sector** | Project Coordinator, Program Officer, Field Coordinator |
| **CSR Management** | Corporate Social Responsibility programme roles |
| **Community Development** | Livelihood, rural development, tribal welfare, capacity building |
| **Social Work** | MSW-level roles in India — especially Jharkhand & East India |
| **AI for Social Impact** | Prompt engineering, AI literacy, tech-for-good roles |
| **M&E** | Monitoring & Evaluation positions |
| **International Orgs** | UNDP, UNICEF, Oxfam, CARE India aligned roles |

---

## 📡 Sources

| Platform | Method | Coverage |
|---|---|---|
| 🇺🇳 **ReliefWeb** | API | Public REST API — most reliable |
| 💼 **DevNetJobs** | Scrape | NGO-focused job board |
| 💡 **Idealist** | Scrape | Social impact roles |
| 🇮🇳 **NGOJobsIndia** | Scrape | India-specific NGO roles |
| 🔗 **LinkedIn** | Scrape | May be blocked (anti-bot) |
| 💻 **Indeed** | Scrape | May be blocked (anti-bot) |

---

## 🏗️ How It Works

```
GitHub Actions (cron — twice daily)
        │
        ▼
   main.py (orchestrator)
        │
        ├── scraper.py  ──►  6 job sources  ──►  keyword filter
        │
        ├── deduplication  (seen_jobs.json — auto-committed)
        │
        └── notifier.py  ──►  Telegram Bot API
```

**Files:**
```
├── main.py               # Orchestrator — deduplication, logging, summary
├── scraper.py            # 6 job scrapers with keyword profile matching
├── notifier.py           # Telegram bot — rich HTML alerts + retry logic
├── test_notification.py  # Validate credentials before deploying
├── seen_jobs.json        # Persisted job IDs (auto-committed by CI)
├── requirements.txt
├── .env                  # Local secrets (never committed)
└── .github/workflows/
    └── ngo_tracker.yml   # Scheduled workflow
```

---

## ⚙️ Setup

### 1. Clone and install

```bash
git clone https://github.com/Rituparno-Majumdar/ngo-jobs-radar.git
cd ngo-jobs-radar
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create `.env`

```env
NGO_TELEGRAM_BOT_TOKEN=your_bot_token_here
NGO_TELEGRAM_CHAT_ID=your_chat_id_here
```

Create a bot via [@BotFather](https://t.me/BotFather) on Telegram.

### 3. Test locally

```bash
python test_notification.py   # sends a sample alert
python main.py                # full run
```

### 4. Add GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `NGO_TELEGRAM_BOT_TOKEN` | Your bot token |
| `NGO_TELEGRAM_CHAT_ID` | Your chat ID |

Also enable: **Settings → Actions → General → Workflow permissions → Read and write**

---

## ⏰ Schedule

Runs at **06:15 AM and 06:15 PM IST** every day (`cron: '45 0,12 * * *'`).

---

## 📬 Sample Alert

```
🇺🇳 New NGO Job Alert — ReliefWeb

📋 Title:         Project Coordinator – WASH Programme
🏢 Organisation:  UNICEF India
📍 Location:      Jharkhand, India

Seeking a coordinator with 3+ years experience in rural
community development and M&E frameworks...

🔍 View & Apply
```

---

## 🔧 Customise

Edit `scraper.py` to adjust the matching logic:

- **`CORE_TERMS`** — keywords that qualify a listing (e.g. add `"gender"`, `"WASH"`)
- **`EXCLUDE_TERMS`** — keywords that disqualify a listing (e.g. add `"sales"`)

---

## 📄 License

[MIT](LICENSE) © Rituparno Majumdar
