"""
cv_tailor.py — Tailors a structured CV to match a specific job description.

Workflow:
1. CV is stored as structured JSON (not raw text) — see cv/cv_structured.json
2. For each job application, the LLM:
   - Reorders bullet points to surface the most relevant experience
   - Rephrases bullets using the job's terminology (without fabricating experience)
   - Adjusts the skills section ordering to match keywords in the posting
3. Outputs a new structured JSON, which gets rendered to .docx (see cv_renderer.py)

IMPORTANT: This only rephrases and reorders existing, truthful content.
It never invents skills, experience, or qualifications the user doesn't have.
"""

import os
import json
import requests
from pathlib import Path

CV_DIR = Path(__file__).parent.parent / "cv"
STRUCTURED_CV_PATH = CV_DIR / "cv_structured.json"
TAILORED_DIR = CV_DIR / "tailored"
TAILORED_DIR.mkdir(exist_ok=True)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def load_structured_cv() -> dict:
    """
    Expected structure of cv_structured.json:
    {
      "name": "...",
      "contact": {"email": "...", "phone": "...", "location": "...", "linkedin": "...", "github": "..."},
      "summary": "...",
      "skills": ["Python", "SQL", ...],
      "experience": [
        {"title": "...", "company": "...", "dates": "...", "bullets": ["...", "..."]}
      ],
      "projects": [
        {"name": "...", "description": "...", "bullets": ["...", "..."]}
      ],
      "education": [
        {"degree": "...", "institution": "...", "dates": "..."}
      ]
    }
    """
    if not STRUCTURED_CV_PATH.exists():
        raise FileNotFoundError(
            "cv_structured.json not found. Create it manually following the "
            "schema in cv_tailor.py's load_structured_cv() docstring, or build "
            "it from your existing CV PDF/docx with a one-off conversion script."
        )
    return json.loads(STRUCTURED_CV_PATH.read_text())


def _call_llm(prompt: str, max_tokens: int = 2000) -> str:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,  # lower temp — faithful edits, not creative ones
    }
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=40)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def tailor_cv(cv: dict, job: dict) -> dict:
    """
    Takes the structured base CV + a job dict (title, company, description),
    returns a tailored structured CV (same schema, edited content).
    """
    job_title = job.get("title", "")
    company = job.get("company", "")
    description = job.get("description", "")[:1500]

    prompt = f"""
You are tailoring a candidate's CV for a specific job application.

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{description}

CANDIDATE'S CURRENT CV (JSON):
{json.dumps(cv, indent=2)}

TASK:
Return an edited version of this CV as JSON, following these STRICT rules:

1. DO NOT invent, exaggerate, or add any skill, tool, experience, or qualification
   that is not already present in the original CV. This is non-negotiable.
2. You MAY reorder the "skills" list to put job-relevant skills first.
3. You MAY reorder "experience" and "projects" bullet points within each entry
   to surface the most relevant ones first.
4. You MAY lightly rephrase existing bullet points to use terminology from the
   job description IF AND ONLY IF the underlying fact stays identical
   (e.g. "built ML models" -> "developed machine learning models" is fine;
   adding a tool or result that wasn't there is NOT fine).
5. You MAY rewrite the "summary" field to better align with the role, using only
   facts already present elsewhere in the CV.
6. Do NOT change names, dates, company names, degree names, or institutions.
7. Keep the exact same JSON schema/keys as the input.

Return ONLY the JSON object. No markdown, no explanation, no code fences.
"""

    raw_response = _call_llm(prompt)
    cleaned = _strip_code_fences(raw_response)

    try:
        tailored = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  [cv_tailor] Failed to parse LLM output as JSON: {e}")
        print("  [cv_tailor] Falling back to original CV (untailored)")
        return cv

    return tailored


def _verify_no_fabrication(original: dict, tailored: dict) -> list:
    """
    Lightweight safety check: flags any skill in the tailored CV that
    wasn't in the original. Doesn't catch fabricated bullet *claims*
    (that needs human review), but catches the most common failure mode.
    """
    warnings = []
    original_skills = set(s.lower() for s in original.get("skills", []))
    tailored_skills = set(s.lower() for s in tailored.get("skills", []))
    new_skills = tailored_skills - original_skills
    if new_skills:
        warnings.append(f"New skills appeared that weren't in original CV: {new_skills}")
    return warnings


def save_tailored_cv(tailored: dict, job: dict) -> Path:
    """Save tailored CV JSON to a job-specific file."""
    safe_company = "".join(c for c in job.get("company", "job") if c.isalnum())[:30]
    safe_title = "".join(c for c in job.get("title", "role") if c.isalnum())[:30]
    job_id_suffix = job.get("job_id", "")[:8]
    filename = f"{safe_company}_{safe_title}_{job_id_suffix}.json"
    out_path = TAILORED_DIR / filename
    out_path.write_text(json.dumps(tailored, indent=2))
    return out_path


def tailor_for_job(job: dict) -> dict | None:
    """
    Full pipeline: load base CV, tailor it for this job, verify, save result.
    Returns the tailored CV dict, or None if tailoring failed entirely.
    """
    try:
        base_cv = load_structured_cv()
    except FileNotFoundError as e:
        print(f"  [cv_tailor] {e}")
        return None

    tailored = tailor_cv(base_cv, job)

    warnings = _verify_no_fabrication(base_cv, tailored)
    if warnings:
        for w in warnings:
            print(f"  [cv_tailor] WARNING: {w}")
        print("  [cv_tailor] Falling back to original CV due to fabrication risk")
        tailored = base_cv

    path = save_tailored_cv(tailored, job)
    print(f"  [cv_tailor] Tailored CV saved: {path.name}")
    return tailored
