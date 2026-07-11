import requests
from bs4 import BeautifulSoup
import re
import os
import logging
import time
import random
import hashlib
import json
from urllib.parse import quote_plus, urljoin
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


# ─── Helper Functions for LLM Extraction ──────────────────────────────────────

def extract_clean_text(html_content, base_url=None):
    """Cleans up raw HTML into formatted text, preserving links as markdown [text](url)."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        # Remove elements that contain navigation, scripts, styling, or boilerplate
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.extract()
        
        # Convert links to [text](url) format to allow Gemini to extract listing URLs
        for a in soup.find_all('a', href=True):
            href = a['href']
            if base_url:
                href = urljoin(base_url, href)
            text = a.get_text().strip()
            if text:
                a.replace_with(f" [{text}]({href}) ")
            else:
                a.replace_with(f" ({href}) ")
                
        text = soup.get_text(separator=' ')
        # Collapse whitespace and empty lines
        lines = [line.strip() for line in text.splitlines()]
        clean_lines = [line for line in lines if line]
        return '\n'.join(clean_lines)
    except Exception as e:
        logger.warning(f"Error cleaning HTML: {e}")
        return html_content[:50000]


def gemini_extract_items(text, schema_type, source_name, base_url=None):
    """Calls the Gemini API using requests to perform structured item extraction."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment. Fallback failed.")
        return []

    model = "gemini-2.5-flash"
    
    if schema_type == 'grant':
        prompt = (
            f"You are a web scraping assistant extracting institutional grant opportunities (CSR, Govt, FCRA, RFPs, funding calls) from the text of a webpage from '{source_name}'.\n"
            f"Analyze the text below and extract all open grant opportunities/funding calls. Ignore job vacancies or standard construction/civil tenders.\n\n"
            f"Extract the following fields for each grant opportunity and return them as a JSON list of objects:\n"
            f"- 'title': The title of the grant or RFP opportunity.\n"
            f"- 'company': The donor organization or foundation name (if not found, use 'See grant listing' or a reasonable guess from context).\n"
            f"- 'url': The URL link to the grant detail page (use links found in the text associated with the grant; resolve against '{base_url}' if relative).\n"
            f"- 'description': A brief summary of eligibility, guidelines, or scope (approx 100-200 characters).\n"
            f"- 'location': The target location or region (e.g. 'India', 'Global').\n\n"
            f"Only return a valid JSON list. Do not include markdown code block formatting like ```json ... ```. Just return the raw JSON string starting with [ and ending with ]."
        )
    else:
        prompt = (
            f"You are a web scraping assistant extracting NGO / development sector / social impact job openings from the text of a webpage from '{source_name}'.\n"
            f"Analyze the text below and extract all open job vacancies. Filter for relevant roles such as project coordinators, program officers, CSR managers, social work, monitoring & evaluation.\n\n"
            f"Extract the following fields for each job opening and return them as a JSON list of objects:\n"
            f"- 'title': The job title.\n"
            f"- 'company': The organization or company hiring (if not found, use 'Unknown' or a reasonable guess from context).\n"
            f"- 'location': The job location.\n"
            f"- 'url': The URL link to apply or view the job detail page (use links found in the text associated with the job; resolve against '{base_url}' if relative).\n"
            f"- 'description': A brief summary of the role (approx 100-200 characters).\n"
            f"- 'date_posted': The date posted if visible (otherwise empty string).\n\n"
            f"Only return a valid JSON list. Do not include markdown code block formatting like ```json ... ```. Just return the raw JSON string starting with [ and ending with ]."
        )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{prompt}\n\nWebpage Text:\n\"\"\"\n{text}\n\"\"\""}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        res_data = response.json()
        content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Strip markdown format blocks if present
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        items = json.loads(content)
        if not isinstance(items, list):
            logger.error("Gemini returned JSON that is not a list.")
            return []
        return items
    except Exception as e:
        logger.error(f"Failed calling Gemini API or parsing response: {e}")
        return []


def generate_stable_id(prefix, item):
    """Generates a stable unique ID for an extracted item based on URL or Title."""
    url = item.get("url", "")
    title = item.get("title", "")
    if url and url != "#":
        unique_str = url.split("?")[0].rstrip("/")
    else:
        unique_str = title
    val_hash = hashlib.md5(unique_str.encode()).hexdigest()[:12]
    return f"{prefix}_{val_hash}"


