"""
login_check.py — verifies a saved browser session is still logged in.

Opens a site headlessly using the user's saved profile (see session_manager.py)
and reports whether the page looks logged-in or logged-out. Run as a separate
process so it gets a subprocess-capable event loop on Windows.

  argv[1] = profile directory (Chromium user_data_dir)
  argv[2] = site url to test

Prints "__CHECK__" + JSON: {"state": "logged_in|logged_out|unknown", "detail": "..."}
"""

import sys
import json
import time
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# Words/links that signal you are NOT logged in, vs that you ARE.
_LOGGED_OUT_HINTS = ["sign in", "log in", "login", "create account", "join now", "register"]
_LOGGED_IN_HINTS = ["sign out", "log out", "logout", "my account", "profile", "dashboard",
                    "saved jobs", "applications"]


def _launch(p, profile_dir, user_agent):
    last_err = None
    for channel in ("chrome", "msedge", None):
        try:
            kw = dict(user_data_dir=profile_dir, headless=True, user_agent=user_agent)
            if channel:
                kw["channel"] = channel
            return p.chromium.launch_persistent_context(**kw)
        except Exception as e:
            last_err = e
            continue
    raise last_err


def _classify(page) -> tuple[str, str]:
    """Decide logged_in / logged_out from visible text + auth cookies."""
    try:
        body = (page.inner_text("body") or "").lower()
    except Exception:
        body = ""

    has_out = any(h in body for h in _LOGGED_IN_HINTS)   # sign-OUT etc. = logged in
    has_in = any(h in body for h in _LOGGED_OUT_HINTS)    # sign-IN etc. = logged out

    if has_out and not has_in:
        return "logged_in", "Found account/sign-out controls on the page."
    if has_in and not has_out:
        return "logged_out", "Page is still showing a sign-in / register prompt."

    # Ambiguous text — fall back to whether any session cookies exist.
    try:
        cookies = page.context.cookies()
        auth_like = [c for c in cookies if any(
            k in (c.get("name", "").lower())
            for k in ("session", "auth", "token", "logged", "li_at", "sid")
        )]
        if auth_like:
            return "logged_in", f"Session cookies present ({len(auth_like)} found)."
    except Exception:
        pass

    return "unknown", "Couldn't tell for sure — open the site to confirm."


def main():
    if len(sys.argv) < 3:
        print('__CHECK__' + json.dumps({"state": "unknown", "detail": "missing args"}))
        return

    profile_dir, url = sys.argv[1], sys.argv[2]
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('__CHECK__' + json.dumps({"state": "unknown", "detail": "Playwright not installed"}))
        return

    try:
        with sync_playwright() as p:
            context = _launch(p, profile_dir, ua)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(2)
            state, detail = _classify(page)
            context.close()
    except Exception as e:
        state, detail = "unknown", f"Check failed: {str(e).strip() or type(e).__name__}"

    print('__CHECK__' + json.dumps({"state": state, "detail": detail}))


if __name__ == "__main__":
    main()
