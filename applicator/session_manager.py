"""
session_manager.py — persistent, reusable logins for job sites.

Instead of storing your passwords (unsafe, and Google blocks automated logins),
we keep a per-user Chromium PROFILE directory. You log in ONCE yourself in a
visible browser window — including via "Sign in with Google" if you like — and
Chromium saves the session cookies into that profile. Every later application
run reuses the profile headlessly, so sites that remember you stay logged in.

Security note: the profile directory holds live session cookies — treat it like
a password. It lives only under this user's data folder on this machine.
"""

import sys
import subprocess
from pathlib import Path

_LOGIN_WORKER = Path(__file__).parent / "login_session.py"
_CHECK_WORKER = Path(__file__).parent / "login_check.py"


def profile_dir(user_id: str) -> Path:
    """Per-user Chromium profile directory (created on first login)."""
    d = Path(__file__).parent.parent / "data" / "users" / user_id / "browser_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_saved_session(user_id: str) -> bool:
    """True once the user has logged in at least once (profile has cookies)."""
    d = profile_dir(user_id)
    # A fresh empty dir won't have these; a used profile will.
    return any((d / marker).exists() for marker in ("Default", "Cookies", "Network"))


def clear_session(user_id: str) -> None:
    """Forget all saved logins for this user."""
    import shutil
    d = profile_dir(user_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def open_login_browser(user_id: str, start_url: str = "") -> tuple[bool, str]:
    """
    Launch a VISIBLE browser using this user's profile so they can log in to job
    sites manually. Blocks until the user closes the browser window, at which
    point the session cookies are persisted in the profile.

    Returns (ok, message).
    """
    d = profile_dir(user_id)
    try:
        proc = subprocess.run(
            [sys.executable, str(_LOGIN_WORKER), str(d), start_url or ""],
            capture_output=True, text=True, timeout=1800,  # up to 30 min to log in
        )
    except subprocess.TimeoutExpired:
        return False, "Login window timed out (30 min). Your progress may still be saved."
    except Exception as e:
        return False, f"Couldn't open the login browser: {e}"

    out = (proc.stdout or "") + (proc.stderr or "")
    if "__LOGIN_DONE__" in out:
        return True, "Session saved. You won't need to log in to those sites again."
    if "Playwright not installed" in out:
        return False, "Playwright isn't installed in this environment."
    last = (proc.stderr or "").strip().splitlines()
    return False, (last[-1] if last else "Login window closed before a session was saved.")


def test_saved_login(user_id: str, url: str) -> tuple[str, str]:
    """
    Open `url` headlessly with the saved profile and report whether the session
    still looks logged in. Returns (state, detail) where state is one of
    'logged_in', 'logged_out', 'unknown'.
    """
    import json
    if not has_saved_session(user_id):
        return "unknown", "No saved session yet — log in first."

    d = profile_dir(user_id)
    try:
        proc = subprocess.run(
            [sys.executable, str(_CHECK_WORKER), str(d), url],
            capture_output=True, text=True, timeout=90,
        )
    except subprocess.TimeoutExpired:
        return "unknown", "The check timed out."
    except Exception as e:
        return "unknown", f"Couldn't run the check: {e}"

    for line in (proc.stdout or "").splitlines():
        if line.startswith("__CHECK__"):
            try:
                data = json.loads(line[len("__CHECK__"):])
                return data.get("state", "unknown"), data.get("detail", "")
            except Exception:
                break
    err = (proc.stderr or "").strip().splitlines()
    return "unknown", (err[-1] if err else "No result from the check.")
