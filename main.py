import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from scraper import get_all_scrapers
from notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SEEN_JOBS_FILE = "seen_jobs.json"
MAX_SEEN_JOBS = 2000  # cap to avoid unbounded growth


def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        try:
            with open(SEEN_JOBS_FILE, 'r') as f:
                return set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse seen_jobs.json. Starting fresh.")
            return set()
    return set()


def save_seen_jobs(seen_jobs: set):
    # Keep only the latest MAX_SEEN_JOBS entries to avoid bloat
    jobs_list = list(seen_jobs)[-MAX_SEEN_JOBS:]
    with open(SEEN_JOBS_FILE, 'w') as f:
        json.dump(jobs_list, f, indent=2)


def main():
    logger.info("=" * 60)
    logger.info("🚀 NGO Job Tracker Starting...")
    logger.info("=" * 60)

    seen_jobs = load_seen_jobs()
    notifier = TelegramNotifier()
    scrapers = get_all_scrapers()

    new_jobs_found = 0
    total_checked = 0

    for scraper in scrapers:
        scraper_name = scraper.__class__.__name__
        logger.info(f"📡 Running scraper: {scraper_name}")

        try:
            jobs = scraper.fetch_jobs()
        except Exception as e:
            logger.error(f"Scraper {scraper_name} failed with unhandled exception: {e}")
            continue

        total_checked += len(jobs)

        for job in jobs:
            job_id = job.get('id')
            if not job_id:
                continue

            if job_id not in seen_jobs:
                logger.info(f"  🆕 New job: {job.get('title')} [{job.get('source')}]")

                success = notifier.send_job_alert(job)

                if success:
                    seen_jobs.add(job_id)
                    new_jobs_found += 1
                else:
                    logger.error(f"  ❌ Failed to notify for: {job_id}")
            else:
                logger.debug(f"  ✅ Already seen: {job_id}")

    # Save updated seen list
    save_seen_jobs(seen_jobs)

    # Send summary heartbeat
    notifier.send_summary(new_jobs_found, total_checked)

    logger.info("=" * 60)
    logger.info(f"✅ Done. Sent {new_jobs_found} new alerts from {total_checked} listings checked.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
