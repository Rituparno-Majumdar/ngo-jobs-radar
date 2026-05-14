import requests
from bs4 import BeautifulSoup
import re
import os
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# --- Keyword Configuration based on Rituparno's Profile ---

PROFILE_KEYWORDS = [
    "ngo", "project manager", "project coordinator", "social work",
    "community development", "csr", "corporate social responsibility",
    "social impact", "nonprofit", "non-profit", "non profit",
    "msw", "development sector", "livelihood", "rural development",
    "tribal", "social welfare", "capacity building", "field coordinator",
    "program officer", "program manager", "impact assessment",
    "monitoring evaluation", "m&e", "social enterprise", "undp",
    "unicef", "oxfam", "care india", "ngo project", "social sector",
    "civil society", "community mobilization", "generative ai",
    "ai for good", "ai for social", "prompt engineer", "data analysis",
    "gender", "women empowerment", "education", "health", "jharkhand",
    "india", "remote"
]

# Require at least one of these core terms to match
CORE_TERMS = [
    "ngo", "social work", "community development", "csr", "nonprofit",
    "non-profit", "social impact", "livelihood", "rural development",
    "program officer", "project coordinator", "project manager",
    "development sector", "social enterprise", "capacity building",
    "monitoring evaluation", "m&e", "social sector", "social welfare",
    "ai for good", "ai for social", "prompt engineer"
]

# Exclude irrelevant tech-only listings
EXCLUDE_TERMS = [
    "react developer", "backend engineer", "devops", "machine learning engineer",
    "data engineer", "cybersecurity", "cloud architect", "game developer"
]


class BaseScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
        })

    def fetch_jobs(self):
        """Must return a list of dicts: id, title, company, url, source, description, location"""
        raise NotImplementedError

    def matches_profile(self, title="", description="", location=""):
        """Check if a job matches Rituparno's profile."""
        combined = f"{title} {description} {location}".lower()

        # Must match at least one core term
        has_core = any(term in combined for term in CORE_TERMS)

        # Must not be a pure tech role
        is_excluded = any(ex in combined for ex in EXCLUDE_TERMS)

        return has_core and not is_excluded


