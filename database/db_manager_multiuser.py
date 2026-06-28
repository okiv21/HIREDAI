"""
db_manager.py (multi-user) — every read/write is scoped to a user_id.

This replaces the single-user db_manager. A user's CV, API keys, job
matches, and applications are never visible to or mixed with another
user's data — every query filters on user_id.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"
SCHEMA_PATH = Path(__file__).parent / "schema_multiuser.sql"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


# ---------- Users ----------

def create_user(name: str = "", email: str = "") -> str:
    """Create a new user and return their user_id."""
    user_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute("""
        INSERT INTO users (user_id, name, email, created_at, last_active_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, name, email, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return user_id


def get_user(user_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_cv(user_id: str, cv_structured: dict):
    conn = get_connection()
    conn.execute("UPDATE users SET cv_structured = ? WHERE user_id = ?",
                 (json.dumps(cv_structured), user_id))
    conn.commit()
    conn.close()


def update_user_prefs(user_id: str, job_prefs: dict):
    conn = get_connection()
    conn.execute("UPDATE users SET job_prefs = ? WHERE user_id = ?",
                 (json.dumps(job_prefs), user_id))
    conn.commit()
    conn.close()


def set_auto_apply(user_id: str, auto_apply: bool):
    """
    auto_apply=False (default, recommended): agent prepares everything and
    stops at 'awaiting_review' for the user to confirm in the UI.
    auto_apply=True: agent submits without a confirm step. Use with caution.
    """
    conn = get_connection()
    conn.execute("UPDATE users SET auto_apply = ? WHERE user_id = ?",
                 (int(auto_apply), user_id))
    conn.commit()
    conn.close()


def touch_user(user_id: str):
    conn = get_connection()
    conn.execute("UPDATE users SET last_active_at = ? WHERE user_id = ?",
                 (datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()


# ---------- Jobs (always scoped to user_id) ----------

def job_exists(user_id: str, job_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE user_id = ? AND job_id = ?", (user_id, job_id)
    ).fetchone()
    conn.close()
    return row is not None


def get_job_status(user_id: str, job_id: str) -> str | None:
    """Returns the current status of a job for this user, or None if it
    doesn't exist yet. Used to distinguish a fresh 'pending' match (should
    proceed to preparation) from a job already prepared/applied/skipped
    in a previous run (should be treated as a true duplicate)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM jobs WHERE user_id = ? AND job_id = ?", (user_id, job_id)
    ).fetchone()
    conn.close()
    return row["status"] if row else None


def _scalar(value):
    """SQLite can only bind str/int/float/None. Coerce anything else (e.g. a
    list or dict a scraper returned) into a safe string so a single odd field
    can't crash an entire run."""
    if value is None or isinstance(value, (str, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def save_job(user_id: str, job: dict):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO jobs
            (user_id, job_id, title, company, location, work_type, salary, description,
             url, platform, sponsorship, match_score, seniority, field, scraped_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            user_id, _scalar(job.get("job_id")), _scalar(job.get("title")),
            _scalar(job.get("company")), _scalar(job.get("location")),
            _scalar(job.get("work_type")), _scalar(job.get("salary")),
            _scalar(job.get("description")), _scalar(job.get("url")),
            _scalar(job.get("platform")), int(job.get("sponsorship", False)),
            job.get("match_score"), _scalar(job.get("seniority")),
            _scalar(job.get("field")), datetime.utcnow().isoformat()
        ))
        conn.commit()
    finally:
        conn.close()


def update_job_status(user_id: str, job_id: str, status: str,
                       cover_letter: str = None, tailored_cv_path: str = None,
                       notes: str = None):
    """
    Updates a job's status. Only overwrites cover_letter / tailored_cv_path /
    notes if a non-None value is actually passed — calling this with just a
    new status (e.g. marking 'failed') will NOT wipe out previously-saved
    cover letters or tailored CVs.
    """
    conn = get_connection()
    fields = ["status = ?", "applied_at = ?"]
    values = [status, datetime.utcnow().isoformat()]

    if cover_letter is not None:
        fields.append("cover_letter = ?")
        values.append(cover_letter)
    if tailored_cv_path is not None:
        fields.append("tailored_cv_path = ?")
        values.append(tailored_cv_path)
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)

    values.extend([user_id, job_id])
    conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE user_id = ? AND job_id = ?", values)
    conn.commit()
    conn.close()


def get_jobs(user_id: str, status: str = None, limit: int = 100) -> list:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? AND status = ? ORDER BY match_score DESC LIMIT ?",
            (user_id, status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY scraped_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_jobs_awaiting_review(user_id: str) -> list:
    """Jobs the agent has fully prepared (tailored CV + cover letter ready)
    but has not submitted — waiting for the user to confirm or skip."""
    return get_jobs(user_id, status="awaiting_review")


def get_jobs_needing_manual(user_id: str) -> list:
    """Jobs the agent prepared but couldn't auto-submit (the form needed login,
    wasn't a real form, captcha, or it errored). The user can finish these
    manually using the prepared cover letter + tailored CV."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE user_id = ? AND status IN ('manual_review', 'failed') "
        "ORDER BY match_score DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_run(user_id: str, stats: dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO runs (user_id, run_at, jobs_scraped, jobs_matched, jobs_applied, jobs_flagged, errors)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, datetime.utcnow().isoformat(),
        stats.get("scraped", 0), stats.get("matched", 0),
        stats.get("applied", 0), stats.get("flagged", 0),
        json.dumps(stats.get("errors", []))
    ))
    conn.commit()
    conn.close()