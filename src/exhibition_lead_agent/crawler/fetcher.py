import time
import random
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx

from exhibition_lead_agent.crawler.cache import DiskCache
from exhibition_lead_agent.crawler.robots import RobotsChecker
from exhibition_lead_agent.db.database import get_db
from exhibition_lead_agent.db.models import FetchLogDB, SnapshotDB

USER_AGENT = "ExhibitionLeadBot/1.0 (+https://github.com/exhibition-lead-agent)"

class Fetcher:
    def __init__(self, request_budget: int = 1000, cache_db: str = ".crawl_cache.db"):
        self.request_budget = request_budget
        self.requests_made = 0
        self.cache = DiskCache(cache_db=cache_db)
        self.robots = RobotsChecker(user_agent=USER_AGENT)
        self.last_request_time = {} # domain -> float timestamp
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=15.0
        )

    def fetch(self, url: str, ignore_robots: bool = False) -> Tuple[int, str, bool]:
        """
        Returns (status_code, html_content, from_cache).
        """
        # 1. Check Cache
        cached = self.cache.get(url)
        if cached:
            status_code, content_bytes = cached
            html = content_bytes.decode("utf-8", errors="replace")
            self._log_fetch(url, status_code, from_cache=True, num_bytes=len(content_bytes))
            return status_code, html, True

        # 2. Check Budget
        if self.requests_made >= self.request_budget:
            raise RuntimeError(f"Request budget limit reached ({self.request_budget} requests)")

        # 3. Check Robots.txt
        if not ignore_robots and not self.robots.is_allowed(url):
            raise RuntimeError(f"Crawling blocked by robots.txt for URL: {url}")

        # 4. Rate Limiting (2-3 seconds per host)
        parsed = urlparse(url)
        domain = parsed.netloc
        now = time.time()
        if domain in self.last_request_time:
            elapsed = now - self.last_request_time[domain]
            delay = random.uniform(2.0, 3.0)
            if elapsed < delay:
                time.sleep(delay - elapsed)

        # 5. Fetch with retry on 429 / 5xx with exponential backoff
        max_retries = 3
        backoff = 2.0
        for attempt in range(max_retries):
            self.requests_made += 1
            self.last_request_time[domain] = time.time()
            try:
                resp = self.client.get(url)
                status_code = resp.status_code
                content_bytes = resp.content

                if status_code in (429, 500, 502, 503, 504):
                    # Check Retry-After
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_sec = float(retry_after)
                        except ValueError:
                            wait_sec = backoff
                    else:
                        wait_sec = backoff

                    if attempt < max_retries - 1:
                        time.sleep(wait_sec)
                        backoff *= 2
                        continue
                    else:
                        if status_code == 429:
                            raise RuntimeError(f"Host {domain} returned rate limit 429 persistent block.")

                # Cache response
                self.cache.set(url, status_code, content_bytes)
                html = content_bytes.decode("utf-8", errors="replace")
                self._log_fetch(url, status_code, from_cache=False, num_bytes=len(content_bytes))
                return status_code, html, False

            except httpx.RequestError as exc:
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    self._log_fetch(url, 0, from_cache=False, num_bytes=0, error=str(exc))
                    raise exc

        return 0, "", False

    def save_snapshot(self, url: str, reason: str, html_content: str):
        db = get_db()
        try:
            snapshot = SnapshotDB(url=url, reason=reason, html_content=html_content)
            db.add(snapshot)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _log_fetch(self, url: str, status: int, from_cache: bool, num_bytes: int, error: Optional[str] = None):
        db = get_db()
        try:
            log_entry = FetchLogDB(
                url=url,
                status=status,
                from_cache=from_cache,
                bytes=num_bytes,
                error=error
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
