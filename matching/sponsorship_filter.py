import json
from pathlib import Path

PREFS_PATH = Path(__file__).parent.parent / "config" / "job_prefs.json"


def load_sponsorship_keywords() -> list:
    prefs = json.loads(PREFS_PATH.read_text())
    return [kw.lower() for kw in prefs.get("sponsorship_keywords", [])]


def check_sponsorship(text: str) -> bool:
    """Returns True if job description mentions sponsorship/relocation support."""
    text_lower = text.lower()
    keywords = load_sponsorship_keywords()
    return any(kw in text_lower for kw in keywords)


def check_exclusions(text: str) -> bool:
    """Returns True if job should be excluded (e.g. requires 10+ years)."""
    prefs = json.loads(PREFS_PATH.read_text())
    exclude = [kw.lower() for kw in prefs.get("exclude_keywords", [])]
    text_lower = text.lower()
    return any(kw in text_lower for kw in exclude)
