import json
import numpy as np
from pathlib import Path
from matching.embedder import embed_text, load_cv_embedding, cosine_similarity
from matching.sponsorship_filter import check_sponsorship, check_exclusions

PREFS_PATH = Path(__file__).parent.parent / "config" / "job_prefs.json"


def load_prefs() -> dict:
    return json.loads(PREFS_PATH.read_text())


# ---------- Seniority detection ----------

# Order matters: senior signals are checked before junior ones so that a title
# like "Senior Graduate Programme Lead" is correctly flagged senior, not graduate.
_SENIOR_SIGNALS = [
    "senior", "sr.", "sr ", "lead", "principal", "staff",
    "head of", "manager", "director", "vp", "vice president",
    "architect", "chief", "10+ years", "8+ years", "7+ years",
]
_INTERN_SIGNALS = ["intern", "internship", "placement year", "industrial placement"]
_GRADUATE_SIGNALS = ["graduate", "new grad", "trainee", "early careers", "apprentice"]
_JUNIOR_SIGNALS = ["junior", "jr.", "jr ", "associate"]
_ENTRY_SIGNALS = ["entry level", "entry-level", "no experience", "0-2 years", "1-2 years"]
_MID_SIGNALS = ["mid-level", "mid level", "3-5 years", "4+ years", "5+ years"]


def detect_seniority(title: str, description: str = "") -> str:
    """
    Classify a job into: intern, graduate, entry, junior, mid, senior, or
    'unspecified' when the posting gives no clear level signal.

    Title is weighted most heavily; description is a fallback signal.
    """
    t = (title or "").lower()
    d = (description or "").lower()[:600]  # only the opening of the description

    if any(s in t for s in _INTERN_SIGNALS):
        return "intern"
    if any(s in t for s in _SENIOR_SIGNALS):
        return "senior"
    if any(s in t for s in _GRADUATE_SIGNALS):
        return "graduate"
    if any(s in t for s in _JUNIOR_SIGNALS):
        return "junior"
    if any(s in t for s in _ENTRY_SIGNALS) or any(s in d for s in _ENTRY_SIGNALS):
        return "entry"
    if any(s in t for s in _MID_SIGNALS) or any(s in d for s in _MID_SIGNALS):
        return "mid"

    # Fall back to description signals for the strong cues
    if any(s in d for s in _INTERN_SIGNALS):
        return "intern"
    if any(s in d for s in _SENIOR_SIGNALS):
        return "senior"
    if any(s in d for s in _GRADUATE_SIGNALS):
        return "graduate"

    # No clear signal — don't guess "mid" and over-filter. Leave it open so a
    # plain "Data Analyst" still reaches an entry/junior seeker.
    return "unspecified"


def is_remote_job(job: dict) -> bool:
    """True if the job is remote / work-from-home / location-independent."""
    wt = (job.get("work_type") or "").lower()
    if wt == "remote":
        return True
    blob = f"{job.get('location', '')} {job.get('title', '')} {job.get('description', '')[:400]}".lower()
    return any(k in blob for k in ("remote", "work from home", "wfh", "anywhere", "worldwide"))


def region_allowed(job: dict, work_types: list, locations: list) -> bool:
    """
    Keep a job only if the user could actually work it from where they are.

    - Remote roles always pass (anyone can do them).
    - If the user wants remote ONLY, onsite/hybrid roles are dropped — this is
      what stops out-of-region onsite listings (e.g. UK-only Adzuna jobs) from
      cluttering a remote seeker's queue.
    - If the user also accepts onsite/hybrid and named preferred locations,
      the job's location must match one of them.
    """
    if is_remote_job(job):
        return True

    wants_onsite = any(w in (work_types or []) for w in ("onsite", "hybrid"))
    if not wants_onsite:
        return False  # remote-only seeker; this onsite role doesn't fit

    named = [l.strip().lower() for l in (locations or []) if l.strip().lower() != "remote"]
    if not named:
        return True  # no specific countries set — don't over-filter

    job_loc = (job.get("location") or "").lower()
    return any(loc in job_loc for loc in named)


