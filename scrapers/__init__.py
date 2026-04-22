"""Scraper adapters for JobBot."""
from __future__ import annotations

import logging
import time

LOGGER = logging.getLogger(__name__)
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def scrape_with_retry(fn, *, max_attempts: int = 3, base_delay: float = 2.0):
    """Call fn(), retrying on transient network/HTTP errors with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            exc_text = str(exc)
            status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            # Try to pull status from requests.HTTPError.response
            if status_code is None:
                response = getattr(exc, "response", None)
                if response is not None:
                    status_code = getattr(response, "status_code", None)
            if status_code in {400, 401, 403}:
                raise
            is_retryable = (
                status_code in _RETRYABLE_HTTP_CODES
                or status_code is None
                or "timeout" in exc_text.lower()
                or "rate limit" in exc_text.lower()
                or "connection" in exc_text.lower()
            )
            if not is_retryable or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt)
            LOGGER.warning("Scraper transient error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, max_attempts, delay, exc_text[:120])
            last_exc = exc
            time.sleep(delay)
    raise last_exc  # pragma: no cover
