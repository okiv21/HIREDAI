import time
import hashlib
import requests
from abc import ABC, abstractmethod


def make_job_id(platform: str, url: str) -> str:
    """Generate a stable unique ID for a job listing."""
    return hashlib.md5(f"{platform}:{url}".encode()).hexdigest()


class BaseScraper(ABC):
    def __init__(self, name: str, rate_limit: float = 1.0):
        self.name = name
        self.rate_limit = rate_limit  # seconds between requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def get(self, url: str, params: dict = None, **kwargs) -> dict | None:
        try:
            time.sleep(self.rate_limit)
            resp = self.session.get(url, params=params, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  [{self.name}] Request failed: {e}")
            return None

    def normalize(self, raw: dict) -> dict:
        """Subclasses map their API response to a standard job dict."""
        raise NotImplementedError

    @abstractmethod
    def fetch(self, keywords: list, location: str, work_type: str) -> list:
        """Return a list of normalized job dicts."""
        pass