def seniority_allowed(job_seniority: str, allowed_levels: list) -> bool:
    """
    A job passes if its detected level is one the user asked for. Postings with
    no clear level ('unspecified') get the benefit of the doubt and always pass —
    only roles that are *clearly* the wrong level (e.g. 'senior') are filtered.
    """
    if not allowed_levels:
        return True
    if job_seniority == "unspecified":
        return True
    return job_seniority in allowed_levels


# ---------- Score calibration ----------

def _calibrate_semantic(raw_cosine: float) -> float:
    """
    all-MiniLM-L6-v2 cosine similarity between a CV and a job posting realistically
    lands in roughly 0.15 (unrelated) to 0.65 (strong match) — it almost never
    approaches 1.0 even for an excellent fit, because the two texts are written in
    very different styles. Mapping that band onto 0..1 makes the final percentage
    intuitive (a great match reads as ~90%, not ~50%).
    """
    lo, hi = 0.15, 0.62
    scaled = (raw_cosine - lo) / (hi - lo)
    return max(0.0, min(scaled, 1.0))


def score_job(job: dict, cv_skills: list, cv_embedding: np.ndarray = None) -> dict:
    """
    Score a job against the user's CV.
    Returns the job dict with match_score, seniority and sponsorship fields added.

    cv_embedding: pass the user's CV embedding directly. If not provided,
    falls back to the single-user cv/cv_embedding.npy file (legacy path).
    """
    prefs = load_prefs()
    description = job.get("description", "") or ""
    title = job.get("title", "") or ""
    full_text = f"{title} {description}"

    # Hard exclude (e.g. "10+ years", "director level")
    if check_exclusions(full_text):
        return None

    # Detect and record seniority so callers can filter on it.
    job["seniority"] = detect_seniority(title, description)

    # Semantic similarity (captures meaning even when exact keywords don't match)
    try:
        if cv_embedding is None:
            cv_embedding = load_cv_embedding()
        job_embedding = embed_text(full_text[:1500])
        raw_semantic = cosine_similarity(cv_embedding, job_embedding)
        semantic_score = _calibrate_semantic(raw_semantic)
    except Exception as e:
        print(f"  [scorer] Semantic scoring failed, falling back to skill-only: {e}")
        semantic_score = None

    # Skill overlap — compare case-insensitively (CV skills are TitleCase,
    # job descriptions are lowercased; without .lower() nothing ever matched).
    desc_lower = full_text.lower()
    matched_skills = [s for s in cv_skills if s.lower() in desc_lower]
    skill_ratio = len(matched_skills) / max(len(cv_skills), 1)
    skill_score = min(skill_ratio * 2.5, 1.0)  # ~40% of your skills matching = full skill_score

    if semantic_score is not None:
        final_score = (semantic_score * 0.6) + (skill_score * 0.4)
    else:
        final_score = skill_score

    final_score = round(min(final_score, 1.0), 4)

    job["match_score"] = final_score
    job["sponsorship"] = check_sponsorship(full_text)
    job["matched_skills"] = matched_skills

    return job


def filter_jobs(jobs: list, cv_skills: list, cv_embedding: np.ndarray = None) -> list:
    """Score all jobs and return only those above the threshold and within
    the user's allowed seniority levels."""
    prefs = load_prefs()
    threshold = prefs.get("min_match_score", 0.55)
    allowed_levels = prefs.get("seniority_levels", [])

    scored = []
    for job in jobs:
        result = score_job(job, cv_skills, cv_embedding=cv_embedding)
        if not result:
            continue
        if not seniority_allowed(result["seniority"], allowed_levels):
            continue
        if result["match_score"] >= threshold:
            scored.append(result)

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored
