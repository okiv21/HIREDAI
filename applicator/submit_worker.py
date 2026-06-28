"""
submit_worker.py — runs the actual Playwright form submission in its OWN process.

WHY THIS EXISTS:
Streamlit runs your script in a worker thread. On Windows, a non-main thread
gets an asyncio SelectorEventLoop, which cannot spawn subprocesses — so when
Playwright tries to launch Chromium it raises a bare `NotImplementedError`.

Running the submission as a separate process (this file, invoked via
`python submit_worker.py <payload.json>`) gives it its own main thread with a
ProactorEventLoop on Windows, which fully supports subprocess launching.

Contract:
  argv[1] = path to a JSON file: {"job": {...}, "cv_path": "...|null",
                                   "structured_cv": {...}|null}
  Prints a single JSON line to stdout: {"result": "applied|manual_review|failed",
                                        "error": "..."|null}
"""

import sys
import json
import time
import asyncio
from pathlib import Path

# Ensure project root is importable when run as a standalone process.
sys.path.insert(0, str(Path(__file__).parent.parent))

# Belt-and-suspenders: guarantee a subprocess-capable loop policy on Windows.
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass


def _run(payload: dict) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"result": "manual_review",
                "error": "Playwright not installed — manual application needed"}

    try:
        from playwright_stealth import stealth_sync
    except ImportError:
        stealth_sync = None

    from applicator.form_filler import fill_form

    job = payload["job"]
    cv_path = payload.get("cv_path")
    structured_cv = payload.get("structured_cv")
    profile_dir = payload.get("profile_dir")  # reuse saved logins if present

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    try:
        with sync_playwright() as p:
            browser = None
            if profile_dir:
                # Persistent context keeps the user's saved sessions/cookies, so
                # sites they logged into once don't ask for login again. Match the
                # channel used at login time (Chrome profile ≠ Chromium profile).
                context = None
                for channel in ("chrome", "msedge", None):
                    try:
                        kw = dict(user_data_dir=profile_dir, headless=True,
                                  user_agent=user_agent)
                        if channel:
                            kw["channel"] = channel
                        context = p.chromium.launch_persistent_context(**kw)
                        break
                    except Exception:
                        continue
                if context is None:
                    return {"result": "failed",
                            "error": "Couldn't open saved-login browser profile"}
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=user_agent)
                page = context.new_page()

            if stealth_sync:
                try:
                    stealth_sync(page)
                except Exception:
                    pass

            page.goto(job["url"], timeout=30000)
            time.sleep(2)

            success = fill_form(page, job, cv_path, structured_cv=structured_cv)
            context.close()
            if browser:
                browser.close()

        if success:
            return {"result": "applied", "error": None}
        return {"result": "manual_review",
                "error": "Form could not be fully automated"}

    except Exception as e:
        msg = str(e).strip() or f"{type(e).__name__} (no further detail available)"
        return {"result": "failed", "error": msg}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"result": "failed", "error": "no payload path given"}))
        return
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = _run(payload)
    # The result is the LAST line of stdout; anything Playwright prints stays above it.
    print("__RESULT__" + json.dumps(out))


if __name__ == "__main__":
    main()
