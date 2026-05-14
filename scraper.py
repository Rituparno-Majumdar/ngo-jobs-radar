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


# ─── Scraper 1: LinkedIn Public Scraper ──────────────────────────────────────
class LinkedInNGOScraper(BaseScraper):
    SEARCH_QUERIES = [
        ("project coordinator ngo", "India"),
        ("social work", "Jharkhand India"),
        ("csr manager", "India"),
        ("community development", "India"),
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for keywords, location in self.SEARCH_QUERIES:
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            # f_TPR=r604800 filters for past 7 days
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


# ─── Scraper 2: Indeed Public Scraper ────────────────────────────────────────
class IndeedNGOScraper(BaseScraper):
    SEARCH_QUERIES = [
        ("ngo project coordinator", "India"),
        ("social work", "Jharkhand"),
        ("csr manager", "India"),
    ]

    def fetch_jobs(self):
        jobs = []
        seen_ids = set()

        for keywords, location in self.SEARCH_QUERIES:
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            url = f"https://in.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}&fromage=7"
            try:
                # Indeed requires clean headers to bypass bot blocks
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                # Indeed job cards usually have class td-heading or job_seen_beacon
                cards = soup.find_all('td', class_='resultContent') or soup.find_all('div', class_='job_seen_beacon')
                for card in cards:
                    title_el = card.find('h2', class_='jobTitle') or card.find('span', title=True)
                    company_el = card.find('span', class_='companyName') or card.find('span', attrs={'data-testid': 'company-name'})
                    loc_el = card.find('div', class_='companyLocation') or card.find('div', attrs={'data-testid': 'text-location'})
                    link_el = card.find('a', href=True)

                    if not title_el or not link_el:
                        continue

                    title = title_el.text.strip()
                    company = company_el.text.strip() if company_el else "Unknown"
                    location_text = loc_el.text.strip() if loc_el else "India"
                    href = link_el['href']
                    job_url = f"https://in.indeed.com{href}" if href.startswith('/') else href
                    
                    # Extract unique job key (jk)
                    jk_match = re.search(r'jk=([a-f0-9]+)', job_url)
                    job_id = jk_match.group(1) if jk_match else job_url.split('/')[-1]

                    if job_id in seen_ids:
                        continue

                    if self.matches_profile(title, "", location_text):
                        seen_ids.add(job_id)
                        jobs.append({
                            "id": f"indeed_{job_id}",
                            "title": title,
                            "company": company,
                            "url": job_url,
                            "source": "Indeed",
                            "description": "View Indeed listing for full details.",
                            "location": location_text
                        })
            except Exception as e:
                logger.error(f"[Indeed] Error for '{keywords}': {e}")

        logger.info(f"[Indeed] Found {len(jobs)} matching jobs.")
        return jobs


def get_all_scrapers():
    return [
        LinkedInNGOScraper(),
        IndeedNGOScraper(),
    ]


