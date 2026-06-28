import json
import time
from pathlib import Path
from applicator.captcha_handler import handle_captcha
from applicator.answer_generator import generate_answer

PROFILE_PATH = Path(__file__).parent.parent / "config" / "user_profile.json"

# Space out Groq calls so a form with many questions sends them one at a time
# (back-to-back requests trip Groq's free-tier rate limits).
ANSWER_DELAY_SECONDS = 2.0

FIELD_MAP = {
    "first name": "first_name",
    "last name": "last_name",
    "full name": "full_name",
    "name": "full_name",
    "email": "email",
    "phone": "phone",
    "mobile": "phone",
    "linkedin": "linkedin",
    "github": "github",
    "location": "location",
    "city": "location",
    "country": "nationality",
}

OPEN_ENDED_TRIGGERS = [
    "tell us about yourself", "about you", "why do you want",
    "why are you interested", "cover letter", "summary",
    "describe yourself", "motivation", "introduce yourself"
]

# Text we look for on a real "submit application" button. Kept deliberately
# specific so we don't accidentally click "Search", "Sign in", "Save" etc.
SUBMIT_BUTTON_TEXTS = [
    "submit application", "submit your application", "send application",
    "apply now", "submit", "send application", "finish & apply",
    "complete application",
]


_LABEL_JS = """
(el) => {
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  // 1. Explicit accessibility labels
  let aria = el.getAttribute('aria-label');
  if (clean(aria)) return clean(aria);
  let labelledby = el.getAttribute('aria-labelledby');
  if (labelledby) {
    const l = document.getElementById(labelledby);
    if (l && clean(l.innerText)) return clean(l.innerText);
  }
  // 2. <label for="id">
  if (el.id) {
    const l = document.querySelector('label[for="' + el.id + '"]');
    if (l && clean(l.innerText)) return clean(l.innerText);
  }
  // 3. Wrapping <label>
  const wrap = el.closest('label');
  if (wrap && clean(wrap.innerText)) return clean(wrap.innerText);
  // 4. Nearest preceding text node / element
  let prev = el.previousElementSibling;
  while (prev) {
    if (clean(prev.innerText)) return clean(prev.innerText);
    prev = prev.previousElementSibling;
  }
  // 5. Fall back to placeholder / name
  return clean(el.getAttribute('placeholder')) || clean(el.getAttribute('name')) || '';
}
"""


def _field_label(field) -> str:
    """Return the human-readable question/label for a form field, looking at
    aria-label, <label>, nearby text, then placeholder/name as a last resort."""
    try:
        text = field.evaluate(_LABEL_JS)
        return (text or "").strip()
    except Exception:
        try:
            return (field.get_attribute("placeholder")
                    or field.get_attribute("name") or "").strip()
        except Exception:
            return ""


# Field labels that are NOT real questions (just structural/profile fields we
# either already handle or should leave alone).
_SKIP_LABEL_HINTS = [
    "search", "keyword", "postcode", "zip", "captcha",
]


def _is_question(label: str) -> bool:
    """Decide whether a free-text field is an application question worth
    answering with the LLM. Skips empty, trivial, or clearly non-question fields."""
    if not label:
        return False
    low = label.lower()
    if any(h in low for h in _SKIP_LABEL_HINTS):
        return False
    # A real question: ends with '?', or is a reasonably worded prompt,
    # or matches one of the classic open-ended triggers.
    if "?" in label:
        return True
    if any(t in low for t in OPEN_ENDED_TRIGGERS):
        return True
    return len(label.split()) >= 3


def _looks_like_real_form(page) -> bool:
    """A genuine application form has at least a file upload or several inputs.
    Many Adzuna 'jobs' just redirect to a listing page with no form at all."""
    try:
        if page.query_selector("input[type=file]"):
            return True
        fields = page.query_selector_all("input, textarea, select")
        meaningful = [
            f for f in fields
            if (f.get_attribute("type") or "text") not in ("hidden", "submit", "button")
        ]
        return len(meaningful) >= 3
    except Exception:
        return False


