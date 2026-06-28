import os
import base64
from scrapers.base_scraper import BaseScraper, make_job_id


class ReedScraper(BaseScraper):
    BASE_URL = "https://www.reed.co.uk/api/1.0/search"

    def __init__(self):
        super().__init__("reed", rate_limit=1.5)
        self.api_key = os.getenv("REED_API_KEY", "")

    def normalize(self, raw: dict) -> dict:
        url = f"https://www.reed.co.uk/jobs/{raw.get('jobId', '')}"
        return {
            "job_id": make_job_id("reed", url),
            "title": raw.get("jobTitle", ""),
            "company": raw.get("employerName", ""),
            "location": raw.get("locationName", ""),
            "salary": f"{raw.get('minimumSalary', '')} - {raw.get('maximumSalary', '')}",
            "description": raw.get("jobDescription", "")[:2000],
            "url": url,
            "platform": "reed",
            "work_type": "remote" if raw.get("locationName", "").lower() == "remote" else "onsite"
        }

    def fetch(self, keywords: list, location: str = "", work_type: str = "remote") -> list:
        if not self.api_key:
            print("  [reed] Missing API key — skipping")
            return []

        encoded = base64.b64encode(f"{self.api_key}:".encode()).decode()
        self.session.headers["Authorization"] = f"Basic {encoded}"

        jobs = []
        for keyword in keywords[:4]:
            params = {"keywords": keyword, "resultsToTake": 20}
            if work_type == "remote":
                params["locationName"] = "remote"
            data = self.get(self.BASE_URL, params=params)
            if data and "results" in data:
                for item in data["results"]:
                    jobs.append(self.normalize(item))
                print(f"  [reed] '{keyword}': {len(data['results'])} jobs")
        return jobs
