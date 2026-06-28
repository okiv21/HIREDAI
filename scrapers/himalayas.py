from scrapers.base_scraper import BaseScraper, make_job_id


class HimalayasScraper(BaseScraper):
    BASE_URL = "https://himalayas.app/jobs/api"

    def __init__(self):
        super().__init__("himalayas", rate_limit=1.5)

    @staticmethod
    def _as_text(value, default: str = "") -> str:
        """Himalayas returns some fields (e.g. locationRestrictions) as lists —
        flatten them to a comma-separated string so they're storable."""
        if isinstance(value, list):
            return ", ".join(str(v) for v in value) or default
        if value in (None, ""):
            return default
        return str(value)

    def normalize(self, raw: dict) -> dict:
        url = raw.get("applicationLink", raw.get("url", ""))
        return {
            "job_id": make_job_id("himalayas", url),
            "title": self._as_text(raw.get("title")),
            "company": self._as_text(raw.get("companyName")),
            "location": self._as_text(raw.get("locationRestrictions"), "Worldwide"),
            "salary": self._as_text(raw.get("salary")),
            "description": self._as_text(raw.get("description"))[:2000],
            "url": url,
            "platform": "himalayas",
            "work_type": "remote"
        }

    def fetch(self, keywords: list, location: str = "", work_type: str = "remote") -> list:
        jobs = []
        for keyword in keywords[:4]:
            data = self.get(self.BASE_URL, params={"q": keyword, "limit": 20})
            if data and "jobs" in data:
                for item in data["jobs"]:
                    jobs.append(self.normalize(item))
                print(f"  [himalayas] '{keyword}': {len(data['jobs'])} jobs")
        return jobs
