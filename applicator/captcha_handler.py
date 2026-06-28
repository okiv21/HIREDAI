"""
captcha_handler.py — best-effort CAPTCHA solving for application forms.

Uses CapSolver (https://capsolver.com) — a paid, proxyless solving service.
Set CAPSOLVER_API_KEY in your .env to enable it; without a key, CAPTCHAs are
flagged for manual review.

Supports the two CAPTCHAs that actually show up on job forms:
  • hCaptcha          (CapSolver task: HCaptchaTaskProxyless)
  • reCAPTCHA v2      (CapSolver task: ReCaptchaV2TaskProxyless)

Limitations (be realistic):
  • reCAPTCHA v3 / Enterprise and Cloudflare Turnstile are not handled here.
  • A solver CANNOT get past a LOGIN wall — that needs your credentials, which
    this tool deliberately does not store. Login-gated forms stay 'manual_review'.
"""

import os
import time
import requests

CREATE_TASK_URL = "https://api.capsolver.com/createTask"
GET_RESULT_URL = "https://api.capsolver.com/getTaskResult"


def _detect_captcha(page) -> tuple[str | None, str | None]:
    """
    Inspect the page and return (kind, sitekey) where kind is 'hcaptcha' or
    'recaptcha', or (None, None) if no supported CAPTCHA is present.
    """
    js = r"""
    () => {
      const attr = (sel, name) => {
        const el = document.querySelector(sel);
        return el ? el.getAttribute(name) : null;
      };
      const fromIframe = (substr, param) => {
        const f = Array.from(document.querySelectorAll('iframe'))
                       .find(i => (i.src || '').includes(substr));
        if (!f) return null;
        try { return new URL(f.src).searchParams.get(param); } catch (e) { return null; }
      };

      // hCaptcha
      let hk = attr('.h-captcha', 'data-sitekey')
            || attr('[data-hcaptcha-sitekey]', 'data-hcaptcha-sitekey')
            || fromIframe('hcaptcha.com', 'sitekey');
      if (hk) return { kind: 'hcaptcha', sitekey: hk };

      // reCAPTCHA v2
      let rk = attr('.g-recaptcha', 'data-sitekey')
            || attr('[data-sitekey]', 'data-sitekey')
            || fromIframe('recaptcha', 'k');
      if (rk) return { kind: 'recaptcha', sitekey: rk };

      return { kind: null, sitekey: null };
    }
    """
    try:
        result = page.evaluate(js)
        return result.get("kind"), result.get("sitekey")
    except Exception:
        return None, None


def _solve_with_capsolver(kind: str, sitekey: str, page_url: str) -> str | None:
    """Submit a solving task to CapSolver and poll for the token."""
    api_key = os.getenv("CAPSOLVER_API_KEY", "")
    if not api_key:
        return None

    task_type = "HCaptchaTaskProxyless" if kind == "hcaptcha" else "ReCaptchaV2TaskProxyless"

    try:
        resp = requests.post(CREATE_TASK_URL, timeout=15, json={
            "clientKey": api_key,
            "task": {
                "type": task_type,
                "websiteURL": page_url,
                "websiteKey": sitekey,
            },
        })
        data = resp.json()
        if data.get("errorId"):
            print(f"  [captcha] CapSolver createTask error: {data.get('errorDescription')}")
            return None

        task_id = data.get("taskId")
        if not task_id:
            return None

        # Poll up to ~60s — solving can genuinely take 20-40s.
        for _ in range(20):
            time.sleep(3)
            r = requests.post(GET_RESULT_URL, timeout=15, json={
                "clientKey": api_key, "taskId": task_id,
            }).json()

            if r.get("errorId"):
                print(f"  [captcha] CapSolver result error: {r.get('errorDescription')}")
                return None
            if r.get("status") == "ready":
                return r.get("solution", {}).get("gRecaptchaResponse")

        print("  [captcha] CapSolver timed out before solving")
        return None
    except Exception as e:
        print(f"  [captcha] CapSolver request failed: {e}")
        return None


def _inject_token(page, kind: str, token: str) -> bool:
    """
    Write the solved token into the page's hidden response field(s) and fire
    any callback the widget registered, so the form accepts it on submit.
    """
    js = r"""
    (args) => {
      const { kind, token } = args;
      const setVal = (sel) => {
        document.querySelectorAll(sel).forEach(el => {
          el.value = token;
          el.style.display = '';          // some sites hide it; harmless to show
          el.dispatchEvent(new Event('change', { bubbles: true }));
        });
      };

      if (kind === 'recaptcha') {
        setVal('#g-recaptcha-response');
        setVal('textarea[name="g-recaptcha-response"]');
      } else {
        setVal('[name="h-captcha-response"]');
        setVal('[name="g-recaptcha-response"]');
      }

      // Best-effort: invoke a registered callback if one exists.
      try {
        if (kind === 'recaptcha' && window.grecaptcha && window.___grecaptcha_cfg) {
          const clients = window.___grecaptcha_cfg.clients || {};
          for (const id in clients) {
            const c = clients[id];
            for (const k in c) {
              const o = c[k];
              if (o && o.callback && typeof o.callback === 'function') {
                o.callback(token); return true;
              }
              for (const kk in (o || {})) {
                const oo = o[kk];
                if (oo && typeof oo.callback === 'function') { oo.callback(token); return true; }
              }
            }
          }
        }
      } catch (e) {}
      return true;
    }
    """
    try:
        page.evaluate(js, {"kind": kind, "token": token})
        return True
    except Exception as e:
        print(f"  [captcha] Token injection failed: {e}")
        return False


def handle_captcha(page, page_url: str) -> bool:
    """
    Returns True if the page can proceed (no CAPTCHA, or one we solved),
    False if a CAPTCHA is present that we couldn't solve (→ manual review).
    """
    kind, sitekey = _detect_captcha(page)

    if not kind or not sitekey:
        return True  # No supported CAPTCHA detected — proceed normally.

    if not os.getenv("CAPSOLVER_API_KEY"):
        print(f"  [captcha] {kind} detected but CAPSOLVER_API_KEY not set — manual review")
        return False

    print(f"  [captcha] {kind} detected — solving via CapSolver...")
    token = _solve_with_capsolver(kind, sitekey, page_url)
    if not token:
        print("  [captcha] Could not solve — flagging for manual review")
        return False

    if _inject_token(page, kind, token):
        print("  [captcha] Solved and token injected")
        time.sleep(1)
        return True

    return False