def _click_submit(page) -> bool:
    """Find and click a real 'submit application' button. Returns True only if
    one was found and clicked — otherwise we cannot honestly claim we applied."""
    try:
        for text in SUBMIT_BUTTON_TEXTS:
            # Case-insensitive match on button / input[type=submit] / link text.
            selector = (
                f"button:has-text(\"{text}\"), "
                f"input[type=submit][value*=\"{text}\" i], "
                f"a:has-text(\"{text}\")"
            )
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                time.sleep(2)
                return True
    except Exception:
        pass
    return False


def _build_profile_from_cv(structured_cv: dict) -> dict:
    contact = structured_cv.get("contact", {})
    full_name = structured_cv.get("name", "")
    parts = full_name.split(" ", 1)
    return {
        "full_name": full_name,
        "first_name": parts[0] if parts else "",
        "last_name": parts[1] if len(parts) > 1 else "",
        "email": contact.get("email", ""),
        "phone": contact.get("phone", ""),
        "linkedin": contact.get("linkedin", ""),
        "github": contact.get("github", ""),
        "location": contact.get("location", ""),
        "nationality": contact.get("nationality", ""),
    }


def load_profile(structured_cv: dict | None = None) -> dict:
    if structured_cv:
        return _build_profile_from_cv(structured_cv)
    if PROFILE_PATH.exists():
        p = json.loads(PROFILE_PATH.read_text())
        parts = p.get("full_name", "").split(" ", 1)
        p["first_name"] = parts[0] if parts else ""
        p["last_name"] = parts[1] if len(parts) > 1 else ""
        return p
    return {}


def fill_form(page, job: dict, cv_path: str = None, structured_cv: dict | None = None) -> bool:
    """
    Attempt to fill AND submit a job application form.

    Returns True ONLY if a real form was filled and a submit button was
    found and clicked. Returns False (-> 'manual_review') if there's no
    real form to fill or no submit button to click, so we never falsely
    report "applied" when nothing was actually submitted.
    """
    profile = load_profile(structured_cv)
    answers_generated = 0  # used to pace Groq calls one at a time

    try:
        # Handle CAPTCHA first
        if not handle_captcha(page, page.url):
            return False

        time.sleep(1)

        # Bail out honestly if this page isn't actually an application form
        # (many Adzuna links redirect to a plain listing / aggregator page).
        if not _looks_like_real_form(page):
            return False

        inputs = page.query_selector_all("input, textarea, select")

        for field in inputs:
            try:
                field_type = field.get_attribute("type") or "text"

                # The REAL visible question, not just a cryptic name attribute.
                question = _field_label(field)
                label_text = question.lower()

                # File upload (CV)
                if field_type == "file" and cv_path:
                    field.set_input_files(cv_path)
                    continue

                # Checkbox (right to work, terms etc) — auto-check
                if field_type == "checkbox":
                    field.check()
                    continue

                # Simple field mapping (name, email, phone, etc.)
                matched_key = None
                for trigger, key in FIELD_MAP.items():
                    if trigger in label_text:
                        matched_key = key
                        break

                if matched_key and profile.get(matched_key):
                    field.fill(str(profile[matched_key]))
                    continue

                # Any remaining free-text question → answer it with Groq using
                # the applicant's actual CV. We answer broadly now (not just a
                # fixed trigger list) as long as there's a real question to answer.
                # Calls are paced one at a time to stay under Groq rate limits.
                if field_type in ("text", "textarea") and _is_question(question):
                    if answers_generated > 0:
                        time.sleep(ANSWER_DELAY_SECONDS)
                    answer = generate_answer(question, job, structured_cv=structured_cv)
                    answers_generated += 1
                    if answer:
                        field.fill(answer)
                    continue

            except Exception:
                continue

        # Only report success if we actually submit the form.
        return _click_submit(page)

    except Exception as e:
        print(f"  [form_filler] Error: {e}")
        return False
