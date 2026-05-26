"""Tests for scraper.py — ReliefWebScraper, LinkedInNGOScraper, and BaseScraper.

Author: Rituparno Majumdar
"""
import hashlib
import requests
import pytest
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import ReliefWebScraper, LinkedInNGOScraper, BaseScraper, CORE_TERMS, EXCLUDE_TERMS


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_reliefweb_rss(items):
    """Build a minimal RSS XML document containing `items` dicts with keys:
    title, link, description, pubDate (all optional except title and link).
    """
    item_xml = ""
    for it in items:
        desc = it.get("description", "")
        pub = it.get("pubDate", "Mon, 01 Jan 2026 00:00:00 +0000")
        item_xml += f"""
        <item>
            <title>{it['title']}</title>
            <link>{it['link']}</link>
            <description><![CDATA[{desc}]]></description>
            <pubDate>{pub}</pubDate>
        </item>
        """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>ReliefWeb Jobs</title>
    {item_xml}
  </channel>
</rss>""".encode("utf-8")


# ─── BaseScraper.matches_profile ─────────────────────────────────────────────

class TestMatchesProfile:
    def setup_method(self):
        # BaseScraper.fetch_jobs raises NotImplementedError; we can still
        # instantiate it to test matches_profile.
        self.scraper = BaseScraper()

    def test_matches_core_term_in_title(self):
        assert self.scraper.matches_profile(title="NGO Project Coordinator") is True

    def test_matches_csr_in_title(self):
        assert self.scraper.matches_profile(title="CSR Manager", location="India") is True

    def test_excludes_software_role(self):
        assert self.scraper.matches_profile(
            title="Senior Software Engineer", description="React developer role"
        ) is False

    def test_no_match_returns_false(self):
        assert self.scraper.matches_profile(title="Kitchen Porter", description="Catering role") is False

    def test_excluded_term_overrides_core_term(self):
        # "ngo" is a core term, "full stack" is an exclude term
        assert self.scraper.matches_profile(title="Full Stack Developer for NGO") is False


# ─── ReliefWebScraper ─────────────────────────────────────────────────────────

class TestReliefWebScraper:
    def setup_method(self):
        self.scraper = ReliefWebScraper()

    def test_returns_matching_jobs(self, mocker):
        """Should parse RSS and return jobs that match the profile."""
        rss = make_reliefweb_rss([
            {
                "title": "Project Coordinator — Community Development",
                "link": "https://reliefweb.int/job/12345",
                "description": (
                    '<div class="tag">Organization: Save the Children</div>'
                    '<div class="tag">Country: India</div>'
                ),
            }
        ])
        mock_resp = MagicMock()
        mock_resp.content = rss
        mock_resp.raise_for_status = MagicMock()
        mocker.patch.object(self.scraper.session, "get", return_value=mock_resp)

        jobs = self.scraper.fetch_jobs()

        assert len(jobs) >= 1
        job = jobs[0]
        assert job["source"] == "ReliefWeb"
        assert "Project Coordinator" in job["title"]
        assert job["company"] == "Save the Children"
        assert job["location"] == "India"
        assert job["url"] == "https://reliefweb.int/job/12345"

    def test_dedup_across_keyword_searches(self, mocker):
        """Same URL returned for multiple keyword searches must appear only once."""
        rss = make_reliefweb_rss([
            {
                "title": "Social Impact Programme Officer",
                "link": "https://reliefweb.int/job/99999",
                "description": '<div class="tag">Country: India</div>',
            }
        ])
        mock_resp = MagicMock()
        mock_resp.content = rss
        mock_resp.raise_for_status = MagicMock()
        mocker.patch.object(self.scraper.session, "get", return_value=mock_resp)

        jobs = self.scraper.fetch_jobs()

        assert len(jobs) >= 1, "fetch_jobs returned 0 jobs — dedup may have removed all results"
        # URL appears in multiple search terms but id is md5 of URL, so deduplicated
        urls = [j["url"] for j in jobs]
        assert len(urls) == len(set(urls)), "Duplicate URLs found — dedup is broken"

    def test_network_error_returns_empty_list(self, mocker):
        """If every RSS request raises, fetch_jobs returns [] without raising."""
        mocker.patch.object(
            self.scraper.session,
            "get",
            side_effect=requests.exceptions.ConnectionError("network down"),
        )
        jobs = self.scraper.fetch_jobs()
        assert jobs == []

    def test_non_matching_jobs_excluded(self, mocker):
        """Jobs that don't match profile keywords should be filtered out."""
        rss = make_reliefweb_rss([
            {
                "title": "Senior Software Engineer",
                "link": "https://reliefweb.int/job/77777",
                "description": "",
            }
        ])
        mock_resp = MagicMock()
        mock_resp.content = rss
        mock_resp.raise_for_status = MagicMock()
        mocker.patch.object(self.scraper.session, "get", return_value=mock_resp)

        jobs = self.scraper.fetch_jobs()
        assert jobs == []

    def test_job_id_is_md5_of_url(self, mocker):
        """job id should follow the reliefweb_<md5> pattern."""
        url = "https://reliefweb.int/job/55555"
        expected_id = f"reliefweb_{hashlib.md5(url.encode()).hexdigest()[:12]}"

        rss = make_reliefweb_rss([
            {
                "title": "NGO Project Manager",
                "link": url,
                "description": '<div class="tag">Country: Nepal</div>',
            }
        ])
        mock_resp = MagicMock()
        mock_resp.content = rss
        mock_resp.raise_for_status = MagicMock()
        mocker.patch.object(self.scraper.session, "get", return_value=mock_resp)

        jobs = self.scraper.fetch_jobs()
        assert any(j["id"] == expected_id for j in jobs)


# ─── LinkedInNGOScraper ───────────────────────────────────────────────────────

class TestLinkedInNGOScraper:
    def setup_method(self):
        self.scraper = LinkedInNGOScraper()

    def test_handles_403_gracefully(self, mocker):
        """A 403 from LinkedIn should not raise — returns empty list."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=403)
        )
        mocker.patch.object(self.scraper.session, "get", return_value=mock_resp)
        # Patch time.sleep so the test doesn't actually wait
        mocker.patch("scraper.time.sleep")

        jobs = self.scraper.fetch_jobs()
        assert jobs == []

    def test_handles_connection_error_gracefully(self, mocker):
        """Connection errors should be caught and return empty list."""
        mocker.patch.object(
            self.scraper.session,
            "get",
            side_effect=requests.exceptions.ConnectionError("blocked"),
        )
        mocker.patch("scraper.time.sleep")

        jobs = self.scraper.fetch_jobs()
        assert jobs == []

    def test_parses_job_cards(self, mocker):
        """Should parse base-card HTML and return matching jobs."""
        html = """
        <html><body>
          <div class="base-card">
            <h3 class="base-search-card__title">CSR Project Coordinator</h3>
            <h4 class="base-search-card__subtitle">Tata Steel</h4>
            <a class="base-card__full-link" href="https://linkedin.com/jobs/view/12345-csr-project">Apply</a>
            <span class="job-search-card__location">Jamshedpur, India</span>
          </div>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mocker.patch.object(self.scraper.session, "get", return_value=mock_resp)
        mocker.patch("scraper.time.sleep")

        jobs = self.scraper.fetch_jobs()

        assert len(jobs) >= 1
        job = jobs[0]
        assert job["source"] == "LinkedIn"
        assert "CSR" in job["title"]
        assert job["company"] == "Tata Steel"
        assert job["location"] == "Jamshedpur, India"