# ─── Base Scraper Class ───────────────────────────────────────────────────────

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

    def llm_fallback(self, response, schema_type, source_name, prefix, base_url=None):
        """Standard fallback pipeline when HTML parsing yields 0 results or fails."""
        logger.info(f"[{source_name}] HTML parsing yielded 0 results or failed. Attempting LLM extraction fallback...")
        try:
            clean_text = extract_clean_text(response.text, base_url=base_url or response.url)
            items = gemini_extract_items(clean_text, schema_type, source_name, base_url=base_url or response.url)
            
            processed_items = []
            for item in items:
                item_id = item.get("id")
                if not item_id:
                    item_id = generate_stable_id(prefix, item)
                
                item["source"] = source_name
                title = item.get("title", "")
                desc = item.get("description", "")
                loc = item.get("location", "")
                
                if self.matches_profile(title, desc, loc):
                    processed_items.append({
                        "id": item_id,
                        "title": title,
                        "company": item.get("company", "See listing"),
                        "location": loc or "India",
                        "url": item.get("url", ""),
                        "source": source_name,
                        "description": desc or "View listing for details.",
                        "date_posted": item.get("date_posted", ""),
                    })
            
            logger.info(f"[{source_name}] LLM fallback successfully extracted {len(processed_items)} items.")
            return processed_items
        except Exception as fallback_err:
            logger.error(f"[{source_name}] LLM fallback failed: {fallback_err}")
            return []


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
            query_jobs = []
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            url = f"https://www.linkedin.com/jobs/search?keywords={encoded_kw}&location={encoded_loc}&f_TPR=r604800"
            response = None
            try:
                response = self.session.get(url, timeout=15)
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
                        query_jobs.append({
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

            # Fallback if scraping yielded no results but page loaded successfully
            if not query_jobs and response is not None and response.status_code == 200:
                query_jobs = self.llm_fallback(response, 'job', 'LinkedIn', 'linkedin')

            jobs.extend(query_jobs)

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

        try:
            self.session.get("https://in.indeed.com/", timeout=10)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            logger.warning(f"[Indeed] Pre-flight failed: {e}")

        for keywords, location in self.SEARCH_QUERIES:
            query_jobs = []
            encoded_kw = quote_plus(keywords)
            encoded_loc = quote_plus(location)
            url = f"https://in.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}&fromage=7"
            response = None
            try:
                self.session.headers.update({'Referer': 'https://in.indeed.com/'})
                response = self.session.get(url, timeout=15)
                time.sleep(random.uniform(3, 6))
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

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
                    
                    jk_match = re.search(r'jk=([a-fA-F0-9]+)', job_url)
                    job_id = jk_match.group(1) if jk_match else job_url.split('/')[-1]

                    if job_id in seen_ids:
                        continue

                    if self.matches_profile(title, "", location_text):
                        seen_ids.add(job_id)
                        query_jobs.append({
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

            # Fallback if scraping yielded no results but page loaded successfully
            if not query_jobs and response is not None and response.status_code == 200:
                query_jobs = self.llm_fallback(response, 'job', 'Indeed', 'indeed', base_url="https://in.indeed.com")

            jobs.extend(query_jobs)

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
                for item in root.findall(".//item"):
                    link_el = item.find("link")
                    title_el = item.find("title")
                    desc_el = item.find("description")
                    pub_el = item.find("pubDate")
                    if title_el is None or link_el is None:
                        continue
                    job_url = link_el.text.strip() if link_el.text else ""
                    job_id = f"reliefweb_{hashlib.md5(job_url.encode()).hexdigest()[:12]}"
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    
                    raw_desc = (desc_el.text or "") if desc_el is not None else ""
                    soup_desc = BeautifulSoup(raw_desc, "html.parser")
                    org = ""
                    country = ""
                    for tag in soup_desc.find_all("div", class_="tag"):
                        text = tag.get_text(strip=True)
                        if text.startswith("Organization:"):
                            org = text.replace("Organization:", "").strip()
                        elif text.startswith("Country:"):
                            country = text.replace("Country:", "").strip()
                    if not self.matches_profile(title_el.text.strip(), raw_desc, country):
                        continue
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
        response = None
        try:
            headers = dict(self.session.headers)
            headers["Referer"] = "https://www.devnetjobs.org/"
            response = self.session.get(self.SEARCH_URL, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            MAX_RESULTS = 30
            for row in soup.select("table.jobslist tr")[1:MAX_RESULTS + 1]:
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
                job_id = f"devnet_{hashlib.md5(url.encode()).hexdigest()[:12]}"
                if not self.matches_profile(title, "", location):
                    continue
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

        # Fallback if scraping yielded no results but page loaded successfully
        if not jobs and response is not None and response.status_code == 200:
            jobs = self.llm_fallback(response, 'job', 'DevNetJobs', 'devnet', base_url="https://www.devnetjobs.org")

        logger.info(f"[DevNetJobs] Found {len(jobs)} jobs.")
        return jobs


# ─── Scraper 5: Idealist Scraper ─────────────────────────────────────────────

class IdealistScraper(BaseScraper):
    """Idealist.org scraper — currently disabled."""

    def fetch_jobs(self) -> list:
        logger.info("[Idealist] Skipped — React SPA with no public RSS feed; requires browser automation.")
        return []


# ─── Scraper 6: NGOJobsIndia Scraper ─────────────────────────────────────────

class NGOJobsIndiaScraper(BaseScraper):
    """Scrapes jobs from NGOJobsIndia.com — India-focused NGO roles."""

    BASE_URL = "https://www.ngojobsindia.com/jobs/"

    def fetch_jobs(self) -> list:
        jobs = []
        response = None
        try:
            response = self.session.get(self.BASE_URL, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for card in soup.select(".job-listing, article.job_listing")[:20]:
                title_el = card.select_one("h3 a, .job-title a, h2 a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                job_id = f"ngoindia_{hashlib.md5(href.encode()).hexdigest()[:12]}"
                org_el = card.select_one(".company, .company-name, .job-company")
                loc_el = card.select_one(".location, .job-location")
                location_text = loc_el.get_text(strip=True) if loc_el else "India"
                if not self.matches_profile(title, "", location_text):
                    continue
                jobs.append({
                    "id": job_id,
                    "title": title,
                    "company": org_el.get_text(strip=True) if org_el else "",
                    "location": location_text,
                    "url": href,
                    "source": "NGOJobsIndia",
                    "description": "",
                    "date_posted": "",
                })
        except Exception as e:
            logger.warning(f"[NGOJobsIndia] Scrape failed: {e}")

        # Fallback if scraping yielded no results but page loaded successfully
        if not jobs and response is not None and response.status_code == 200:
            jobs = self.llm_fallback(response, 'job', 'NGOJobsIndia', 'ngoindia')

        logger.info(f"[NGOJobsIndia] Found {len(jobs)} jobs.")
        return jobs


def get_all_scrapers():
    return [
        ReliefWebScraper(),
        DevNetJobsScraper(),
        IdealistScraper(),
        NGOJobsIndiaScraper(),
        LinkedInNGOScraper(),
        IndeedNGOScraper(),
    ]
