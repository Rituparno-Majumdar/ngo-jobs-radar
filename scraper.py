import requests
from bs4 import BeautifulSoup
import re
import os
import logging
import time
import random
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
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
                # Random delay between queries to avoid bot detection
                time.sleep(random.uniform(2, 4))
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
                            "location": location_text,
                            "date_posted": ""
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

        # Pre-flight: visit home page to get session cookies
        try:
            self.session.get("https://in.indeed.com/", timeout=10)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            logger.warning(f"[Indeed] Pre-flight failed: {e}")

        for keywords, location in self.SEARCH_QUERIES:
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            url = f"https://in.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}&fromage=7"
            try:
                # Set Referer to make it look like a search from the home page
                self.session.headers.update({'Referer': 'https://in.indeed.com/'})
                
                # Indeed requires clean headers to bypass bot blocks
                response = self.session.get(url, timeout=15)
                # Indeed is very sensitive; longer random delay
                time.sleep(random.uniform(3, 6))
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
                    jk_match = re.search(r'jk=([a-fA-F0-9]+)', job_url)
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
                            "location": location_text,
                            "date_posted": ""
                        })
            except Exception as e:
                logger.error(f"[Indeed] Error for '{keywords}': {e}")

        logger.info(f"[Indeed] Found {len(jobs)} matching jobs.")
        return jobs


# ─── Scraper 3: ReliefWeb RSS Scraper ────────────────────────────────────────
class ReliefWebScraper(BaseScraper):
    """Scrapes NGO jobs from ReliefWeb public RSS feeds (no auth required)."""

    RSS_SEARCHES = [
        "project+coordinator",
        "programme+coordinator",
        "NGO+manager",
        "social+impact",
        "CSR",
    ]
    BASE_RSS = "https://reliefweb.int/jobs/rss.xml"

    def fetch_jobs(self) -> list:
        jobs = []
        seen_ids = set()
        for search in self.RSS_SEARCHES:
            try:
                url = f"{self.BASE_RSS}?search={search}&category=0&country=0&type=0&source=0"
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                ns = {"media": "http://search.yahoo.com/mrss/"}
                for item in root.findall(".//item"):
                    link_el = item.find("link")
                    title_el = item.find("title")
                    desc_el = item.find("description")
                    pub_el = item.find("pubDate")
                    if title_el is None or link_el is None:
                        continue
                    job_url = link_el.text.strip() if link_el.text else ""
                    job_id = f"reliefweb_{abs(hash(job_url))}"
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    # Extract org and country from description HTML
                    raw_desc = desc_el.text or "" if desc_el is not None else ""
                    soup_desc = BeautifulSoup(raw_desc, "html.parser")
                    org = ""
                    country = ""
                    for tag in soup_desc.find_all("div", class_="tag"):
                        text = tag.get_text(strip=True)
                        if text.startswith("Organization:"):
                            org = text.replace("Organization:", "").strip()
                        elif text.startswith("Country:"):
                            country = text.replace("Country:", "").strip()
                    jobs.append({
                        "id": job_id,
                        "title": title_el.text.strip(),
                        "company": org,
                        "location": country if country else "International",
                        "url": job_url,
                        "source": "ReliefWeb",
                        "description": "",
                        "date_posted": pub_el.text.strip() if pub_el is not None and pub_el.text else "",
                    })
            except Exception as e:
                logger.warning(f"[ReliefWeb] RSS search '{search}' failed: {e}")
        logger.info(f"[ReliefWeb] Found {len(jobs)} jobs.")
        return jobs