# ─── Scraper 1: DevNetJobs RSS ──────────────────────────────────────────────
class DevNetJobsScraper(BaseScraper):
    """DevNetJobs is one of the largest NGO/development sector job boards."""

    FEED_URL = "https://www.devnetjobs.org/rss/All-International-Development-Jobs.xml"

    def fetch_jobs(self):
        jobs = []
        try:
            response = self.session.get(self.FEED_URL, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            for item in items:
                title = item.title.text.strip() if item.title else ""
                description = item.description.text.strip() if item.description else ""
                url = item.link.text.strip() if item.link else ""
                job_id = item.guid.text.strip() if item.guid else url

                clean_desc = BeautifulSoup(description, "html.parser").get_text(
                    separator=' ', strip=True
                )[:600]

                if self.matches_profile(title, clean_desc):
                    jobs.append({
                        "id": f"devnet_{job_id}",
                        "title": title,
                        "company": "See listing",
                        "url": url,
                        "source": "DevNetJobs",
                        "description": clean_desc,
                        "location": "Global/Remote"
                    })

            logger.info(f"[DevNetJobs] Found {len(jobs)} matching jobs.")
        except Exception as e:
            logger.error(f"[DevNetJobs] Error: {e}")
        return jobs


# ─── Scraper 2: ReliefWeb API ────────────────────────────────────────────────
class ReliefWebScraper(BaseScraper):
    """ReliefWeb is a UN OCHA platform for humanitarian jobs worldwide."""

    API_URL = "https://api.reliefweb.int/v1/jobs"

    SEARCH_QUERIES = [
        "project coordinator social work India",
        "community development NGO India",
        "CSR program manager Jharkhand",
        "social impact AI India",
        "monitoring evaluation NGO India",
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for query in self.SEARCH_QUERIES:
            try:
                payload = {
                    "appname": "ngo-job-tracker",
                    "query": {"value": query},
                    "fields": {
                        "include": ["title", "body", "url", "source", "date", "country"]
                    },
                    "limit": 20,
                    "sort": ["date:desc"]
                }
                response = self.session.post(self.API_URL, json=payload, timeout=15)
                response.raise_for_status()
                data = response.json()

                for item in data.get("data", []):
                    fields = item.get("fields", {})
                    job_id = str(item.get("id", ""))

                    if job_id in seen_ids:
                        continue

                    title = fields.get("title", "")
                    body = fields.get("body", "")
                    source_list = fields.get("source", [])
                    company = source_list[0].get("name", "Unknown") if source_list else "Unknown"
                    url = fields.get("url", "")
                    countries = fields.get("country", [])
                    location = ", ".join(c.get("name", "") for c in countries) if countries else "Global"

                    clean_desc = BeautifulSoup(body, "html.parser").get_text(
                        separator=' ', strip=True
                    )[:600] if body else ""

                    if self.matches_profile(title, clean_desc, location):
                        seen_ids.add(job_id)
                        jobs.append({
                            "id": f"reliefweb_{job_id}",
                            "title": title,
                            "company": company,
                            "url": url,
                            "source": "ReliefWeb",
                            "description": clean_desc,
                            "location": location
                        })

            except Exception as e:
                logger.error(f"[ReliefWeb] Error for query '{query}': {e}")

        logger.info(f"[ReliefWeb] Found {len(jobs)} matching jobs.")
        return jobs


# ─── Scraper 3: Idealist RSS ─────────────────────────────────────────────────
class IdealistScraper(BaseScraper):
    """Idealist is a top platform for nonprofit and social-impact jobs."""

    SEARCH_TERMS = [
        "project+coordinator+ngo+india",
        "social+work+community+development+india",
        "csr+program+manager",
        "ai+social+impact",
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for term in self.SEARCH_TERMS:
            url = f"https://www.idealist.org/en/jobs?q={term}&sort=date"
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                # Idealist renders JSON-LD or card elements
                cards = soup.select('article[data-testid]') or soup.select('.listing-card')

                for card in cards:
                    title_el = card.select_one('h2, h3, [class*="title"]')
                    link_el = card.select_one('a[href]')
                    org_el = card.select_one('[class*="org"], [class*="company"]')
                    loc_el = card.select_one('[class*="location"]')

                    if not title_el or not link_el:
                        continue

                    title = title_el.get_text(strip=True)
                    href = link_el.get('href', '')
                    job_url = f"https://www.idealist.org{href}" if href.startswith('/') else href
                    company = org_el.get_text(strip=True) if org_el else "See listing"
                    location = loc_el.get_text(strip=True) if loc_el else "Unknown"
                    job_id = href.split('/')[-1] or job_url

                    if job_id in seen_ids:
                        continue

                    if self.matches_profile(title, "", location):
                        seen_ids.add(job_id)
                        jobs.append({
                            "id": f"idealist_{job_id}",
                            "title": title,
                            "company": company,
                            "url": job_url,
                            "source": "Idealist",
                            "description": "Visit Idealist for full description.",
                            "location": location
                        })

            except Exception as e:
                logger.error(f"[Idealist] Error for term '{term}': {e}")

        logger.info(f"[Idealist] Found {len(jobs)} matching jobs.")
        return jobs


# ─── Scraper 4: LinkedIn Public Jobs ─────────────────────────────────────────
class LinkedInNGOScraper(BaseScraper):
    """Scrapes LinkedIn public jobs for NGO/social sector roles."""

    SEARCH_QUERIES = [
        ("project coordinator ngo", "India"),
        ("community development csr", "Jharkhand India"),
        ("social work program manager", "India"),
        ("ai social impact nonprofit", "India"),
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for keywords, location in self.SEARCH_QUERIES:
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            url = (
                f"https://www.linkedin.com/jobs/search?"
                f"keywords={encoded_kw}&location={encoded_loc}&f_TPR=r604800"
            )
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                cards = soup.find_all('div', class_='base-card')
                for card in cards:
                    title_el = card.find('h3', class_='base-search-card__title')
                    company_el = card.find('h4', class_='base-search-card__subtitle')
                    link_el = card.find('a', class_='base-card__full-link')
                    loc_el = card.find('span', class_='job-search-card__location')

                    if not title_el:
                        continue

                    title = title_el.text.strip()
                    company = company_el.text.strip() if company_el else "Unknown"
                    job_url = link_el['href'].split('?')[0] if link_el else ""
                    location_text = loc_el.text.strip() if loc_el else "Unknown"
                    job_id = job_url.split('-')[-1] if '-' in job_url else job_url

                    if job_id in seen_ids:
                        continue

                    if self.matches_profile(title, "", location_text):
                        seen_ids.add(job_id)
                        jobs.append({
                            "id": f"linkedin_{job_id}",
                            "title": title,
                            "company": company,
                            "url": job_url,
                            "source": "LinkedIn",
                            "description": "View LinkedIn for full description.",
                            "location": location_text
                        })

            except Exception as e:
                logger.error(f"[LinkedIn] Error for '{keywords}': {e}")

        logger.info(f"[LinkedIn] Found {len(jobs)} matching jobs.")
        return jobs


# ─── Scraper 5: NGOJobsIndia RSS ─────────────────────────────────────────────
class NGOJobsIndiaScraper(BaseScraper):
    """India-specific NGO job board."""

    FEED_URL = "https://www.ngojobsindia.com/rss/jobs"

    def fetch_jobs(self):
        jobs = []
        try:
            response = self.session.get(self.FEED_URL, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')

            for item in items:
                title = item.title.text.strip() if item.title else ""
                description = item.description.text.strip() if item.description else ""
                url = item.link.text.strip() if item.link else ""
                job_id = item.guid.text.strip() if item.guid else url

                clean_desc = BeautifulSoup(description, "html.parser").get_text(
                    separator=' ', strip=True
                )[:600]

                if self.matches_profile(title, clean_desc):
                    jobs.append({
                        "id": f"ngoindia_{job_id}",
                        "title": title,
                        "company": "See listing",
                        "url": url,
                        "source": "NGOJobsIndia",
                        "description": clean_desc,
                        "location": "India"
                    })

            logger.info(f"[NGOJobsIndia] Found {len(jobs)} matching jobs.")
        except Exception as e:
            logger.error(f"[NGOJobsIndia] Error: {e}")
        return jobs


# ─── Scraper 6: Remotive (AI for Social Impact) ──────────────────────────────
class RemotiveSocialScraper(BaseScraper):
    """Searches Remotive for AI/tech roles with social impact angle."""

    API_URL = "https://remotive.com/api/remote-jobs"

    SEARCH_TERMS = ["social impact", "nonprofit", "ngo", "prompt engineer social"]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for term in self.SEARCH_TERMS:
            try:
                response = self.session.get(
                    self.API_URL, params={"search": term}, timeout=15
                )
                response.raise_for_status()
                data = response.json()

                for job in data.get("jobs", []):
                    title = job.get("title", "")
                    description = job.get("description", "")
                    job_id = str(job.get("id", ""))

                    if job_id in seen_ids:
                        continue

                    clean_desc = BeautifulSoup(description, "html.parser").get_text(
                        separator=' ', strip=True
                    )[:600] if description else ""

                    if self.matches_profile(title, clean_desc):
                        seen_ids.add(job_id)
                        jobs.append({
                            "id": f"remotive_{job_id}",
                            "title": title,
                            "company": job.get("company_name", "Unknown"),
                            "url": job.get("url", ""),
                            "source": "Remotive",
                            "description": clean_desc,
                            "location": "Remote"
                        })

            except Exception as e:
                logger.error(f"[Remotive] Error for '{term}': {e}")

        logger.info(f"[Remotive] Found {len(jobs)} matching jobs.")
        return jobs


def get_all_scrapers():
    """Return all configured scrapers for the NGO job tracker."""
    return [
        DevNetJobsScraper(),
        ReliefWebScraper(),
        IdealistScraper(),
        LinkedInNGOScraper(),
        NGOJobsIndiaScraper(),
        RemotiveSocialScraper(),
    ]
