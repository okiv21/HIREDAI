import os
from scrapers.base_scraper import BaseScraper, make_job_id

# Adzuna only has job boards for these countries. Nigeria/Ghana are NOT covered,
# so a user there is best served by remote roles (or the za / gb / us boards).
SUPPORTED_COUNTRIES = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb",
    "in", "it", "mx", "nl", "nz", "pl", "sg", "us", "za",
}

# Map common location names the user might pick to Adzuna country codes.
COUNTRY_MAP = {
    "uk": "gb", "united kingdom": "gb", "england": "gb", "britain": "gb",
    "usa": "us", "us": "us", "united states": "us", "america": "us",
    "canada": "ca", "germany": "de", "netherlands": "nl", "holland": "nl",
    "australia": "au", "india": "in", "south africa": "za", "singapore": "sg",
    "france": "fr", "spain": "es", "italy": "it", "brazil": "br",
    "new zealand": "nz", "poland": "pl", "switzerland": "ch", "austria": "at",
    "belgium": "be", "mexico": "mx",
}

DEFAULT_COUNTRY = "gb"


def resolve_country(locations: list) -> str:
    """Pick an Adzuna country code from the user's preferred locations.
    Falls back to gb if none are supported (e.g. they only want remote/Nigeria)."""
    for loc in (locations or []):
        code = COUNTRY_MAP.get((loc or "").strip().lower())
        if code in SUPPORTED_COUNTRIES:
            return code
    return DEFAULT_COUNTRY


class AdzunaScraper(BaseScraper):
    BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"

    def __init__(self, country: str = DEFAULT_COUNTRY):
        super().__init__("adzuna", rate_limit=1.0)
        self.app_id = os.getenv("ADZUNA_APP_ID", "")
        self.api_key = os.getenv("ADZUNA_API_KEY", "")
        self.country = country if country in SUPPORTED_COUNTRIES else DEFAULT_COUNTRY

    def _is_remote(self, raw: dict) -> bool:
        blob = f"{raw.get('title', '')} {raw.get('description', '')}".lower()
        return "remote" in blob or "work from home" in blob or "wfh" in blob

    def normalize(self, raw: dict) -> dict:
        url = raw.get("redirect_url", "")
        return {
            "job_id": make_job_id("adzuna", url),
            "title": raw.get("title", ""),
            "company": raw.get("company", {}).get("display_name", ""),
            "location": raw.get("location", {}).get("display_name", ""),
            "salary": f"{raw.get('salary_min', '')} - {raw.get('salary_max', '')}",
            "description": raw.get("description", ""),
            "url": url,
            "platform": "adzuna",
            "work_type": "remote" if self._is_remote(raw) else "onsite"
        }

    def fetch(self, keywords: list, location: str = "", work_type: str = "remote") -> list:
        if not self.app_id or not self.api_key:
            print("  [adzuna] Missing API credentials — skipping")
            return []

        jobs = []
        for keyword in keywords[:5]:  # limit to avoid hammering API
            url = self.BASE_URL.format(country=self.country)
            params = {
                "app_id": self.app_id,
                "app_key": self.api_key,
                "results_per_page": 20,
                "what": keyword,
                "content-type": "application/json"
            }
            if work_type == "remote":
                params["what"] = f"{keyword} remote"

            data = self.get(url, params=params)
            if data and "results" in data:
                for item in data["results"]:
                    jobs.append(self.normalize(item))
                print(f"  [adzuna] '{keyword}' ({self.country}): {len(data['results'])} jobs")

        return jobs
