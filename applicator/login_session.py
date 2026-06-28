"""
login_session.py — opens a VISIBLE browser on this user's profile so they can
log in to job sites by hand. Run as a separate process (see session_manager.py).

Persistent context auto-saves cookies/localStorage into the profile directory,
so the agent's later headless runs stay logged in.

  argv[1] = profile directory (Chromium user_data_dir)
  argv[2] = optional start URL to open

Prints "__LOGIN_DONE__" when the browser is closed and the session is saved.

Importantly, we strip the automation flags and prefer the user's REAL Chrome.
Google and others block sign-in on automation-controlled browsers ("this browser
may not be secure"), so a vanilla Playwright Chromium can't log into Google.
"""

import sys
import time
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# Friendly chooser. Links open in the SAME tab (no target=_blank popups, which
# Chromium blocks under automation), and there's a real address bar to type into.
_LANDING = """
<!doctype html><html><head><meta charset="utf-8"><title>HiredAI — log in</title>
<style>
 body{font-family:system-ui,Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;
      max-width:640px;margin:40px auto;padding:0 24px;line-height:1.6}
 h1{color:#6366f1} a{color:#22d3ee;font-size:1.15rem;display:block;margin:12px 0}
 .note{background:#1e293b;padding:16px;border-radius:10px;margin-top:20px;color:#94a3b8}
</style></head><body>
 <h1>🔐 Log in to your job sites</h1>
 <p>Click a site (or type any address in the bar above). Sign in normally —
 including “Sign in with Google” if you like. When you're done,
 <b>close this window</b> and your sessions are saved automatically.</p>
 <a href="https://himalayas.app/login">→ Himalayas</a>
 <a href="https://remotive.com/">→ Remotive</a>
 <a href="https://www.arbeitnow.com/">→ Arbeitnow</a>
 <a href="https://www.linkedin.com/login">→ LinkedIn</a>
 <div class="note">HiredAI never sees or stores your passwords — only the
 browser session (cookies) is kept, on this machine, under your user folder.</div>
</body></html>
"""

# Flags that make the browser look like a normal user browser, not a bot.
_LAUNCH_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]
_IGNORE_ARGS = ["--enable-automation"]


def _launch(p, profile_dir):
    """Prefer the user's real Chrome (Google trusts it); fall back to Edge, then
    to Playwright's bundled Chromium."""
    last_err = None
    for channel in ("chrome", "msedge", None):
        try:
            kwargs = dict(
                user_data_dir=profile_dir,
                headless=False,
                args=_LAUNCH_ARGS,
                ignore_default_args=_IGNORE_ARGS,
                no_viewport=True,
            )
            if channel:
                kwargs["channel"] = channel
            return p.chromium.launch_persistent_context(**kwargs)
        except Exception as e:
            last_err = e
            continue
    raise last_err


def main():
    if len(sys.argv) < 2:
        print("no profile dir given", file=sys.stderr)
        return

    profile_dir = sys.argv[1]
    start_url = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed", file=sys.stderr)
        return

    with sync_playwright() as p:
        try:
            context = _launch(p, profile_dir)
        except Exception as e:
            print(f"Could not launch a browser: {e}", file=sys.stderr)
            return

        # Hide the webdriver flag that sites sniff for.
        try:
            context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )
        except Exception:
            pass

        page = context.pages[0] if context.pages else context.new_page()

        try:
            if start_url:
                page.goto(start_url, timeout=45000)
            else:
                page.set_content(_LANDING)
        except Exception:
            # Navigation hiccup shouldn't close the window — let the user use the
            # address bar manually.
            try:
                page.set_content(_LANDING)
            except Exception:
                pass

        # Wait until the user closes the browser. Accessing context.pages after
        # close raises, which is our signal that they're done.
        deadline = time.time() + 1800
        try:
            while time.time() < deadline:
                if not context.pages:
                    break
                time.sleep(1)
        except Exception:
            pass
        finally:
            try:
                context.close()
            except Exception:
                pass

    print("__LOGIN_DONE__")


if __name__ == "__main__":
    main()
