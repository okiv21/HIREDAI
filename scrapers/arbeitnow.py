from scrapers.base_scraper import BaseScraper, make_job_id


class ArbeitnowScraper(BaseScraper):
    BASE_URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self):
        super().__init__("arbeitnow", rate_limit=1.0)

    def normalize(self, raw: dict) -> dict:
        url = raw.get("url", "")
        return {
            "job_id": make_job_id("arbeitnow", url),
            "title": raw.get("title", ""),
            "company": raw.get("company_name", ""),
            "location": raw.get("location", ""),
            "salary": "",
            "description": raw.get("description", "")[:2000],
            "url": url,
            "platform": "arbeitnow",
            "work_type": "remote" if raw.get("remote", False) else "onsite"
        }

    def fetch(self, keywords: list, location: str = "", work_type: str = "remote") -> list:
        data = self.get(self.BASE_URL)
        if not data or "data" not in data:
            return []
        jobs = [self.normalize(item) for item in data["data"]]
        print(f"  [arbeitnow] fetched {len(jobs)} jobs")
        return jobs
