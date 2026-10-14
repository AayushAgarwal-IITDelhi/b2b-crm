import urllib.robotparser
from urllib.parse import urlparse
import httpx

class RobotsChecker:
    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self.parsers = {}

    def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        if domain not in self.parsers:
            robots_url = f"{domain}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = httpx.get(robots_url, timeout=5.0, headers={"User-Agent": self.user_agent})
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.allow_all = True
            except Exception:
                rp.allow_all = True
            self.parsers[domain] = rp
        return self.parsers[domain].can_fetch(self.user_agent, url)
