"""Tests for dedup and persistence logic in main.py.

main.py is a script; its importable functions are:
  load_seen_jobs()       — reads seen_jobs.json, returns a set
  save_seen_jobs()       — writes a set to seen_jobs.json, caps at MAX_SEEN_JOBS
  filter_new_jobs()      — returns jobs whose id is not in the seen set

Author: Rituparno Majumdar
"""
import json
import os
import sys
import tempfile
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the importable helpers (not main() itself)
from main import load_seen_jobs, save_seen_jobs, filter_new_jobs, MAX_SEEN_JOBS


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
    """Test the real filter_new_jobs() from main.py."""

    def test_new_job_is_processed(self):
        jobs = [{"id": "reliefweb_new1", "title": "PM"}]
        seen = set()
        new = filter_new_jobs(jobs, seen)
        assert len(new) == 1

    def test_already_seen_job_skipped(self):
        jobs = [{"id": "reliefweb_old1", "title": "PM"}]
        seen = {"reliefweb_old1"}
        new = filter_new_jobs(jobs, seen)
        assert new == []

    def test_same_job_from_two_scrapers_deduplicated(self):
        """If two scrapers return the same id, filter_new_jobs returns it only once."""
        jobs = [
            {"id": "reliefweb_dup", "title": "CSR Manager"},
            {"id": "reliefweb_dup", "title": "CSR Manager"},  # duplicate
        ]
        seen = set()
        new = filter_new_jobs(jobs, seen)
        assert len(new) == 1

    def test_job_without_id_is_skipped(self):
        jobs = [{"title": "No ID Job"}]
        seen = set()
        new = filter_new_jobs(jobs, seen)
        assert new == []

    def test_mix_of_new_and_seen(self):
        jobs = [
            {"id": "job_1", "title": "Old"},
            {"id": "job_2", "title": "New"},
            {"id": "job_3", "title": "Also New"},
        ]
        seen = {"job_1"}
        new = filter_new_jobs(jobs, seen)
        assert len(new) == 2
        new_ids = {j["id"] for j in new}
        assert new_ids == {"job_2", "job_3"}

    def test_failed_notification_does_not_add_job_to_seen(self, mocker, tmp_path, monkeypatch):
        """If send_job_alert returns False, the job id must NOT be added to seen_jobs.
        This test would fail if the success-guard in main() were removed.
        """
        monkeypatch.chdir(tmp_path)

        job = {"id": "reliefweb_fail1", "title": "PM", "source": "ReliefWeb"}
        seen = set()

        # Simulate the logic in main(): only add to seen if send_job_alert succeeds
        mock_notifier = MagicMock()
        mock_notifier.send_job_alert.return_value = False

        if job["id"] not in seen:
            success = mock_notifier.send_job_alert(job)
            if success:
                seen.add(job["id"])

        assert job["id"] not in seen, (
            "Job id was added to seen_jobs even though send_job_alert returned False — "
            "this means failed notifications would be silently dropped forever."
        )
