"""Shared HTTP plumbing for Telegram API calls: sessions and retrying requests."""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger("agenttg")

_MAX_RETRIES = 3
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def make_session() -> requests.Session:
    """Create a new session configured with TELEGRAM_HTTPS_PROXY if set."""
    session = requests.Session()
    proxy = os.environ.get("TELEGRAM_HTTPS_PROXY")
    if proxy:
        session.proxies = {"https": proxy}
    return session


def _request_with_retry(session, http_method, url, **kwargs):
    """Execute an HTTP request with exponential backoff retry on transient errors."""
    files = kwargs.get("files")
    for attempt in range(_MAX_RETRIES):
        try:
            resp = getattr(session, http_method)(url, **kwargs)
            if resp.status_code not in _RETRY_STATUSES or attempt == _MAX_RETRIES - 1:
                return resp
            logger.warning(
                "Telegram API %s returned %s (body: %s), retry %d/%d",
                url.rsplit("/", 1)[-1],
                resp.status_code,
                resp.text[:200],
                attempt + 1,
                _MAX_RETRIES - 1,
            )
        except requests.RequestException as exc:
            if attempt == _MAX_RETRIES - 1:
                raise
            logger.warning(
                "Telegram API %s request failed: %s, retry %d/%d",
                url.rsplit("/", 1)[-1],
                exc,
                attempt + 1,
                _MAX_RETRIES - 1,
            )
        if files:
            for f in files.values():
                if hasattr(f, "seek"):
                    f.seek(0)
        time.sleep(2**attempt)
