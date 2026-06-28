"""
run_agent_multiuser.py — runs one user's scrape → score → prepare cycle.

Unlike the single-user run_agent.py (which runs on a GitHub Actions cron
for just you), this version is called on-demand from the Streamlit
dashboard's "Run agent now" button, scoped to whichever user clicked it.

API keys (Groq, Adzuna) come from the server's .env — shared across the
small group of users at this scale — but every job, CV, and result stays
scoped to that user's user_id in the database.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager_multiuser import (
    save_job, job_exists, log_run, get_user,
)
from matching.embedder import embed_text, load_cv_embedding, embed_cv
from matching.scorer import score_job, seniority_allowed, region_allowed

from scrapers.adzuna import AdzunaScraper, resolve_country
from scrapers.remotive import RemotiveScraper
from scrapers.arbeitnow import ArbeitnowScraper
from scrapers.himalayas import HimalayasScraper

PLATFORMS_PATH = Path(__file__).parent.parent / "config" / "platforms.json"


def _active_scrapers(adzuna_country: str = "gb") -> list:
    platforms = json.loads(PLATFORMS_PATH.read_text())
    scrapers = []
    if platforms.get("adzuna", {}).get("enabled"):
        scrapers.append(AdzunaScraper(country=adzuna_country))
    if platforms.get("remotive", {}).get("enabled"):
        scrapers.append(RemotiveScraper())
    if platforms.get("arbeitnow", {}).get("enabled"):
        scrapers.append(ArbeitnowScraper())
    if platforms.get("himalayas", {}).get("enabled"):
        scrapers.append(HimalayasScraper())
    return scrapers


def _user_cv_embedding_path(user_id: str) -> Path:
    p = Path(__file__).parent.parent / "data" / "users" / user_id / "cv_embedding.npy"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_for_user(user_id: str, max_results: int = 15) -> dict:
    """
    Scrapes jobs, scores them against this user's structured CV, and saves
    matches to the database as 'pending' (not yet prepared for review).

    Returns a stats dict: {scraped, matched, errors}
    """
    stats = {"scraped": 0, "matched": 0, "errors": []}

    user = get_user(user_id)
    if not user or not user.get("cv_structured"):
        stats["errors"].append("No structured CV found for this user")
        log_run(user_id, stats)
        return stats

    cv_structured = json.loads(user["cv_structured"])
    cv_skills = cv_structured.get("skills", [])
    prefs = json.loads(user["job_prefs"]) if user.get("job_prefs") else {}
    keywords = prefs.get("job_titles", ["Data Scientist"])
    work_types = prefs.get("work_types", ["remote"])
    work_type = work_types[0] if work_types else "remote"
    min_score = prefs.get("min_match_score", 0.55)
    allowed_levels = prefs.get("seniority_levels", [])
    locations = prefs.get("locations", [])
    adzuna_country = resolve_country(locations)

    # Build a one-line CV summary text for embedding (skills + any bullets)
    cv_text_parts = cv_skills.copy()
    for exp in cv_structured.get("experience", []):
        cv_text_parts.extend(exp.get("bullets", []))
    for proj in cv_structured.get("projects", []):
        cv_text_parts.extend(proj.get("bullets", []))
    cv_text = " ".join(cv_text_parts)[:3000]

    # Embed this user's CV (cached per-user, not shared with other users)
    embedding_path = _user_cv_embedding_path(user_id)
    import numpy as np
    try:
        if embedding_path.exists():
            cv_embedding = np.load(embedding_path)
        else:
            cv_embedding = embed_text(cv_text)
            np.save(embedding_path, cv_embedding)
    except Exception as e:
        stats["errors"].append(
            f"CV embedding failed ({e}) — matches will rely on keyword overlap only, "
            f"which is much less accurate. Check sentence-transformers is installed."
        )
        cv_embedding = None

    all_jobs = []
    for scraper in _active_scrapers(adzuna_country=adzuna_country):
        try:
            jobs = scraper.fetch(keywords=keywords, work_type=work_type)
            new_jobs = [j for j in jobs if not job_exists(user_id, j["job_id"])]
            all_jobs.extend(new_jobs)
        except Exception as e:
            stats["errors"].append(f"{scraper.name}: {e}")

    stats["scraped"] = len(all_jobs)

    all_scores = []
    skipped_seniority = 0
    skipped_region = 0
    for job in all_jobs:
        # Drop jobs the user can't actually work from their region (e.g. onsite
        # UK roles when they only want remote) before spending a score on them.
        if not region_allowed(job, work_types, locations):
            skipped_region += 1
            continue

        scored = score_job(job, cv_skills, cv_embedding=cv_embedding)
        if not scored:
            continue
        all_scores.append(scored["match_score"])
        # Drop roles whose seniority the user didn't ask for (e.g. senior
        # roles when they selected only entry/junior).
        if not seniority_allowed(scored["seniority"], allowed_levels):
            skipped_seniority += 1
            continue
        if scored["match_score"] >= min_score:
            save_job(user_id, scored)
            stats["matched"] += 1

    stats["skipped_seniority"] = skipped_seniority
    stats["skipped_region"] = skipped_region

    if all_scores:
        stats["max_score"] = round(max(all_scores), 3)
        stats["avg_score"] = round(sum(all_scores) / len(all_scores), 3)
    else:
        stats["max_score"] = None
        stats["avg_score"] = None

    log_run(user_id, stats)
    return stats


def prepare_matched_jobs(user_id: str, max_to_prepare: int = 5) -> dict:
    """
    Takes the top 'pending' matched jobs (highest match_score first, since
    get_jobs already orders by score) and prepares them — tailors the CV,
    writes the cover letter — so they show up in the user's review queue.
    Stops short of submitting anything.

    Capped at 5 by default: each prepared job makes 1-2 Groq API calls
    (cover letter + CV tailoring), and Groq's free tier rate-limits fairly
    aggressively. Preparing too many in one run causes some cover letters
    to fail with empty/error text — 5 keeps a single run comfortably under
    that limit while still surfacing your best matches.
    """
    from database.db_manager_multiuser import get_jobs
    from applicator.apply_manager_multiuser import prepare_application, submit_application

    user = get_user(user_id)
    cv_structured = json.loads(user["cv_structured"])
    cv_text = " ".join(cv_structured.get("skills", []))
    auto_apply = bool(user.get("auto_apply"))

    pending = get_jobs(user_id, status="pending", limit=max_to_prepare)
    prepared_count = 0
    auto_submitted = 0

    for i, job in enumerate(pending):
        result = prepare_application(user_id, job, cv_structured, cv_text)
        if result.get("status") == "awaiting_review":
            prepared_count += 1
            # If the user opted out of the review step, submit immediately.
            if auto_apply:
                outcome = submit_application(
                    user_id, job, result.get("tailored_cv_path"),
                    structured_cv=cv_structured,
                )
                if outcome == "applied":
                    auto_submitted += 1
        if i < len(pending) - 1:
            time.sleep(2)  # space out Groq calls to stay under rate limits

    return {"prepared": prepared_count, "auto_submitted": auto_submitted,
            "auto_apply": auto_apply}