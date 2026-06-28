from scrapers.base_scraper import BaseScraper, make_job_id


class RemotiveScraper(BaseScraper):
    BASE_URL = "https://remotive.com/api/remote-jobs"

    def __init__(self):
        super().__init__("remotive", rate_limit=1.5)

    def normalize(self, raw: dict) -> dict:
        url = raw.get("url", "")
        return {
            "job_id": make_job_id("remotive", url),
            "title": raw.get("title", ""),
            "company": raw.get("company_name", ""),
            "location": raw.get("candidate_required_location", "Worldwide"),
            "salary": raw.get("salary", ""),
            "description": raw.get("description", "")[:2000],
            "url": url,
            "platform": "remotive",
            "work_type": "remote"
        }

    def fetch(self, keywords: list, location: str = "", work_type: str = "remote") -> list:
        jobs = []
        for keyword in keywords[:4]:
            data = self.get(self.BASE_URL, params={"search": keyword, "limit": 20})
            if data and "jobs" in data:
                for item in data["jobs"]:
                    jobs.append(self.normalize(item))
                print(f"  [remotive] '{keyword}': {len(data['jobs'])} jobs")
        return jobs
