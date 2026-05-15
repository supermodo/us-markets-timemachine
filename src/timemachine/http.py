"""HTTPS fetcher with timeout, bounded retry-with-backoff, custom User-Agent.

stdlib only — urllib.request. Avoids the `requests` dependency to keep v1
zero-runtime-deps and immune to supply-chain churn.

Errors are normalized to FetchError; the caller (capture / mirror) treats any
FetchError as a `missing` status in the manifest, never as a `data` outcome.
"""

import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = (
    "us-markets-timemachine/0.1 (+https://github.com/supermac/us-markets-timemachine) "
    "[autonomous archive worker]"
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.5  # 1.5s, 2.25s, 3.375s — bounded total ~7s


class FetchError(Exception):
    """A fetch ultimately failed after exhausting retries (or fatal HTTP error)."""


def fetch(
    url: str,
    *,
    user_agent: str = USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    sleep: callable = time.sleep,  # injectable for tests
) -> bytes:
    """Fetch `url` with retries on transient errors.

    `user_agent` defaults to a generic project string; sources with stricter
    UA requirements (notably SEC EDGAR, which mandates "Name email@host" and
    silently 403s otherwise) override it explicitly.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = Request(url, headers={"User-Agent": user_agent})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as e:
            # Retry transient server errors; give up on client errors (4xx).
            if 500 <= e.code < 600 and attempt + 1 < max_retries:
                last_error = e
                sleep(backoff_base * (2**attempt))
                continue
            raise FetchError(f"HTTP {e.code} for {url}") from e
        except (URLError, TimeoutError) as e:
            last_error = e
            if attempt + 1 < max_retries:
                sleep(backoff_base * (2**attempt))
                continue
            raise FetchError(f"network error for {url}: {e}") from e

    raise FetchError(f"exhausted retries for {url}: {last_error}")
