-- Multi-user schema. Every job/run row is scoped to a user_id, so each
-- friend's CV, preferences, and applications stay separate. API keys
-- (Groq, Adzuna) live in the server's .env and are shared across all
-- users at this small scale — see scheduler/run_agent_multiuser.py.

CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,       -- random uuid, set on first visit/session
    name            TEXT,
    email           TEXT,
    created_at      TEXT,
    last_active_at  TEXT,
    cv_structured   TEXT,                   -- JSON blob, this user's parsed CV
    job_prefs       TEXT,                   -- JSON blob, this user's preferences
    auto_apply      INTEGER DEFAULT 0       -- 0 = review-and-confirm, 1 = full auto (not recommended)
);

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    job_id          TEXT,
    title           TEXT,
    company         TEXT,
    location        TEXT,
    work_type       TEXT,
    salary          TEXT,
    description     TEXT,
    url             TEXT,
    platform        TEXT,
    sponsorship     INTEGER DEFAULT 0,
    match_score     REAL,
    seniority       TEXT,
    field           TEXT,
    scraped_at      TEXT,
    status          TEXT DEFAULT 'pending', -- pending | awaiting_review | applied | skipped | manual_review | failed
    applied_at      TEXT,
    cover_letter    TEXT,
    tailored_cv_path TEXT,
    notes           TEXT,
    UNIQUE(user_id, job_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    run_at          TEXT,
    jobs_scraped    INTEGER,
    jobs_matched    INTEGER,
    jobs_applied    INTEGER,
    jobs_flagged    INTEGER,
    errors          TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id);
