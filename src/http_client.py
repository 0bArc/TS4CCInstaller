from __future__ import annotations

import random
import threading
import time
from typing import Any, Mapping, MutableMapping, Optional

import requests
from requests.adapters import HTTPAdapter

from logger import logger

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
BASE = "https://www.thesimsresource.com"

DEFAULT_TIMEOUT = (10, 30)  # connect, read
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_thread_local = threading.local()
_retry_statuses = {429, 503}


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=0)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def session() -> requests.Session:
    """Thread-local Session so Flask workers do not share one cookie jar."""
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = _new_session()
        _thread_local.session = s
    return s


def new_session() -> requests.Session:
    """Fresh Session (e.g. captcha / download job)."""
    return _new_session()


def _sleep_backoff(attempt: int, retry_after: Optional[str] = None) -> None:
    if retry_after:
        try:
            delay = float(retry_after)
            time.sleep(min(max(delay, 0.5), 60.0))
            return
        except ValueError:
            pass
    base = min(2**attempt, 20)
    time.sleep(base + random.uniform(0.1, 0.8))


def request(
    method: str,
    url: str,
    *,
    sess: Optional[requests.Session] = None,
    timeout: Any = DEFAULT_TIMEOUT,
    retries: int = 3,
    headers: Optional[Mapping[str, str]] = None,
    **kwargs: Any,
) -> requests.Response:
    """HTTP request with timeouts and backoff on 429/503."""
    s = sess or session()
    last: Optional[requests.Response] = None
    for attempt in range(retries + 1):
        try:
            resp = s.request(
                method,
                url,
                timeout=timeout,
                headers=dict(headers) if headers else None,
                **kwargs,
            )
            if resp.status_code in _retry_statuses and attempt < retries:
                logger.warning(
                    f"HTTP {resp.status_code} for {url}; backing off (attempt {attempt + 1})"
                )
                _sleep_backoff(attempt, resp.headers.get("Retry-After"))
                last = resp
                continue
            return resp
        except requests.RequestException as e:
            if attempt >= retries:
                raise
            logger.warning(f"Request error for {url}: {e}; retrying")
            _sleep_backoff(attempt)
    if last is not None:
        return last
    raise RuntimeError(f"request failed: {method} {url}")


def get(url: str, **kwargs: Any) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    return request("POST", url, **kwargs)
