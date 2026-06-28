"""
apply_manager.py (multi-user) — prepares an application fully (tailored CV +
cover letter), then STOPS at 'awaiting_review' instead of submitting.

The actual submission only happens when submit_application() is called,
which the Streamlit UI triggers after the user clicks Confirm on the
review screen. This is the human-in-the-loop safety step.

If a user has explicitly set auto_apply=True in their settings, run_agent
can call submit_application() immediately after prepare_application() —
but the default and recommended path is always: prepare, show, confirm, submit.
"""

import sys
import json
import time
import tempfile
import subprocess
from pathlib import Path

from database.db_manager_multiuser import update_job_status, get_user, get_job_status
from applicator.cover_letter import generate_cover_letter

try:
    import playwright  # noqa: F401
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

_WORKER = Path(__file__).parent / "submit_worker.py"


def _base_cv_path(user_id: str) -> str | None:
    """The user's original uploaded CV (PDF) — used as-is for applications."""
    p = Path(__file__).parent.parent / "data" / "users" / user_id / "cv" / "my_cv.pdf"
    return str(p) if p.exists() else None


def prepare_application(user_id: str, job: dict, structured_cv: dict, cv_text: str) -> dict:
    """
    Does everything EXCEPT submit: writes the cover letter and marks the job
    'awaiting_review'. The user's original uploaded CV is used as-is for the
    application (no tailoring).

    Returns a dict with the prepared materials so the UI can show them
    on the review screen.
    """
    # Block only if this job has already been prepared/applied/skipped before —
    # a 'pending' row from the current scrape is expected and should proceed.
    existing = get_job_status(user_id, job["job_id"])
    if existing and existing not in ("pending",):
        return {"status": "duplicate"}

    cover_letter = generate_cover_letter(job, cv_text, structured_cv=structured_cv)
    cv_path = _base_cv_path(user_id)

    note = ("Prepared — your uploaded CV will be used, waiting for confirmation"
            if cv_path else
            "Prepared — no CV on file; upload one in Setup before submitting")

    update_job_status(
        user_id, job["job_id"], "awaiting_review",
        cover_letter=cover_letter, tailored_cv_path=cv_path,
        notes=note
    )

    return {
        "status": "awaiting_review",
        "job": job,
        "cover_letter": cover_letter,
        "tailored_cv_path": cv_path,
    }


def submit_application(user_id: str, job: dict, tailored_cv_path: str | None,
                       structured_cv: dict | None = None) -> str:
    """
    Submits the application via Playwright, run in a SEPARATE PROCESS.

    Running Playwright directly here fails on Windows because Streamlit
    executes this code in a worker thread, where the asyncio event loop
    can't spawn the browser subprocess (raises NotImplementedError).
    The submit_worker.py child process gets its own main-thread
    ProactorEventLoop, which works correctly.

    Returns: 'applied', 'manual_review', or 'failed'
    """
    if not PLAYWRIGHT_AVAILABLE:
        update_job_status(user_id, job["job_id"], "manual_review",
                          notes="Playwright not installed — manual application needed")
        return "manual_review"

    from applicator.session_manager import profile_dir, has_saved_session

    payload = {
        "job": job,
        "cv_path": tailored_cv_path,
        "structured_cv": structured_cv,
        "profile_dir": str(profile_dir(user_id)) if has_saved_session(user_id) else None,
    }

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(payload, f)
            tmp = f.name

        proc = subprocess.run(
            [sys.executable, str(_WORKER), tmp],
            capture_output=True, text=True, timeout=120,
        )

        result, error = _parse_worker_output(proc)

    except subprocess.TimeoutExpired:
        result, error = "failed", "Submission timed out after 120s"
    except Exception as e:
        result, error = "failed", str(e).strip() or type(e).__name__
    finally:
        if tmp:
            Path(tmp).unlink(missing_ok=True)

    if result == "applied":
        update_job_status(user_id, job["job_id"], "applied",
                          notes="Submitted successfully")
        print(f"  [apply] Applied: {job['title']} @ {job['company']} (user {user_id[:8]})")
    elif result == "manual_review":
        update_job_status(user_id, job["job_id"], "manual_review", notes=error)
    else:
        update_job_status(user_id, job["job_id"], "failed", notes=error)
        print(f"  [apply] Failed: {job['title']} — {error}")

    return result


def _parse_worker_output(proc: subprocess.CompletedProcess) -> tuple[str, str | None]:
    """Extract the worker's JSON result line; fall back to stderr on a crash."""
    marker = "__RESULT__"
    for line in (proc.stdout or "").splitlines():
        if line.startswith(marker):
            data = json.loads(line[len(marker):])
            return data.get("result", "failed"), data.get("error")
    # Worker crashed before emitting a result.
    err = (proc.stderr or "").strip().splitlines()
    detail = err[-1] if err else f"worker exited with code {proc.returncode}"
    return "failed", detail


def skip_application(user_id: str, job: dict):
    """User reviewed and chose not to apply."""
    update_job_status(user_id, job["job_id"], "skipped", notes="User skipped after review")