import html
import os
import re
import time
import requests
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def url_safe(url: str) -> str:
    """Escape & → &amp; so Telegram HTML parse mode renders the link correctly."""
    return url.replace('&', '&amp;') if url else '#'


def is_valid_url(url: str) -> bool:
    """Return True if url looks like an absolute HTTP/HTTPS link."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False

# Source emojis for visual scanning in Telegram
SOURCE_EMOJI = {
    "DevNetJobs":    "🌐",
    "ReliefWeb":     "🇺🇳",
    "Idealist":      "💡",
    "LinkedIn":      "🔗",
    "NGOJobsIndia":  "🇮🇳",
    "Remotive":      "💻",
    "Indeed":        "🔍",
    "DevelopmentWala": "🪔",
}


class TelegramNotifier:
    def __init__(self, bot_token=None, chat_id=None):
        # Use dedicated NGO bot secrets; fall back to shared token if not set
        self.bot_token = (
            bot_token
            or os.environ.get("NGO_TELEGRAM_BOT_TOKEN")
            or os.environ.get("TELEGRAM_BOT_TOKEN")
        )
        self.chat_id = (
            chat_id
            or os.environ.get("NGO_TELEGRAM_CHAT_ID")
            or os.environ.get("TELEGRAM_CHAT_ID")
        )

        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not fully set. Notifications disabled.")

        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_job_alert(self, job):
        """Send a richly formatted job alert to Telegram."""
        if not self.bot_token or not self.chat_id:
            logger.error("Cannot send alert: Telegram credentials missing.")
            return False

        source = job.get('source', 'Web')
        emoji = SOURCE_EMOJI.get(source, "📢")
        location = job.get('location', 'Not specified')

        # Truncate description for clean Telegram formatting
        desc = job.get('description', '')
        if desc and len(desc) > 300:
            desc = desc[:300].rsplit(' ', 1)[0] + "..."

        desc_block = f"\n<i>{html.escape(desc)}</i>" if desc and desc.lower() != "see listing" \
                     and "linkedin" not in desc.lower() \
                     and "idealist" not in desc.lower() else ""

        # Validate and escape the URL for Telegram HTML mode
        raw_url = job.get('url', '')
        if is_valid_url(raw_url):
            apply_button = f'<a href="{url_safe(raw_url)}">🔍 View &amp; Apply</a>'
        else:
            apply_button = "⚠️ Link unavailable — search the title on the source site."
            logger.warning(f"Invalid URL for job '{job.get('title')}': '{raw_url}'")

        message = (
            f"{emoji} <b>New NGO Job Alert — {html.escape(source)}</b>\n\n"
            f"📋 <b>Title:</b> {html.escape(job.get('title', 'N/A'))}\n"
            f"🏢 <b>Organisation:</b> {html.escape(job.get('company', 'See listing'))}\n"
            f"📍 <b>Location:</b> {html.escape(location)}\n"
            f"{desc_block}\n\n"
            f"{apply_button}"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/sendMessage", json=payload, timeout=15
                )
                response.raise_for_status()
                logger.info(f"✅ Alert sent: {job.get('title')}")
                return True
            except requests.exceptions.RequestException as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"❌ Failed to send Telegram message after 3 attempts: {e}")
        return False

    def send_summary(self, total_new, total_checked, scraper_stats=None):
        """Send a daily summary message (optional heartbeat)."""
        if not self.bot_token or not self.chat_id:
            return False

        stats_lines = ""
        if scraper_stats:
            lines = []
            for name, s in scraper_stats.items():
                if s.get("failed"):
                    lines.append(f"  ❌ {name}: FAILED")
                elif s["found"] == 0:
                    lines.append(f"  ⚠️ {name}: 0 results (may be blocked)")
                else:
                    lines.append(f"  ✅ {name}: {s['found']} checked, {s['new']} new")
            stats_lines = "\n" + "\n".join(lines) + "\n"

        if total_new == 0:
            message = (
                "🤖 <b>NGO Job Tracker — Scan Complete</b>\n\n"
                f"✅ Checked {total_checked} jobs across all platforms.\n"
                f"📭 No new listings found this cycle.{stats_lines}"
            )
        else:
            message = (
                "🤖 <b>NGO Job Tracker — Scan Complete</b>\n\n"
                f"🆕 <b>{total_new} new job(s)</b> sent above!\n"
                f"✅ Checked {total_checked} total listings.{stats_lines}"
            )

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(
                f"{self.base_url}/sendMessage", json=payload, timeout=15
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send summary: {e}")
            return False
