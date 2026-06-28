# 🎯 HiredAI

An AI job-application agent. It searches remote-friendly job boards, scores each
listing against **your** CV, writes a tailored cover letter, drafts answers to
application questions from your CV, and prepares everything for you to review —
nothing is submitted until you confirm (unless you explicitly turn on auto-apply).

Multi-user: each person who opens the app gets their own private session — their
CV, preferences, saved logins and application history stay separate from everyone
else's. Shared API keys live in the server's `.env`, which is fine for a small
group on free-tier keys.

> **Privacy:** your CV, embeddings, saved login cookies and the jobs database all
> live under `data/` and are **git-ignored** — they never leave your machine.

---

## 1. Install

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
playwright install chromium
npm install -g docx        # optional, only used by the legacy CV-tailoring path
```

## 2. Add your API key

Copy the example env file and fill in your Groq key (the only one required):

```bash
cp .env.example .env
```

- **Groq** (required) — free at <https://console.groq.com>. Powers CV parsing,
  matching, cover letters and form answers.
- **CapSolver** (optional) — <https://capsolver.com>, pay-as-you-go. Enables
  automatic solving of hCaptcha / reCAPTCHA v2 on application forms.
- Adzuna / Reed / Telegram are optional and off by default.

## 3. Run

```bash
streamlit run dashboard/app.py
```

Opens at <http://localhost:8501>.

---

## How to use it

### Setup tab
1. **Upload your CV** (PDF) and click **Parse & structure CV**. Review the
   extracted JSON — this becomes the source of truth for matching and answers.
2. **Job preferences** — job titles, seniority levels (intern → senior),
   work type, preferred locations, sponsorship preference, and your minimum
   match score.
3. **Saved logins** (optional but recommended) — click **Open browser & log in**.
   Your real Chrome opens; sign in to any job sites (including "Sign in with
   Google"), then close the window. The agent reuses that session so login-walled
   sites let it through. Use **Test saved login** to check a session is still
   valid. *Your passwords are never stored — only the browser session cookies,
   on your machine.*
4. **Submission mode** — review each application first (recommended) or
   auto-apply.
5. Click **🚀 Find matching jobs now**.

### Review queue tab
Every prepared match shows its **CV match score**, the attached CV, and an
editable cover letter. Click **Confirm & submit** or **Skip**. Anything the agent
couldn't auto-submit (login walls, non-form pages) drops into a
**"🔧 Needs you to finish manually"** section with a one-click link to the
posting plus your cover letter and CV ready to use.

### History tab
Track everything with status filters, submitted/found timestamps, and manual
status correction.

---

## Features

- **Sources:** Remotive, Arbeitnow, Himalayas (remote-first). Adzuna and Reed are
  built in but disabled by default — toggle in `config/platforms.json`.
- **Smart matching:** Sentence-BERT semantic similarity + case-insensitive skill
  overlap, calibrated to an intuitive 0–100% score.
- **Region & level filters:** drops onsite roles outside your region and roles
  outside your chosen seniority levels.
- **Cover letters & form answers** generated per job from your real CV via Groq
  (Llama 3.3 70B) — grounded in your CV, never fabricated.
- **Saved logins** via a persistent Chrome profile, so sites stay signed in.
- **CAPTCHA solving** (hCaptcha / reCAPTCHA v2) via CapSolver when a key is set.
- **Human-in-the-loop by default** — review, edit, then confirm. Auto-apply is
  opt-in.
- **Visa-sponsorship flagging** for international candidates.

---

## Honest limitations

- **"Applied" ≠ guaranteed.** It means the form was filled and submit was
  clicked. Confirmation emails (if any) come from the *employer's* system, not
  HiredAI — always verify important applications on the job site.
- **Login walls need you.** A CAPTCHA solver can't get past a login that needs
  your account; those land in the manual-completion section. Saved logins help
  here, but sessions expire and need an occasional refresh.
- **Not every site is auto-submittable.** Aggregator links and multi-step /
  authenticated forms are flagged for manual completion rather than faked as
  "applied".
- CapSolver is paid per solve; reCAPTCHA v3 / Enterprise and Cloudflare Turnstile
  aren't handled.

---

## Suggested first run

1. Boot the app — no errors in the terminal.
2. Upload a real CV and sanity-check the structured JSON.
3. Run with a **high** minimum match score (e.g. 0.85) first, so few jobs reach
   the apply stage — confirms scraping + scoring work.
4. Lower it gradually, read the cover letters in the Review queue.
5. Confirm exactly one low-stakes job and verify it on the employer's site.
6. Only then rely on it more broadly.
