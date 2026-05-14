import requests
from bs4 import BeautifulSoup
import re
import os
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# --- Keyword Configuration based on Rituparno's Profile ---
CORE_TERMS = [
    "ngo", "social work", "community development", "csr", "nonprofit",
    "non-profit", "social impact", "livelihood", "rural development",
    "program officer", "project coordinator", "project manager",
    "development sector", "social enterprise", "capacity building",
    "monitoring evaluation", "m&e", "social sector", "social welfare",
    "ai for good", "ai for social", "prompt engineer", "linguist"
]

EXCLUDE_TERMS = [
    "react developer", "backend engineer", "devops", "machine learning engineer",
    "data engineer", "cybersecurity", "cloud architect", "game developer",
    "senior software engineer", "full stack", "oracle", "ebs", "erp", "sap",
    "it project manager", "software project manager"
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
        combined = f"{title} {description} {location}".lower()
        has_core = any(term in combined for term in CORE_TERMS)
        is_excluded = any(ex in combined for ex in EXCLUDE_TERMS)
        return has_core and not is_excluded


# ─── Scraper 1: ReliefWeb API v2 (Official UN/Humanitarian Jobs) ─────────────
class ReliefWebScraper(BaseScraper):
    API_URL = "https://api.reliefweb.int/v2/jobs"

    SEARCH_QUERIES = [
        "project coordinator India",
        "community development India",
        "social work India",
        "monitoring evaluation India",
        "social impact",
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for query in self.SEARCH_QUERIES:
            try:
                # ReliefWeb v2 query structure
                payload = {
                    "appname": "ngo-job-tracker",
                    "query": {"value": query, "operator": "AND"},
                    "fields": {
                        "include": ["title", "body", "url", "source", "date", "country"]
                    },
                    "limit": 15,
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
                    )[:500] if body else ""

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
                logger.error(f"[ReliefWeb v2] Error for query '{query}': {e}")

        logger.info(f"[ReliefWeb v2] Found {len(jobs)} matching jobs.")
        return jobs


# ─── Scraper 2: WeWorkRemotely RSS (Remote AI/Linguist/Data) ─────────────────
class WeWorkRemotelyScraper(BaseScraper):
    FEED_URL = "https://weworkremotely.com/categories/remote-data-programming-jobs.rss"

    def fetch_jobs(self):
        jobs = []
        try:
            response = self.session.get(self.FEED_URL, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all(['item', 'entry'])

            for item in items:
                title = item.title.text.strip() if item.title else ""
                description = item.description.text if item.description else ""
                
                url = ""
                link_tag = item.find('link')
                if link_tag:
                    url = link_tag.text.strip() if link_tag.text else link_tag.get('href', '')

                job_id = item.guid.text.strip() if item.guid else url
                clean_desc = BeautifulSoup(description, "html.parser").get_text(separator=' ', strip=True)[:500]

                if self.matches_profile(title, clean_desc):
                    jobs.append({
                        "id": f"wwr_{job_id}",
                        "title": title,
                        "company": "See listing",
                        "url": url,
                        "source": "WeWorkRemotely",
                        "description": clean_desc,
                        "location": "Remote"
                    })
            logger.info(f"[WeWorkRemotely] Found {len(jobs)} matching jobs.")
        except Exception as e:
            logger.error(f"[WeWorkRemotely] Error: {e}")
        return jobs


# ─── Scraper 3: Remotive API (Remote Social Impact & AI) ─────────────────────
class RemotiveSocialScraper(BaseScraper):
    API_URL = "https://remotive.com/api/remote-jobs"
    SEARCH_TERMS = ["social impact", "nonprofit", "ngo", "prompt engineer", "linguist"]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for term in self.SEARCH_TERMS:
            try:
                response = self.session.get(self.API_URL, params={"search": term}, timeout=15)
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
                    )[:500] if description else ""

                    if self.matches_profile(title, clean_desc):
                        seen_ids.add(job_id)
                        jobs.append({
                            "id": f"remotive_{job_id}",
                            "title": title,
                            "company": job.get("company_name", "Unknown"),
                            "url": job.get("url", ""),
                            "source": "Remotive",
                            "description": clean_desc,
                            "location": job.get("candidate_required_location", "Remote")
                        })
            except Exception as e:
                logger.error(f"[Remotive] Error for '{term}': {e}")

        logger.info(f"[Remotive] Found {len(jobs)} matching jobs.")
        return jobs


# ─── Scraper 4: LinkedIn Public Scraper ──────────────────────────────────────
class LinkedInNGOScraper(BaseScraper):
    SEARCH_QUERIES = [
        ("project coordinator ngo", "India"),
        ("social work", "Jharkhand India"),
        ("csr manager", "India"),
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for keywords, location in self.SEARCH_QUERIES:
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            url = f"https://www.linkedin.com/jobs/search?keywords={encoded_kw}&location={encoded_loc}&f_TPR=r604800"
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

                    if not title_el or not link_el:
                        continue

                    title = title_el.text.strip()
                    company = company_el.text.strip() if company_el else "Unknown"
                    job_url = link_el['href'].split('?')[0]
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
                            "description": "View LinkedIn listing for full details.",
                            "location": location_text
                        })
            except Exception as e:
                logger.error(f"[LinkedIn] Error for '{keywords}': {e}")

        logger.info(f"[LinkedIn] Found {len(jobs)} matching jobs.")
        return jobs


def get_all_scrapers():
    return [
        ReliefWebScraper(),
        WeWorkRemotelyScraper(),
        RemotiveSocialScraper(),
        LinkedInNGOScraper(),
    ]
