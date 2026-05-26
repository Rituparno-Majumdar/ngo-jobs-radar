"""Tests for notifier.py — TelegramNotifier.

Author: Rituparno Majumdar
"""
import pytest
import requests
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifier import TelegramNotifier


SAMPLE_JOB = {
    "id": "reliefweb_abc123",
    "title": "Project Coordinator",
    "company": "Save the Children",
    "location": "India",
    "url": "https://reliefweb.int/job/12345",
    "source": "ReliefWeb",
    "description": "Coordinate community development activities in rural India.",
    "date_posted": "2026-05-26",
}


class TestTelegramNotifier:
    def test_send_job_alert_success(self, mocker):
        """send_job_alert returns True when Telegram responds 200."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("notifier.requests.post", return_value=mock_resp)

        result = notifier.send_job_alert(SAMPLE_JOB)

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert payload["chat_id"] == "fake_chat"
        assert payload["parse_mode"] == "HTML"

    def test_send_job_alert_missing_credentials_returns_false(self):
        """send_job_alert returns False when bot_token or chat_id is missing."""
        notifier = TelegramNotifier(bot_token=None, chat_id=None)
        # Also clear env vars so there's no fallback
        result = notifier.send_job_alert(SAMPLE_JOB)
        assert result is False

    def test_send_job_alert_retries_on_request_exception(self, mocker):
        """send_job_alert retries 3 times on RequestException and returns False."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")
        mocker.patch("notifier.time.sleep")  # don't actually sleep during retries
        mock_post = mocker.patch(
            "notifier.requests.post",
            side_effect=requests.exceptions.RequestException("timeout"),
        )

        result = notifier.send_job_alert(SAMPLE_JOB)

        assert result is False
        assert mock_post.call_count == 3  # 3 attempts total

    def test_send_job_alert_url_with_ampersand_escaped(self, mocker):
        """URLs with & must be escaped to &amp; in the Telegram HTML payload."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("notifier.requests.post", return_value=mock_resp)

        job_with_amp = dict(SAMPLE_JOB, url="https://example.com/jobs?q=ngo&l=india")
        notifier.send_job_alert(job_with_amp)

        payload = mock_post.call_args[1]["json"]
        assert "&amp;" in payload["text"]
        assert "&l=india" not in payload["text"]  # raw & should not appear in href

    def test_send_summary_success(self, mocker):
        """send_summary returns True on a 200 response."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mocker.patch("notifier.requests.post", return_value=mock_resp)

        result = notifier.send_summary(total_new=3, total_checked=15)
        assert result is True

    def test_send_summary_no_jobs_message(self, mocker):
        """send_summary uses 'no new listings' text when total_new == 0."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("notifier.requests.post", return_value=mock_resp)

        notifier.send_summary(total_new=0, total_checked=10)

        payload = mock_post.call_args[1]["json"]
        assert "No new listings" in payload["text"]

    def test_send_summary_missing_credentials_returns_false(self):
        """send_summary returns False when credentials are missing."""
        notifier = TelegramNotifier(bot_token=None, chat_id=None)
        result = notifier.send_summary(total_new=1, total_checked=5)
        assert result is False

    def test_send_summary_returns_false_on_network_failure(self, mocker):
        """send_summary should catch network errors and return False."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")
        mocker.patch(
            "notifier.requests.post",
            side_effect=requests.exceptions.RequestException("network error"),
        )
        result = notifier.send_summary(total_new=5, total_checked=20)
        assert result is False

    def test_send_job_alert_invalid_url(self, mocker):
        """Jobs with invalid URLs should still send (with fallback text, not a link)."""
        notifier = TelegramNotifier(bot_token="fake_token", chat_id="fake_chat")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("notifier.requests.post", return_value=mock_resp)

        job_bad_url = dict(SAMPLE_JOB, url="not_a_url")
        result = notifier.send_job_alert(job_bad_url)

        assert result is True
        payload = mock_post.call_args[1]["json"]
        assert "⚠️" in payload["text"]  # fallback warning text
