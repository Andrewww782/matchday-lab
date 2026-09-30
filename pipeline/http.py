"""Polite HTTP with an on-disk cache so the pipeline never hammers a source."""
import hashlib
import json
import time
from pathlib import Path

import requests

from pipeline.config import RAW, USER_AGENT

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_CACHE = RAW / "http"
_CACHE.mkdir(parents=True, exist_ok=True)

# Sources that failed this run and were served from an older cached copy (reported by run_all).
STALE: set[str] = set()


def _path(url: str, suffix: str) -> Path:
    return _CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + suffix)


def get_bytes(url: str, max_age_hours: float = 12, retries: int = 3, user_agent: str | None = None) -> bytes:
    """GET a URL, reusing a cached copy younger than max_age_hours.

    max_age_hours=float("inf") caches forever (for finished seasons). `user_agent` overrides the
    default for sources that only accept certain clients."""
    p = _path(url, ".bin")
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_hours * 3600:
        return p.read_bytes()
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=60, headers={"User-Agent": user_agent} if user_agent else None)
            r.raise_for_status()
            p.write_bytes(r.content)
            time.sleep(0.5)  # be gentle with free sources
            return r.content
        except requests.RequestException:
            if attempt == retries - 1:
                if p.exists():  # stale cache beats no data
                    STALE.add(url)
                    return p.read_bytes()
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def get_json(url: str, max_age_hours: float = 12, user_agent: str | None = None):
    return json.loads(get_bytes(url, max_age_hours, user_agent=user_agent))


def cached_json(key: str, fn, max_age_hours: float = 12):
    """Cache the JSON result of an arbitrary fetch function (e.g. a scraper)."""
    p = _path(key, ".json")
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_hours * 3600:
        return json.loads(p.read_text(encoding="utf-8"))
    try:
        data = fn()
    except Exception:
        if p.exists():
            STALE.add(key)
            return json.loads(p.read_text(encoding="utf-8"))
        raise
    p.write_text(json.dumps(data), encoding="utf-8")
    return data
