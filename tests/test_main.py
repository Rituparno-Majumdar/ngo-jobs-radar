"""Tests for dedup and persistence logic in main.py.

main.py is a script; its importable functions are:
  load_seen_jobs()  — reads seen_jobs.json, returns a set
  save_seen_jobs()  — writes a set to seen_jobs.json, caps at MAX_SEEN_JOBS

Author: Rituparno Majumdar
"""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the importable helpers (not main() itself)
from main import load_seen_jobs, save_seen_jobs, MAX_SEEN_JOBS


class TestLoadSeenJobs:
    def test_returns_empty_set_when_file_missing(self, tmp_path, monkeypatch):
        """load_seen_jobs returns an empty set if seen_jobs.json doesn't exist."""
        monkeypatch.chdir(tmp_path)
        result = load_seen_jobs()
        assert result == set()

    def test_loads_existing_ids(self, tmp_path, monkeypatch):
        """load_seen_jobs returns the ids stored in seen_jobs.json."""
        monkeypatch.chdir(tmp_path)
        ids = ["reliefweb_abc", "linkedin_123", "indeed_xyz"]
        (tmp_path / "seen_jobs.json").write_text(json.dumps(ids))

        result = load_seen_jobs()
        assert result == set(ids)

    def test_returns_empty_set_on_corrupt_json(self, tmp_path, monkeypatch):
        """load_seen_jobs returns empty set (not raises) if json is corrupt."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "seen_jobs.json").write_text("not valid json {{")

        result = load_seen_jobs()
        assert result == set()


class TestSaveSeenJobs:
    def test_saves_ids_to_file(self, tmp_path, monkeypatch):
        """save_seen_jobs writes ids as a JSON list."""
        monkeypatch.chdir(tmp_path)
        ids = {"reliefweb_abc", "linkedin_123"}
        save_seen_jobs(ids)

        data = json.loads((tmp_path / "seen_jobs.json").read_text())
        assert set(data) == ids

    def test_caps_at_max_seen_jobs(self, tmp_path, monkeypatch):
        """save_seen_jobs keeps only the last MAX_SEEN_JOBS entries."""
        monkeypatch.chdir(tmp_path)
        # Create more IDs than MAX_SEEN_JOBS
        big_set = {f"job_{i}" for i in range(MAX_SEEN_JOBS + 500)}
        save_seen_jobs(big_set)

        data = json.loads((tmp_path / "seen_jobs.json").read_text())
        assert len(data) == MAX_SEEN_JOBS

    def test_roundtrip(self, tmp_path, monkeypatch):
        """IDs saved and then loaded should be identical."""
        monkeypatch.chdir(tmp_path)
        ids = {"reliefweb_abc", "linkedin_123", "devnet_xyz"}
        save_seen_jobs(ids)
        loaded = load_seen_jobs()
        assert loaded == ids


class TestDedupLogic:
    """Test the dedup pattern used in main(): only notify jobs not already in seen_jobs."""

    def _run_dedup(self, jobs, seen_jobs):
        """Replicate the dedup logic from main() inline."""
        new_jobs = []
        for job in jobs:
            job_id = job.get("id")
            if not job_id:
                continue
            if job_id not in seen_jobs:
                seen_jobs.add(job_id)
                new_jobs.append(job)
        return new_jobs

    def test_new_job_is_processed(self):
        jobs = [{"id": "reliefweb_new1", "title": "PM"}]
        seen = set()
        new = self._run_dedup(jobs, seen)
        assert len(new) == 1
        assert "reliefweb_new1" in seen

    def test_already_seen_job_skipped(self):
        jobs = [{"id": "reliefweb_old1", "title": "PM"}]
        seen = {"reliefweb_old1"}
        new = self._run_dedup(jobs, seen)
        assert new == []

    def test_same_job_from_two_scrapers_deduplicated(self):
        """If two scrapers return the same id, it should only be sent once."""
        jobs = [
            {"id": "reliefweb_dup", "title": "CSR Manager"},
            {"id": "reliefweb_dup", "title": "CSR Manager"},  # duplicate
        ]
        seen = set()
        new = self._run_dedup(jobs, seen)
        assert len(new) == 1

    def test_job_without_id_is_skipped(self):
        jobs = [{"title": "No ID Job"}]
        seen = set()
        new = self._run_dedup(jobs, seen)
        assert new == []

    def test_mix_of_new_and_seen(self):
        jobs = [
            {"id": "job_1", "title": "Old"},
            {"id": "job_2", "title": "New"},
            {"id": "job_3", "title": "Also New"},
        ]
        seen = {"job_1"}
        new = self._run_dedup(jobs, seen)
        assert len(new) == 2
        new_ids = {j["id"] for j in new}
        assert new_ids == {"job_2", "job_3"}