# ─── Scraper 4: DevNetJobs Scraper ───────────────────────────────────────────
class DevNetJobsScraper(BaseScraper):
    """Scrapes NGO jobs from DevNetJobs.org."""

    SEARCH_URL = "https://www.devnetjobs.org/jobs/all-categories/all-types"

    def fetch_jobs(self) -> list:
        jobs = []
        try:
            headers = dict(self.session.headers)
            headers["Referer"] = "https://www.devnetjobs.org/"
            resp = self.session.get(self.SEARCH_URL, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table.jobslist tr")[1:31]:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                title_el = cols[0].find("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                url = f"https://www.devnetjobs.org{href}" if href.startswith("/") else href
                org = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                location = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                job_id = f"devnet_{abs(hash(url))}"
                jobs.append({
                    "id": job_id,
                    "title": title,
                    "company": org,
                    "location": location,
                    "url": url,
                    "source": "DevNetJobs",
                    "description": "",
                    "date_posted": "",
                })
        except Exception as e:
            logger.warning(f"[DevNetJobs] Scrape failed: {e}")
        logger.info(f"[DevNetJobs] Found {len(jobs)} jobs.")
        return jobs


# ─── Scraper 5: Idealist Scraper ─────────────────────────────────────────────
class IdealistScraper(BaseScraper):
    """Scrapes NGO/social-impact jobs from Idealist.org."""

    SEARCH_URLS = [
        "https://www.idealist.org/en/jobs?q=NGO+coordinator&radius=Anywhere",
        "https://www.idealist.org/en/jobs?q=CSR+sustainability&radius=Anywhere",
    ]

    def fetch_jobs(self) -> list:
        jobs = []
        seen_ids = set()
        for url in self.SEARCH_URLS:
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select("div[data-test='job-card']")[:15]:
                    title_el = card.select_one("h2, h3, [data-test='job-title']")
                    link_el = card.select_one("a[href]")
                    org_el = card.select_one("[data-test='org-name'], .org-name")
                    loc_el = card.select_one("[data-test='location'], .location")
                    if not title_el or not link_el:
                        continue
                    title = title_el.get_text(strip=True)
                    href = link_el.get("href", "")
                    job_url = f"https://www.idealist.org{href}" if href.startswith("/") else href
                    job_id = f"idealist_{abs(hash(job_url))}"
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    jobs.append({
                        "id": job_id,
                        "title": title,
                        "company": org_el.get_text(strip=True) if org_el else "",
                        "location": loc_el.get_text(strip=True) if loc_el else "",
                        "url": job_url,
                        "source": "Idealist",
                        "description": "",
                        "date_posted": "",
                    })
            except Exception as e:
                logger.warning(f"[Idealist] Scrape failed for {url}: {e}")
        logger.info(f"[Idealist] Found {len(jobs)} jobs.")
        return jobs


# ─── Scraper 6: NGOJobsIndia Scraper ─────────────────────────────────────────
class NGOJobsIndiaScraper(BaseScraper):
    """Scrapes jobs from NGOJobsIndia.com — India-focused NGO roles."""

    BASE_URL = "https://www.ngojobsindia.com/jobs/"

    def fetch_jobs(self) -> list:
        jobs = []
        try:
            resp = self.session.get(self.BASE_URL, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".job-listing, article.job_listing")[:20]:
                title_el = card.select_one("h3 a, .job-title a, h2 a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                job_id = f"ngoindia_{abs(hash(href))}"
                org_el = card.select_one(".company, .company-name, .job-company")
                loc_el = card.select_one(".location, .job-location")
                jobs.append({
                    "id": job_id,
                    "title": title,
                    "company": org_el.get_text(strip=True) if org_el else "",
                    "location": loc_el.get_text(strip=True) if loc_el else "India",
                    "url": href,
                    "source": "NGOJobsIndia",
                    "description": "",
                    "date_posted": "",
                })
        except Exception as e:
            logger.warning(f"[NGOJobsIndia] Scrape failed: {e}")
        logger.info(f"[NGOJobsIndia] Found {len(jobs)} jobs.")
        return jobs


def get_all_scrapers():
    return [
        ReliefWebScraper(),       # API-based, most reliable
        DevNetJobsScraper(),      # NGO-focused board
        IdealistScraper(),        # Social impact roles
        NGOJobsIndiaScraper(),    # India-specific
        LinkedInNGOScraper(),     # May be blocked
        IndeedNGOScraper(),       # May be blocked
    ]


